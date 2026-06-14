"""Unit tests for DemandMatchingEngine.matches_for (G1 match view).

Covers the match-view derivation layered on top of the ranking core:
- ranking maps to PII-free BuyerMatch rows (display label, distance, reasons);
- intent_tier buckets the clamped match_score (HIGH/MEDIUM/LOW);
- distance_km is the haversine when geo is known, else a deterministic seeded
  distance derived from the buyer id;
- match_count_within_5km counts matches within the radius;
- top_reason is the first reason of the top match, or None when empty;
- match_reasons always carry at least one reason and lead with the wishlist
  signal when the item's category is a persona interest.
"""

from __future__ import annotations

from rebridge_data.geohash import geohash_distance_km, seeded_distance_km
from rebridge_data.models import BuyerPersona

from rebridge_service.demand_matching_engine import (
    DemandMatchingEngine,
    MatchView,
)

from .fakes import FakeBuyerPersonaRepository


def _persona(
    buyer_id: str,
    *,
    geohash5: str = "9q8yy",
    persona_type: str = "browser",
    category_interests: list[str] | None = None,
    intent: float = 0.5,
    lifecycle: float = 0.5,
    price_sensitivity: float = 0.5,
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


def test_matches_for_returns_ranked_pii_free_rows():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona(
                "buy_hi",
                persona_type="deal_seeker",
                category_interests=["electronics"],
                intent=0.95,
                lifecycle=0.9,
                price_sensitivity=0.95,
            ),
            _persona(
                "buy_lo",
                persona_type="browser",
                category_interests=["electronics"],
                intent=0.1,
                lifecycle=0.1,
                price_sensitivity=0.1,
            ),
        ]
    )
    engine = DemandMatchingEngine(repo)

    view = engine.matches_for("itm_1", geo="9q8yy", category="electronics")

    assert isinstance(view, MatchView)
    assert view.item_id == "itm_1"
    assert [m.buyer_id for m in view.matches] == ["buy_hi", "buy_lo"]
    top = view.matches[0]
    # PII-free display label of the form "Buyer N km away".
    assert top.display_label == f"Buyer {round(top.distance_km)} km away"
    # Score is clamped to [0, 1] and rounded to two decimals.
    assert 0.0 <= top.match_score <= 1.0
    assert round(top.match_score, 2) == top.match_score
    # Same geohash -> zero distance.
    assert top.distance_km == 0.0


def test_intent_tier_from_score():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona(
                "high",
                persona_type="deal_seeker",
                intent=1.0,
                lifecycle=1.0,
                price_sensitivity=1.0,
            ),
            _persona(
                "medium",
                persona_type="browser",
                intent=0.7,
                lifecycle=0.7,
                price_sensitivity=0.7,
            ),
            _persona(
                "low",
                persona_type="browser",
                intent=0.1,
                lifecycle=0.1,
                price_sensitivity=0.1,
            ),
        ]
    )
    engine = DemandMatchingEngine(repo)

    tiers = {
        m.buyer_id: m.intent_tier
        for m in engine.matches_for("itm", geo="9q8yy", category="electronics").matches
    }
    assert tiers["high"] == "HIGH"
    assert tiers["medium"] == "MEDIUM"
    assert tiers["low"] == "LOW"


def test_distance_uses_haversine_when_geo_known():
    repo = FakeBuyerPersonaRepository(
        personas=[_persona("far", geohash5="9q5ct", category_interests=["electronics"])]
    )
    # geo_radius=2 widens the neighborhood to the "9q" prefix so a buyer in a
    # different sub-cell is still a candidate, exercising the haversine path.
    engine = DemandMatchingEngine(repo, geo_radius=2)

    view = engine.matches_for("itm", geo="9q8yy", category="electronics")
    assert view.matches[0].distance_km == geohash_distance_km("9q8yy", "9q5ct")


def test_distance_falls_back_to_seeded_when_geo_empty():
    repo = FakeBuyerPersonaRepository(
        personas=[_persona("buy_seed", category_interests=["electronics"])]
    )
    engine = DemandMatchingEngine(repo)

    view = engine.matches_for("itm", geo="", category="electronics")
    assert view.matches[0].distance_km == seeded_distance_km("buy_seed")


def test_match_count_within_5km_counts_nearby():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona("near", geohash5="9q8yy", category_interests=["electronics"]),
            _persona("far", geohash5="9q5ct", category_interests=["electronics"]),
        ]
    )
    # Widen to the "9q" prefix so both buyers are candidates.
    engine = DemandMatchingEngine(repo, geo_radius=2)

    view = engine.matches_for("itm", geo="9q8yy", category="electronics")
    expected = sum(1 for m in view.matches if m.distance_km <= 5.0)
    assert view.match_count_within_5km == expected
    # near is 0 km (same cell); far is >5 km away, so exactly one within 5 km.
    assert len(view.matches) == 2
    assert view.match_count_within_5km == 1


def test_top_reason_and_reasons_lead_with_wishlist():
    repo = FakeBuyerPersonaRepository(
        personas=[
            _persona(
                "buy_wish",
                persona_type="deal_seeker",
                category_interests=["electronics"],
                intent=0.9,
                lifecycle=0.9,
                price_sensitivity=0.9,
            )
        ]
    )
    engine = DemandMatchingEngine(repo)

    view = engine.matches_for("itm", geo="9q8yy", category="electronics")
    top = view.matches[0]
    assert top.match_reasons[0] == "wishlisted this product"
    assert "deal-seeker" in top.match_reasons
    assert view.top_reason == "wishlisted this product"


def test_reasons_always_at_least_one_without_wishlist():
    # Category not in interests for the engine query would filter the persona
    # out, so to exercise "no wishlist reason" we rely on persona_type mapping
    # via a category the persona holds but a different reason path. Here the
    # persona interest matches the query, but we assert the persona-type reason
    # is always present as a fallback guarantee.
    repo = FakeBuyerPersonaRepository(
        personas=[_persona("b", persona_type="gifter", category_interests=["toys"])]
    )
    engine = DemandMatchingEngine(repo)
    view = engine.matches_for("itm", geo="9q8yy", category="toys")
    assert len(view.matches[0].match_reasons) >= 1
    assert "shopping for a gift" in view.matches[0].match_reasons


def test_empty_when_no_candidates():
    repo = FakeBuyerPersonaRepository(personas=[])
    engine = DemandMatchingEngine(repo)

    view = engine.matches_for("itm", geo="9q8yy", category="electronics")
    assert view.matches == ()
    assert view.match_count_within_5km == 0
    assert view.top_reason is None
