"""Property-based test for demand candidate filtering.

# Feature: rebridge-backend, Property 21: Demand candidate filtering

Property 21 (design.md): *For any* set of seeded buyer personas and a listed
Item, every returned candidate SHALL match the Item's category, fall within the
geo radius, and have a wishlist or cart signal for the category.

**Validates: Requirements 13.1**

The Demand_Matching_Engine models the wishlist/cart signal as the presence of
the listed category in a persona's ``category_interests``, and the geo radius as
the requested geohash truncated to the configured ``geo_radius`` (the
neighborhood prefix). ``DemandMatchingEngine.filter_candidates`` must therefore
return *exactly* the personas in the seeded pool that both carry the category
signal and whose geohash lies inside the neighborhood prefix.

This test drives the real engine over arbitrary persona pools (against the
in-memory :class:`FakeBuyerPersonaRepository`, no AWS, no mocks) and asserts two
complementary halves of the filter contract:

* **Soundness** - every returned candidate matches the category and falls within
  the geo neighborhood prefix.
* **Completeness** - no qualifying persona in the pool is omitted: the returned
  list equals exactly the filtered subset, in repository order.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import BuyerPersona

from rebridge_service.demand_matching_engine import DemandMatchingEngine

from .fakes import FakeBuyerPersonaRepository

# A small geohash alphabet so generated persona geohashes and query geohashes
# share prefixes often enough to exercise both in-radius and out-of-radius
# personas (a wide alphabet would almost never collide).
_GEO_ALPHABET = "0123bc"

# A small category universe so a persona's interests overlap the queried
# category often enough to produce both matching and non-matching candidates.
_CATEGORIES = ["electronics", "books", "toys", "home"]

_geohash = st.text(alphabet=_GEO_ALPHABET, min_size=1, max_size=5)

_persona = st.builds(
    BuyerPersona,
    buyer_id=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
        min_size=1,
        max_size=10,
    ),
    geohash5=_geohash,
    persona_type=st.sampled_from(
        ["browser", "deal_seeker", "price_balker", "loyalist"]
    ),
    category_interests=st.lists(
        st.sampled_from(_CATEGORIES), min_size=0, max_size=4, unique=True
    ),
    intent=st.floats(min_value=0.0, max_value=1.0),
    lifecycle=st.floats(min_value=0.0, max_value=1.0),
    price_sensitivity=st.floats(min_value=0.0, max_value=1.0),
)

# Distinct buyer ids so the pool holds one persona per id and the returned list
# is an unambiguous subset of the input pool.
_persona_pool = st.lists(
    _persona, max_size=30, unique_by=lambda p: p.buyer_id
)


@settings(max_examples=200)
@given(
    personas=_persona_pool,
    query_geo=_geohash,
    category=st.sampled_from(_CATEGORIES),
    geo_radius=st.one_of(st.none(), st.integers(min_value=0, max_value=6)),
)
def test_filter_candidates_is_sound_and_complete(
    personas: list[BuyerPersona],
    query_geo: str,
    category: str,
    geo_radius: int | None,
) -> None:
    """filter_candidates returns exactly the category + geo-neighborhood matches.

    Validates: Requirements 13.1
    """

    repo = FakeBuyerPersonaRepository(personas=personas)
    engine = DemandMatchingEngine(repo, geo_radius=geo_radius)

    # The neighborhood prefix the engine searches within: the query geohash
    # truncated to the configured radius (full geohash when radius is None).
    neighborhood = query_geo if geo_radius is None else query_geo[:geo_radius]

    result = engine.filter_candidates(geo=query_geo, category=category)

    # -- Soundness: every returned candidate qualifies on both axes ----------
    for candidate in result:
        assert category in candidate.category_interests, (
            f"{candidate.buyer_id} returned without the category signal"
        )
        assert candidate.geohash5.startswith(neighborhood), (
            f"{candidate.buyer_id} returned outside the geo neighborhood "
            f"{neighborhood!r}"
        )

    # -- Completeness: the result equals exactly the qualifying subset -------
    expected = [
        p
        for p in personas
        if category in p.category_interests
        and p.geohash5.startswith(neighborhood)
    ]
    assert [c.buyer_id for c in result] == [p.buyer_id for p in expected], (
        "filter_candidates must return exactly the qualifying personas, in "
        "repository order, omitting none and inventing none"
    )
