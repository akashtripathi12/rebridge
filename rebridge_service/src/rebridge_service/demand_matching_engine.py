"""Demand matching: candidate filtering, weighted scoring, and ranking.

This module implements the *filtering + scoring + ranking* core of the
Demand_Matching_Engine (Engine B, Pillar 4). On a ``LISTED`` event the engine
retrieves candidate buyers from the seeded ``BuyerPersonaRepository``, filters
them to those within the listed Item's geo radius that carry a wishlist/cart
signal for the Item's category, scores each candidate with a weighted function
of ``(intent, lifecycle, geo, price_sensitivity)``, and ranks them in
descending score order with an anti-cannibalization bias that favors
deal-seeker and price-balker personas.

Requirement traceability:
- 13.1: retrieve candidates filtered by geo, category, and wishlist/cart signal.
- 13.2: score from intent, lifecycle, geo, and price-sensitivity weights.
- 13.3: rank candidates in descending score order.
- 13.4: apply anti-cannibalization weighting favoring deal-seeker / price-balker
  personas.
- 13.5: notify the top min(N, count) ranked buyers and upsert the Item onto the
  Second-Chance PDP shelf (:meth:`DemandMatchingEngine.match`).
- 13.6: operate over seeded buyer persona data (the injected repository).
- 15.4: emit a ``MATCHED`` event identifying the Item when the engine pushes to
  ranked buyers (:meth:`DemandMatchingEngine.match`, via ``EventingService``).

:meth:`DemandMatchingEngine.rank` returns the full ranked list of scored
candidates; :meth:`DemandMatchingEngine.match` slices it to the configured
top-N, notifies those buyers through the injected :class:`BuyerNotifier`, upserts
the Item onto the injected :class:`SecondChanceShelf`, and emits ``MATCHED``
through the injected :class:`EventingService`.

The engine is framework-free: it depends only on the abstract
``BuyerPersonaRepository``, ``BuyerNotifier``, and ``SecondChanceShelf`` seams,
the ``EventingService`` (itself programmed against ``EventPublisher``), and the
standard library. No AWS, no web framework, no persistence side effects.
"""

from __future__ import annotations

from dataclasses import dataclass

from rebridge_data.geohash import geohash_distance_km, seeded_distance_km
from rebridge_data.interfaces import (
    BuyerNotifier,
    BuyerPersonaRepository,
    SecondChanceShelf,
)
from rebridge_data.models import BuyerPersona, LifecycleEvent

from rebridge_service.eventing_service import EventingService

__all__ = [
    "FAVORED_PERSONA_TYPES",
    "MatchWeights",
    "ScoredCandidate",
    "MatchResult",
    "BuyerMatch",
    "MatchView",
    "DemandMatchingEngine",
]


# Requirement 13.4: persona types that receive the anti-cannibalization bias.
# Deal-seekers and price-balkers are buyers who would not have paid full price
# for a new unit, so steering recoverable inventory toward them grows the pie
# instead of cannibalizing first-hand sales.
FAVORED_PERSONA_TYPES: frozenset[str] = frozenset({"deal_seeker", "price_balker"})


@dataclass(frozen=True)
class MatchWeights:
    """Configurable weights for the candidate scoring function (Req 13.2, 13.4).

    The four signal weights combine the per-candidate signals into a base score:

        base = intent*w_intent + lifecycle*w_lifecycle
             + geo*w_geo + price_sensitivity*w_price_sensitivity

    ``anti_cannibalization_bonus`` is a non-negative additive term applied to
    favored personas (deal-seeker / price-balker) on top of the base score
    (Requirement 13.4). Being additive and non-negative guarantees that, all
    other signals equal, a favored persona never ranks below a non-favored one.

    Default assumptions (documented, not derived from the spec, which leaves the
    exact weights open):
    - ``intent`` is weighted highest (0.40): an explicit purchase signal is the
      strongest predictor of a match.
    - ``lifecycle``, ``geo``, and ``price_sensitivity`` each carry 0.20; the
      four weights sum to 1.0 so a base score stays in [0, 1] for signals in
      [0, 1].
    - ``anti_cannibalization_bonus`` is 0.15: enough to lift a favored persona
      above an otherwise-equal non-favored one without swamping a much stronger
      base score from a non-favored buyer.
    """

    intent: float = 0.40
    lifecycle: float = 0.20
    geo: float = 0.20
    price_sensitivity: float = 0.20
    anti_cannibalization_bonus: float = 0.15

    def __post_init__(self) -> None:
        for field_name in (
            "intent",
            "lifecycle",
            "geo",
            "price_sensitivity",
            "anti_cannibalization_bonus",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"{field_name} must be a number, got {type(value).__name__}"
                )
            value = float(value)
            if value != value:  # NaN
                raise ValueError(f"{field_name} must be finite, got NaN")
            if value < 0.0:
                raise ValueError(
                    f"{field_name} must be non-negative, got {value}"
                )
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True)
class ScoredCandidate:
    """A candidate buyer paired with its computed match score (Req 13.2).

    ``score`` is the final score including any anti-cannibalization bonus.
    ``base_score`` is the weighted-signal score before the bonus, retained so
    callers can see the bias contribution. ``favored`` records whether the
    anti-cannibalization bonus was applied (Requirement 13.4).
    """

    persona: BuyerPersona
    score: float
    base_score: float
    favored: bool


@dataclass(frozen=True)
class MatchResult:
    """The outcome of a :meth:`DemandMatchingEngine.match` call (Req 13.5, 15.4).

    ``ranking`` is the full descending-score ranking produced for the match.
    ``notified`` is exactly the ``min(N, count)`` top candidates that received a
    proactive push, in rank order (Requirement 13.5). ``event`` is the
    ``MATCHED`` :class:`LifecycleEvent` that was emitted identifying the Item
    (Requirement 15.4).
    """

    item_id: str
    ranking: tuple[ScoredCandidate, ...]
    notified: tuple[ScoredCandidate, ...]
    event: LifecycleEvent


# -- match-view derivation constants (G1: GET /items/{id}/matches) -----------

# Intent-tier cutoffs applied to the (clamped, rounded) match score. A score at
# or above HIGH is HIGH; at or above MEDIUM is MEDIUM; otherwise LOW.
INTENT_TIER_HIGH_CUTOFF: float = 0.80
INTENT_TIER_MEDIUM_CUTOFF: float = 0.60

# Default radius (km) used to count nearby matches (match_count_within_5km).
DEFAULT_MATCH_RADIUS_KM: float = 5.0

# Human-readable, PII-free reason text keyed by persona_type. Every persona type
# maps to exactly one reason, guaranteeing at least one reason per match.
PERSONA_TYPE_REASONS: dict[str, str] = {
    "deal_seeker": "deal-seeker",
    "price_balker": "price-sensitive shopper nearby",
    "collector": "collects this category",
    "gifter": "shopping for a gift",
    "browser": "browsing this category",
}

# Reason emitted when the listed Item's category is one of a candidate's
# wishlist/cart interests (Requirement 13.1 signal).
WISHLIST_REASON: str = "wishlisted this product"

# Fallback reason for a persona_type not present in PERSONA_TYPE_REASONS, so the
# "always at least one reason" guarantee holds for any seeded data.
FALLBACK_REASON: str = "category match"


def _clamp01(value: float) -> float:
    """Clamp ``value`` into the inclusive ``[0.0, 1.0]`` range."""

    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


@dataclass(frozen=True)
class BuyerMatch:
    """A single ranked buyer rendered for the matches API (G1).

    ``display_label`` is PII-free ("Buyer N km away"); ``match_score`` is the
    candidate score clamped to ``[0, 1]`` and rounded to two decimals;
    ``match_reasons`` always carries at least one reason; ``intent_tier`` is one
    of ``HIGH``/``MEDIUM``/``LOW`` derived from ``match_score``.
    """

    buyer_id: str
    display_label: str
    distance_km: float
    match_score: float
    match_reasons: tuple[str, ...]
    intent_tier: str


@dataclass(frozen=True)
class MatchView:
    """The full matches result for an Item (G1: GET /items/{id}/matches).

    ``matches`` is the ranked list of :class:`BuyerMatch` (descending score).
    ``match_count_within_5km`` counts matches whose ``distance_km`` is within the
    radius; ``top_reason`` is the first reason of the top match, or ``None`` when
    there are no matches.
    """

    item_id: str
    matches: tuple[BuyerMatch, ...]
    match_count_within_5km: int
    top_reason: str | None


def _common_prefix_len(a: str, b: str) -> int:
    """Number of leading characters ``a`` and ``b`` share."""

    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


class DemandMatchingEngine:
    """Filters, scores, and ranks seeded candidate buyers for a listed Item.

    Collaborators are injected as interfaces (Requirement 13.6: the seeded
    ``BuyerPersonaRepository`` is the only demand source in v1). The engine is
    stateless across calls and may be reused.

    ``weights`` configures the scoring function (Requirement 13.2, 13.4).
    ``geo_radius`` configures the geo radius as the number of geohash
    characters that define the neighborhood: the query geohash is truncated to
    ``geo_radius`` characters before candidate lookup, so a *smaller*
    ``geo_radius`` means a *larger* radius (fewer geohash characters cover a
    bigger area), matching geohash semantics. When ``None`` the radius is
    defined by the full precision of the query geohash passed to :meth:`rank`.

    To use :meth:`match` (the top-N proactive push, Second-Chance PDP shelf
    upsert, and ``MATCHED`` emission of Requirements 13.5 and 15.4), inject the
    ``notifier``, ``shelf``, and ``eventing`` collaborators. ``top_n`` configures
    the default number of buyers to notify per match (Requirement 13.5); it may
    be overridden per call. These four are optional so the filtering/scoring/
    ranking core can be constructed without them.
    """

    def __init__(
        self,
        buyers: BuyerPersonaRepository,
        weights: MatchWeights | None = None,
        geo_radius: int | None = None,
        notifier: BuyerNotifier | None = None,
        shelf: SecondChanceShelf | None = None,
        eventing: EventingService | None = None,
        top_n: int = 5,
    ) -> None:
        if geo_radius is not None:
            if isinstance(geo_radius, bool) or not isinstance(geo_radius, int):
                raise ValueError(
                    f"geo_radius must be an int or None, got "
                    f"{type(geo_radius).__name__}"
                )
            if geo_radius < 0:
                raise ValueError(
                    f"geo_radius must be non-negative, got {geo_radius}"
                )
        self._validate_top_n(top_n)
        self._buyers = buyers
        self._weights = weights or MatchWeights()
        self._geo_radius = geo_radius
        self._notifier = notifier
        self._shelf = shelf
        self._eventing = eventing
        self._top_n = top_n

    @staticmethod
    def _validate_top_n(top_n: int) -> None:
        """Reject a non-positive or non-integer top-N (Requirement 13.5)."""
        if isinstance(top_n, bool) or not isinstance(top_n, int):
            raise ValueError(
                f"top_n must be an int, got {type(top_n).__name__}"
            )
        if top_n < 1:
            raise ValueError(f"top_n must be at least 1, got {top_n}")

    @property
    def top_n(self) -> int:
        """The default number of buyers notified per match (Requirement 13.5)."""

        return self._top_n

    @property
    def weights(self) -> MatchWeights:
        """The scoring weights this engine applies."""

        return self._weights

    # -- filtering (Requirement 13.1) -------------------------------------
    def _neighborhood(self, query_geo: str) -> str:
        """Return the query geohash truncated to the configured radius.

        A smaller ``geo_radius`` yields a shorter prefix and therefore a larger
        geographic neighborhood. When ``geo_radius`` is ``None`` the full query
        geohash is used (the tightest radius).
        """

        if self._geo_radius is None:
            return query_geo
        return query_geo[: self._geo_radius]

    def filter_candidates(self, geo: str, category: str) -> list[BuyerPersona]:
        """Return seeded candidates within the geo radius with a category signal.

        Retrieves the seeded candidate pool from the repository for the
        radius-adjusted neighborhood (Requirement 13.6) and keeps only personas
        that (a) carry a wishlist or cart signal for ``category`` — modeled by
        the persona's ``category_interests`` — and (b) fall within the geo
        radius, i.e. their geohash lies inside the neighborhood prefix
        (Requirement 13.1).
        """

        neighborhood = self._neighborhood(geo)
        pool = self._buyers.candidates(neighborhood, category)
        return [
            persona
            for persona in pool
            if category in persona.category_interests
            and persona.geohash5.startswith(neighborhood)
        ]

    # -- scoring (Requirements 13.2, 13.4) --------------------------------
    def _geo_affinity(self, persona_geo: str, query_geo: str) -> float:
        """Geo proximity signal in [0, 1] from geohash prefix overlap.

        Derives the ``geo`` scoring signal from how closely the persona's
        geohash matches the listed Item's geohash: the shared prefix length
        normalized by the longer of the two geohashes. Identical geohashes score
        1.0; no shared prefix scores 0.0. This gives the weighted score a real
        geo dimension even though the seeded persona carries no standalone geo
        magnitude.
        """

        longest = max(len(persona_geo), len(query_geo))
        if longest == 0:
            return 1.0
        return _common_prefix_len(persona_geo, query_geo) / longest

    def score_candidate(
        self, persona: BuyerPersona, geo: str
    ) -> ScoredCandidate:
        """Compute the weighted score for a single candidate (Req 13.2, 13.4).

        The base score is a weighted sum of the persona's intent, lifecycle,
        price-sensitivity, and a derived geo-affinity signal. Favored personas
        (deal-seeker / price-balker) receive the additive anti-cannibalization
        bonus on top (Requirement 13.4).
        """

        w = self._weights
        geo_signal = self._geo_affinity(persona.geohash5, geo)
        base = (
            w.intent * persona.intent
            + w.lifecycle * persona.lifecycle
            + w.geo * geo_signal
            + w.price_sensitivity * persona.price_sensitivity
        )
        favored = persona.persona_type in FAVORED_PERSONA_TYPES
        bonus = w.anti_cannibalization_bonus if favored else 0.0
        return ScoredCandidate(
            persona=persona,
            score=base + bonus,
            base_score=base,
            favored=favored,
        )

    # -- ranking (Requirements 13.3, 13.4) --------------------------------
    def rank(self, geo: str, category: str) -> list[ScoredCandidate]:
        """Filter, score, and rank candidate buyers for a listed Item.

        Returns the full ranked list of scored candidates in descending score
        order (Requirement 13.3). The ranking is a permutation of the filtered
        candidates: ties preserve the repository's input order (a stable sort),
        and the anti-cannibalization bonus guarantees that, all signals equal, a
        favored persona ranks no lower than a non-favored one (Requirement
        13.4).

        A later task slices this list to the top-N for proactive push, PDP shelf
        placement, and ``MATCHED`` emission (Requirements 13.5, 15.4).
        """

        candidates = self.filter_candidates(geo, category)
        scored = [self.score_candidate(persona, geo) for persona in candidates]
        # sorted() is stable, so candidates with equal scores keep their
        # repository order, making the result a deterministic permutation.
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored

    # -- match view for the matches API (G1) ------------------------------
    def matches_for(
        self,
        item_id: str,
        geo: str,
        category: str,
        radius_km: float = DEFAULT_MATCH_RADIUS_KM,
    ) -> MatchView:
        """Build the ranked buyer-match view for ``item_id`` (G1).

        Ranks candidate buyers for ``(geo, category)`` via :meth:`rank`, then
        maps each :class:`ScoredCandidate` to a PII-free :class:`BuyerMatch`:

        * ``distance_km`` is the haversine distance between ``geo`` and the
          persona's geohash when ``geo`` is non-empty, else a deterministic
          seeded distance derived from a stable hash of the buyer id (so an
          unlisted Item with no location still yields a stable figure);
        * ``match_score`` is the candidate score clamped to ``[0, 1]`` and
          rounded to two decimals;
        * ``match_reasons`` derives from the persona's category interest and
          persona type (always at least one reason);
        * ``intent_tier`` buckets ``match_score`` into HIGH/MEDIUM/LOW.

        ``match_count_within_5km`` counts matches within ``radius_km`` and
        ``top_reason`` is the first reason of the top match (or ``None`` when no
        candidates match). Callers (the API layer) attach ``generated_at``.
        """

        ranking = self.rank(geo, category)
        matches: list[BuyerMatch] = []
        for candidate in ranking:
            persona = candidate.persona
            distance = self._distance_for(geo, persona)
            score = round(_clamp01(candidate.score), 2)
            reasons = self._match_reasons(persona, category)
            matches.append(
                BuyerMatch(
                    buyer_id=persona.buyer_id,
                    display_label=f"Buyer {round(distance)} km away",
                    distance_km=distance,
                    match_score=score,
                    match_reasons=reasons,
                    intent_tier=self._intent_tier(score),
                )
            )

        within = sum(1 for m in matches if m.distance_km <= radius_km)
        top_reason = matches[0].match_reasons[0] if matches else None
        return MatchView(
            item_id=item_id,
            matches=tuple(matches),
            match_count_within_5km=within,
            top_reason=top_reason,
        )

    @staticmethod
    def _distance_for(geo: str, persona: BuyerPersona) -> float:
        """Distance (km) for a candidate: haversine when geo is known, else seeded."""

        if geo:
            return geohash_distance_km(geo, persona.geohash5)
        return seeded_distance_km(persona.buyer_id)

    @staticmethod
    def _intent_tier(match_score: float) -> str:
        """Bucket a match score into HIGH/MEDIUM/LOW (G1)."""

        if match_score >= INTENT_TIER_HIGH_CUTOFF:
            return "HIGH"
        if match_score >= INTENT_TIER_MEDIUM_CUTOFF:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _match_reasons(persona: BuyerPersona, category: str) -> tuple[str, ...]:
        """Derive PII-free match reasons from category interest + persona type.

        The category-interest signal (if present) leads, followed by the
        persona-type reason. At least one reason is always produced.
        """

        reasons: list[str] = []
        if category in persona.category_interests:
            reasons.append(WISHLIST_REASON)
        reasons.append(
            PERSONA_TYPE_REASONS.get(persona.persona_type, FALLBACK_REASON)
        )
        return tuple(reasons)

    # -- top-N push, placement, emission (Requirements 13.5, 15.4) --------
    def match(
        self,
        item_id: str,
        geo: str,
        category: str,
        top_n: int | None = None,
    ) -> MatchResult:
        """Rank, push to the top-N buyers, place on the shelf, and emit MATCHED.

        Produces the ranking for ``(geo, category)`` (Requirements 13.1-13.4),
        then for the listed ``item_id``:

        * notifies **exactly** the top ``min(N, count)`` ranked buyers through
          the injected :class:`BuyerNotifier`, where ``count`` is the number of
          ranked candidates and ``N`` is ``top_n`` (defaulting to the engine's
          configured ``top_n``). When ``N >= count`` every ranked buyer is
          notified and no more; when there are no candidates none are notified
          (Requirement 13.5);
        * upserts ``item_id`` onto the Second-Chance PDP shelf through the
          injected :class:`SecondChanceShelf` (idempotent placement,
          Requirement 13.5);
        * emits a ``MATCHED`` event identifying the Item through the injected
          :class:`EventingService` (Requirement 15.4).

        The shelf upsert and ``MATCHED`` emission happen for any ranking,
        including an empty one, so a listed Item always reaches its placement
        surface. Returns a :class:`MatchResult` capturing the full ranking, the
        notified slice, and the emitted event.

        Requires ``notifier``, ``shelf``, and ``eventing`` to have been injected
        at construction; raises :class:`RuntimeError` otherwise.
        """

        self._require_match_collaborators()
        effective_n = self._top_n if top_n is None else top_n
        self._validate_top_n(effective_n)

        ranking = self.rank(geo, category)
        # min(N, count): never notify more buyers than exist, never more than N.
        cutoff = min(effective_n, len(ranking))
        notified = tuple(ranking[:cutoff])

        for candidate in notified:
            self._notifier.notify(candidate.persona.buyer_id, item_id)

        self._shelf.upsert(item_id)
        event = self._eventing.emit_matched(item_id)

        return MatchResult(
            item_id=item_id,
            ranking=tuple(ranking),
            notified=notified,
            event=event,
        )

    def _require_match_collaborators(self) -> None:
        """Ensure the push/placement/emission seams were injected (13.5, 15.4)."""
        missing = [
            name
            for name, value in (
                ("notifier", self._notifier),
                ("shelf", self._shelf),
                ("eventing", self._eventing),
            )
            if value is None
        ]
        if missing:
            raise RuntimeError(
                "match() requires the injected collaborator(s): "
                f"{', '.join(missing)}"
            )
