"""Unit and property tests for :class:`SeededBuyerPersonaRepository`.

The repository is the only demand source in v1 (Requirements 13.6, 18.2). It
loads a synthetic JSON persona seed shipped as package data and answers
``candidates(geo, category)`` by filtering that pool to personas whose geohash5
starts with the queried geo prefix and whose category_interests include the
queried category.

These tests cover:
* loading the packaged seed (shape, scope, anti-cannibalization persona types),
* constructor injection of an explicit persona list (overriding the seed),
* candidates() filtering by geo prefix + category, case-insensitivity, and
* a property that every returned candidate genuinely matches the filter.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from rebridge_data import SeededBuyerPersonaRepository
from rebridge_data.models import BuyerPersona

# Categories shared with the price-band seed (design.md 10.1 / 13.6).
_SEED_CATEGORIES = {"electronics", "apparel", "home", "toys", "books"}


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
            ["electronics"] if category_interests is None else category_interests
        ),
        intent=intent,
        lifecycle=lifecycle,
        price_sensitivity=price_sensitivity,
    )


# -- seed loading ---------------------------------------------------------


def test_loads_packaged_seed_with_personas():
    repo = SeededBuyerPersonaRepository()
    personas = repo.personas

    assert len(personas) >= 20
    assert all(isinstance(p, BuyerPersona) for p in personas)
    # buyer_ids are unique opaque tokens.
    assert len({p.buyer_id for p in personas}) == len(personas)


def test_seed_categories_are_within_price_band_categories():
    repo = SeededBuyerPersonaRepository()
    seen = {c for p in repo.personas for c in p.category_interests}
    assert seen <= _SEED_CATEGORIES
    # Every price-band category is represented by at least one persona.
    assert seen == _SEED_CATEGORIES


def test_seed_spans_several_neighborhoods():
    repo = SeededBuyerPersonaRepository()
    neighborhoods = {p.geohash5 for p in repo.personas}
    assert len(neighborhoods) >= 3
    # geohash5 values are 5-character geohash prefixes.
    assert all(len(g) == 5 for g in neighborhoods)


def test_seed_includes_anti_cannibalization_persona_types():
    repo = SeededBuyerPersonaRepository()
    types = {p.persona_type for p in repo.personas}
    assert "deal_seeker" in types
    assert "price_balker" in types


def test_signals_are_in_unit_interval():
    repo = SeededBuyerPersonaRepository()
    for p in repo.personas:
        assert 0.0 <= p.intent <= 1.0
        assert 0.0 <= p.lifecycle <= 1.0
        assert 0.0 <= p.price_sensitivity <= 1.0


def test_seed_supports_candidate_lookup():
    repo = SeededBuyerPersonaRepository()
    # The packaged seed places electronics buyers in the 9q8yy neighborhood.
    found = repo.candidates("9q8yy", "electronics")
    assert found
    assert all(c.geohash5.startswith("9q8yy") for c in found)
    assert all("electronics" in c.category_interests for c in found)


# -- constructor injection (override the seed) ----------------------------


def test_injected_personas_override_packaged_seed():
    injected = [_persona("only-1"), _persona("only-2")]
    repo = SeededBuyerPersonaRepository(personas=injected)
    assert [p.buyer_id for p in repo.personas] == ["only-1", "only-2"]


# -- candidates() filtering ----------------------------------------------


def test_candidates_filters_by_geo_and_category():
    repo = SeededBuyerPersonaRepository(
        personas=[
            _persona("in_geo_in_cat", geohash5="9q8yy", category_interests=["electronics"]),
            _persona("in_geo_other_cat", geohash5="9q8yy", category_interests=["toys"]),
            _persona("out_of_geo", geohash5="dr5ru", category_interests=["electronics"]),
        ]
    )

    found = repo.candidates("9q8yy", "electronics")

    assert [c.buyer_id for c in found] == ["in_geo_in_cat"]


def test_candidates_geo_prefix_widens_neighborhood():
    repo = SeededBuyerPersonaRepository(
        personas=[
            _persona("a", geohash5="9q8yy", category_interests=["home"]),
            _persona("b", geohash5="9q8yz", category_interests=["home"]),
            _persona("c", geohash5="9q900", category_interests=["home"]),
        ]
    )

    # Full 5-char geo -> exact match only.
    assert {c.buyer_id for c in repo.candidates("9q8yy", "home")} == {"a"}
    # 3-char prefix widens to every 9q8* persona.
    assert {c.buyer_id for c in repo.candidates("9q8", "home")} == {"a", "b"}


def test_candidates_matches_any_listed_category_interest():
    repo = SeededBuyerPersonaRepository(
        personas=[_persona("multi", category_interests=["books", "home"])]
    )
    assert repo.candidates("9q8yy", "home")
    assert repo.candidates("9q8yy", "books")
    assert repo.candidates("9q8yy", "toys") == []


def test_candidates_is_case_insensitive():
    repo = SeededBuyerPersonaRepository(
        personas=[_persona("p", geohash5="9q8yy", category_interests=["Electronics"])]
    )
    found = repo.candidates("9Q8YY", "ELECTRONICS")
    assert [c.buyer_id for c in found] == ["p"]


def test_candidates_empty_when_no_match():
    repo = SeededBuyerPersonaRepository(
        personas=[_persona("p", geohash5="9q8yy", category_interests=["books"])]
    )
    assert repo.candidates("zzzzz", "books") == []
    assert repo.candidates("9q8yy", "toys") == []


def test_candidates_preserves_seed_order():
    repo = SeededBuyerPersonaRepository(
        personas=[
            _persona("first", category_interests=["books"]),
            _persona("second", category_interests=["books"]),
            _persona("third", category_interests=["books"]),
        ]
    )
    assert [c.buyer_id for c in repo.candidates("9q8yy", "books")] == [
        "first",
        "second",
        "third",
    ]


# -- property: every returned candidate matches the filter ----------------

# A tiny geo alphabet keeps prefixes overlapping (so matches occur often) and
# makes input generation cheap; the property holds for any character set.
_GEO_ALPHABET = "bcd"
_geohash = st.text(alphabet=_GEO_ALPHABET, min_size=1, max_size=3)
_categories = st.sampled_from(sorted(_SEED_CATEGORIES))


@st.composite
def _personas(draw):
    # One list draw (geo, interests) per persona is far cheaper than a manual
    # per-element draw loop, and ids are assigned afterwards to stay unique.
    specs = draw(
        st.lists(
            st.tuples(
                _geohash,
                st.lists(_categories, max_size=2, unique=True),
            ),
            max_size=6,
        )
    )
    return [
        _persona(f"b{i}", geohash5=geo, category_interests=cats)
        for i, (geo, cats) in enumerate(specs)
    ]


@given(personas=_personas(), geo=_geohash, category=_categories)
def test_every_candidate_matches_geo_and_category(personas, geo, category):
    repo = SeededBuyerPersonaRepository(personas=personas)

    found = repo.candidates(geo, category)

    for c in found:
        assert c.geohash5.lower().startswith(geo.lower())
        assert category.lower() in {i.lower() for i in c.category_interests}
    # Completeness: no qualifying persona is dropped.
    expected = [
        p
        for p in personas
        if p.geohash5.lower().startswith(geo.lower())
        and category.lower() in {i.lower() for i in p.category_interests}
    ]
    assert [c.buyer_id for c in found] == [p.buyer_id for p in expected]
