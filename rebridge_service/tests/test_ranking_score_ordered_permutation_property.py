"""Property-based test for score-ordered ranking with anti-cannibalization bias.

# Feature: rebridge-backend, Property 22: Ranking is a score-ordered permutation with anti-cannibalization bias

Property 22 (design.md): *For any* set of scored candidate buyers, the ranking
SHALL be a permutation of the input ordered non-increasing by score, where the
score is a weighted function of intent, lifecycle, geo, and price-sensitivity,
and where between two candidates equal on all other factors a deal-seeker or
price-balker persona SHALL rank no lower.

**Validates: Requirements 13.2, 13.3, 13.4**

This test generates arbitrary seeded persona pools (varied geohash, persona
type, category interests, and signal magnitudes) together with arbitrary
scoring weights, then asserts that ``DemandMatchingEngine.rank``:

1. returns a permutation of the engine's filtered candidate set (no loss, no
   duplicates, nothing invented);
2. produces scores in non-increasing order (Requirement 13.3);
3. assigns each candidate a score equal to the weighted sum of its signals plus
   the anti-cannibalization bonus iff the persona is favored (Requirements 13.2,
   13.4);
4. never ranks a non-favored persona above a favored persona that is equal on
   every base signal — i.e. all else equal, a favored persona's score is no
   lower (Requirement 13.4).

It runs against the in-memory ``FakeBuyerPersonaRepository`` (no AWS, no mocks).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import BuyerPersona

from rebridge_service.demand_matching_engine import (
    FAVORED_PERSONA_TYPES,
    DemandMatchingEngine,
    MatchWeights,
)

from .fakes import FakeBuyerPersonaRepository

# Small, overlap-prone alphabets so generated geohashes and categories actually
# collide often enough to exercise non-trivial filtered pools and geo affinity.
_GEO_ALPHABET = "012"
_CATEGORIES = ["electronics", "books", "toys"]
_PERSONA_TYPES = ["browser", "collector", "gifter", "deal_seeker", "price_balker"]

_geohash = st.text(alphabet=_GEO_ALPHABET, min_size=1, max_size=5)
_signal = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


def _persona_strategy(buyer_id: str) -> st.SearchStrategy[BuyerPersona]:
    return st.builds(
        BuyerPersona,
        buyer_id=st.just(buyer_id),
        geohash5=_geohash,
        persona_type=st.sampled_from(_PERSONA_TYPES),
        category_interests=st.lists(
            st.sampled_from(_CATEGORIES), min_size=0, max_size=3, unique=True
        ),
        intent=_signal,
        lifecycle=_signal,
        price_sensitivity=_signal,
    )


@st.composite
def _persona_pool(draw: st.DrawFn) -> list[BuyerPersona]:
    # Distinct buyer ids so the filtered result is a true set permutation.
    ids = draw(
        st.lists(
            st.text(alphabet="abcdefghij", min_size=1, max_size=6),
            min_size=0,
            max_size=25,
            unique=True,
        )
    )
    return [draw(_persona_strategy(buyer_id)) for buyer_id in ids]


_weights = st.builds(
    MatchWeights,
    intent=_signal,
    lifecycle=_signal,
    geo=_signal,
    price_sensitivity=_signal,
    anti_cannibalization_bonus=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
)


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def _geo_affinity(persona_geo: str, query_geo: str) -> float:
    """Mirror of the engine's geo-affinity signal for score recomputation."""

    longest = max(len(persona_geo), len(query_geo))
    if longest == 0:
        return 1.0
    return _common_prefix_len(persona_geo, query_geo) / longest


@settings(max_examples=200)
@given(
    personas=_persona_pool(),
    weights=_weights,
    geo=_geohash,
    category=st.sampled_from(_CATEGORIES),
    geo_radius=st.sampled_from([None, 1, 2, 3]),
)
def test_rank_is_score_ordered_permutation_with_bias(
    personas, weights, geo, category, geo_radius
):
    repo = FakeBuyerPersonaRepository(personas=personas)
    engine = DemandMatchingEngine(repo, weights=weights, geo_radius=geo_radius)

    filtered = engine.filter_candidates(geo, category)
    ranked = engine.rank(geo, category)

    # 1) Permutation of the filtered candidate set: no loss, no dupes, nothing
    #    invented (Requirements 13.2/13.3 operate over exactly the candidates).
    ranked_ids = sorted(c.persona.buyer_id for c in ranked)
    filtered_ids = sorted(p.buyer_id for p in filtered)
    assert ranked_ids == filtered_ids

    # 2) Scores are non-increasing (Requirement 13.3: descending order).
    scores = [c.score for c in ranked]
    assert scores == sorted(scores, reverse=True)

    # 3) Each score is the weighted sum of signals plus the bonus iff favored
    #    (Requirements 13.2 + 13.4).
    for c in ranked:
        p = c.persona
        expected_base = (
            weights.intent * p.intent
            + weights.lifecycle * p.lifecycle
            + weights.geo * _geo_affinity(p.geohash5, geo)
            + weights.price_sensitivity * p.price_sensitivity
        )
        is_favored = p.persona_type in FAVORED_PERSONA_TYPES
        assert c.favored is is_favored
        assert c.base_score == _approx(expected_base)
        expected_score = expected_base + (
            weights.anti_cannibalization_bonus if is_favored else 0.0
        )
        assert c.score == _approx(expected_score)

    # 4) All else equal, a favored persona ranks no lower: for any favored and
    #    non-favored pair with the same base score, the favored persona's score
    #    is >= the non-favored one's (the additive non-negative bonus can only
    #    lift it), so it never ranks below (Requirement 13.4).
    favored = [c for c in ranked if c.favored]
    non_favored = [c for c in ranked if not c.favored]
    for f in favored:
        for n in non_favored:
            if f.base_score == _approx(n.base_score):
                assert f.score >= n.score


def _approx(value: float):
    from pytest import approx

    return approx(value, rel=1e-9, abs=1e-12)
