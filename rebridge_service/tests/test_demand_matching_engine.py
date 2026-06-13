"""Unit tests for the Demand_Matching_Engine filtering, scoring, and ranking.

Covers the filtering+scoring+ranking core of Requirement 13:
- 13.1 candidate filtering by geo radius + category + wishlist/cart signal
- 13.2 weighted score over (intent, lifecycle, geo, price_sensitivity)
- 13.3 descending score-ordered ranking (a permutation of the candidates)
- 13.4 anti-cannibalization bias favoring deal-seeker / price-balker personas
- 13.6 operates over the seeded BuyerPersonaRepository

These exercise real business logic against the in-memory
FakeBuyerPersonaRepository (no AWS, no mocks).
"""

from __future__ import annotations

import pytest

from rebridge_data.models import BuyerPersona

from rebridge_service.demand_matching_engine import (
    FAVORED_PERSONA_TYPES,
    DemandMatchingEngine,
    MatchWeights,
    ScoredCandidate,
)

from .fakes import FakeBuyerPersonaRepository


def _persona(
    buyer_id: str,
    *,
    geohash5: str = "9q8yy",
    persona_type: str = "browser",
    category_interests: list[str] | None = None,
    intent: float = 0.0,
    lifecycle: float = 0.0,
    price_sensitivity: float = 0.0,
) -> BuyerPersona:
    return BuyerPersona(
        buyer_id=buyer_id,
        geohash5=geohash5,
        persona_type=persona_type,
        category_interests=(
            category_interests if category_interests is not None else ["electronics"]
        ),
        intent=intent,
        lifecycle=lifecycle,
        price_sensitivity=price_sensitivity,
    )


# --------------------------------------------------------------------------
# Filtering (Requirement 13.1)
# --------------------------------------------------------------------------
def test_filter_keeps_only_category_and_geo_matches():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("in_geo_in_cat", geohash5="9q8yy", category_interests=["electronics"]),
            _persona("other_cat", geohash5="9q8yy", category_interests=["toys"]),
            _persona("out_of_geo", geohash5="dr5ru", category_interests=["electronics"]),
        ]
    )
    engine = DemandMatchingEngine(repo)

    candidates = engine.filter_candidates(geo="9q8yy", category="electronics")

    assert [c.buyer_id for c in candidates] == ["in_geo_in_cat"]


def test_filter_uses_category_interest_as_wishlist_cart_signal():
    # A persona with the category in its interests carries the wishlist/cart
    # signal; one without it is excluded even when geo matches.
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("has_signal", category_interests=["electronics", "books"]),
            _persona("no_signal", category_interests=["books"]),
        ]
    )
    engine = DemandMatchingEngine(repo)

    candidates = engine.filter_candidates(geo="9q8yy", category="electronics")

    assert {c.buyer_id for c in candidates} == {"has_signal"}


def test_coarser_query_geo_widens_the_radius():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("a", geohash5="9q8yy"),
            _persona("b", geohash5="9q8yz"),
            _persona("c", geohash5="9q8zz"),
        ]
    )
    engine = DemandMatchingEngine(repo)

    # 3-char query geohash -> larger radius -> all three 9q8* match.
    wide = engine.filter_candidates(geo="9q8", category="electronics")
    assert {c.buyer_id for c in wide} == {"a", "b", "c"}

    # full 5-char query geohash -> tightest radius -> only the exact match.
    tight = engine.filter_candidates(geo="9q8yy", category="electronics")
    assert {c.buyer_id for c in tight} == {"a"}


def test_explicit_geo_radius_widens_the_neighborhood():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("a", geohash5="9q8yy"),
            _persona("b", geohash5="9q8yz"),
            _persona("c", geohash5="9q900"),
        ]
    )
    # radius of 3 geohash chars truncates the query "9q8yy" -> "9q8", widening
    # the neighborhood to every 9q8* buyer (a and b), excluding 9q9* (c).
    engine = DemandMatchingEngine(repo, geo_radius=3)

    candidates = engine.filter_candidates(geo="9q8yy", category="electronics")

    assert {c.buyer_id for c in candidates} == {"a", "b"}


# --------------------------------------------------------------------------
# Scoring (Requirement 13.2)
# --------------------------------------------------------------------------
def test_score_is_weighted_sum_of_signals_plus_geo_affinity():
    repo = FakeBuyerPersonaRepository()
    weights = MatchWeights(
        intent=0.40,
        lifecycle=0.20,
        geo=0.20,
        price_sensitivity=0.20,
        anti_cannibalization_bonus=0.0,
    )
    engine = DemandMatchingEngine(repo, weights=weights)
    persona = _persona(
        "p",
        geohash5="9q8yy",
        persona_type="browser",
        intent=1.0,
        lifecycle=0.5,
        price_sensitivity=0.25,
    )

    scored = engine.score_candidate(persona, geo="9q8yy")

    # geo affinity is 1.0 for an exact geohash match.
    expected = 0.40 * 1.0 + 0.20 * 0.5 + 0.20 * 1.0 + 0.20 * 0.25
    assert scored.base_score == pytest.approx(expected)
    assert scored.score == pytest.approx(expected)  # no bonus for a browser
    assert scored.favored is False


def test_geo_affinity_decreases_with_geohash_distance():
    repo = FakeBuyerPersonaRepository()
    weights = MatchWeights(
        intent=0.0,
        lifecycle=0.0,
        geo=1.0,
        price_sensitivity=0.0,
        anti_cannibalization_bonus=0.0,
    )
    engine = DemandMatchingEngine(repo, weights=weights)

    exact = engine.score_candidate(_persona("a", geohash5="9q8yy"), geo="9q8yy")
    near = engine.score_candidate(_persona("b", geohash5="9q8yz"), geo="9q8yy")
    far = engine.score_candidate(_persona("c", geohash5="dr5ru"), geo="9q8yy")

    assert exact.score == pytest.approx(1.0)
    assert exact.score > near.score > far.score
    assert far.score == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Ranking (Requirement 13.3)
# --------------------------------------------------------------------------
def test_rank_orders_candidates_by_descending_score():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("low", intent=0.1),
            _persona("high", intent=0.9),
            _persona("mid", intent=0.5),
        ]
    )
    engine = DemandMatchingEngine(repo)

    ranked = engine.rank(geo="9q8yy", category="electronics")

    assert [c.persona.buyer_id for c in ranked] == ["high", "mid", "low"]
    scores = [c.score for c in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_is_a_permutation_of_filtered_candidates():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("a", intent=0.2),
            _persona("b", intent=0.8),
            _persona("c", geohash5="dr5ru", intent=0.9),  # filtered out by geo
            _persona("d", intent=0.5),
        ]
    )
    engine = DemandMatchingEngine(repo)

    ranked = engine.rank(geo="9q8yy", category="electronics")

    filtered_ids = {c.persona.buyer_id for c in ranked}
    assert filtered_ids == {"a", "b", "d"}  # c excluded, none invented


def test_rank_is_stable_for_tied_scores():
    # Identical signals -> identical scores -> repository input order preserved.
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("first", intent=0.5),
            _persona("second", intent=0.5),
            _persona("third", intent=0.5),
        ]
    )
    engine = DemandMatchingEngine(repo)

    ranked = engine.rank(geo="9q8yy", category="electronics")

    assert [c.persona.buyer_id for c in ranked] == ["first", "second", "third"]


# --------------------------------------------------------------------------
# Anti-cannibalization bias (Requirement 13.4)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("favored_type", sorted(FAVORED_PERSONA_TYPES))
def test_favored_persona_outranks_equal_non_favored(favored_type):
    # Two candidates equal on every signal; the favored one must rank no lower
    # (here: strictly higher, given a positive bonus).
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("plain", persona_type="browser", intent=0.5),
            _persona(favored_type, persona_type=favored_type, intent=0.5),
        ]
    )
    engine = DemandMatchingEngine(repo)

    ranked = engine.rank(geo="9q8yy", category="electronics")

    assert ranked[0].persona.buyer_id == favored_type
    assert ranked[0].favored is True
    assert ranked[0].score > ranked[1].score


def test_bonus_does_not_invert_a_much_stronger_base_score():
    # The bias favors but does not blindly override: a far stronger non-favored
    # buyer still outranks a weak favored one.
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("strong_browser", persona_type="browser", intent=1.0),
            _persona("weak_dealseeker", persona_type="deal_seeker", intent=0.0),
        ]
    )
    engine = DemandMatchingEngine(repo)

    ranked = engine.rank(geo="9q8yy", category="electronics")

    assert ranked[0].persona.buyer_id == "strong_browser"


def test_zero_bonus_disables_the_bias():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("browser", persona_type="browser", intent=0.5),
            _persona("dealer", persona_type="deal_seeker", intent=0.5),
        ]
    )
    weights = MatchWeights(anti_cannibalization_bonus=0.0)
    engine = DemandMatchingEngine(repo, weights=weights)

    ranked = engine.rank(geo="9q8yy", category="electronics")

    # Equal base scores, no bonus -> tie -> stable input order.
    assert [c.persona.buyer_id for c in ranked] == ["browser", "dealer"]
    assert ranked[0].score == pytest.approx(ranked[1].score)


# --------------------------------------------------------------------------
# Config validation / edge cases
# --------------------------------------------------------------------------
def test_rank_on_empty_repository_returns_empty():
    engine = DemandMatchingEngine(FakeBuyerPersonaRepository())
    assert engine.rank(geo="9q8yy", category="electronics") == []


def test_default_weights_sum_to_one_and_have_a_positive_bonus():
    w = MatchWeights()
    assert w.intent + w.lifecycle + w.geo + w.price_sensitivity == pytest.approx(1.0)
    assert w.anti_cannibalization_bonus > 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"intent": -0.1},
        {"anti_cannibalization_bonus": -0.5},
        {"geo": float("nan")},
        {"lifecycle": True},
    ],
)
def test_invalid_weights_rejected(kwargs):
    with pytest.raises(ValueError):
        MatchWeights(**kwargs)


@pytest.mark.parametrize("bad_radius", [-1, True, 1.5])
def test_invalid_geo_radius_rejected(bad_radius):
    with pytest.raises(ValueError):
        DemandMatchingEngine(FakeBuyerPersonaRepository(), geo_radius=bad_radius)


def test_scored_candidate_is_immutable():
    scored = ScoredCandidate(
        persona=_persona("p"), score=1.0, base_score=1.0, favored=False
    )
    with pytest.raises(Exception):
        scored.score = 2.0  # type: ignore[misc]
