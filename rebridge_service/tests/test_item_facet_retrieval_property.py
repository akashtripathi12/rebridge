"""Property-based test for Item facet retrieval.

# Feature: rebridge-backend, Property 3: Item retrieval returns exactly the persisted facets

Property 3 (design.md): *For any* Item with an arbitrary subset of GRADE, CARD,
DECISION, and LISTING facets persisted, retrieving the Item SHALL return its
status and exactly those facets.

**Validates: Requirements 1.4**

The strategy below creates an Item through :class:`ItemService`, then persists
an arbitrary subset of the four optional facets directly via the
:class:`FakeItemRepository`. Retrieving the Item through ``get_item`` must then
return the Item status together with exactly the persisted facets - present
facets equal to what was stored, and every absent facet ``None``.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import (
    CardRecord,
    DecisionRecord,
    GradeRecord,
    ItemStatus,
    ListingRecord,
)

from rebridge_service.item_service import ItemService

from tests.fakes import FakeItemRepository

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

_text = st.text(min_size=1, max_size=20)
_money = st.builds(
    lambda cents: Decimal(cents) / Decimal(100),
    st.integers(min_value=0, max_value=1_000_000),
)


def _grade_record(item_id: str) -> st.SearchStrategy[GradeRecord]:
    return st.builds(
        GradeRecord,
        grade=st.sampled_from(
            ["Like New", "Very Good", "Good", "Acceptable", "Unsellable"]
        ),
        confidence=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        summary=_text,
    )


def _card_record(item_id: str) -> st.SearchStrategy[CardRecord]:
    return st.builds(
        CardRecord,
        card_id=_text,
        item_id=st.just(item_id),
        signature=_text,
        qr_target=_text,
        graded_at=_text,
        warranty_stance=_text,
    )


def _decision_record() -> st.SearchStrategy[DecisionRecord]:
    return st.builds(
        DecisionRecord,
        disposition=st.sampled_from(["RESELL", "REFURB", "P2P", "DONATE"]),
        price=_money,
        value=_money,
        cost=_money,
        margin=_money,
        rationale=_text,
    )


def _listing_record(item_id: str) -> st.SearchStrategy[ListingRecord]:
    return st.builds(
        ListingRecord,
        item_id=st.just(item_id),
        status=st.sampled_from(["ACTIVE", "SOLD", "DRAFT"]),
        category=_text,
        price=_money,
        geohash5=st.text(
            alphabet="0123456789bcdefghjkmnpqrstuvwxyz", min_size=5, max_size=5
        ),
        listed_at=_text,
    )


@st.composite
def items_with_facet_subset(draw: st.DrawFn):
    """Create an Item and persist an arbitrary subset of its optional facets.

    Returns ``(repo, item_id, expected)`` where ``expected`` maps each facet
    name to the persisted record or ``None`` when that facet was not persisted.
    Each facet is independently included or omitted, so the full power set of
    {GRADE, CARD, DECISION, LISTING} subsets is reachable.
    """

    repo = FakeItemRepository()
    svc = ItemService(item_repo=repo)
    item_id = svc.create_item(
        {"context_source": "manual", "category": "toys", "age_months": 3}
    ).item_id

    expected: dict[str, object | None] = {
        "grade": None,
        "card": None,
        "decision": None,
        "listing": None,
    }

    if draw(st.booleans()):
        grade = draw(_grade_record(item_id))
        repo.put_grade(item_id, grade)
        expected["grade"] = grade
    if draw(st.booleans()):
        card = draw(_card_record(item_id))
        repo.put_card(item_id, card)
        expected["card"] = card
    if draw(st.booleans()):
        decision = draw(_decision_record())
        repo.put_decision(item_id, decision)
        expected["decision"] = decision
    if draw(st.booleans()):
        listing = draw(_listing_record(item_id))
        repo.put_listing(item_id, listing)
        expected["listing"] = listing

    return repo, item_id, expected


@settings(max_examples=_ITERATIONS)
@given(items_with_facet_subset())
def test_get_item_returns_exactly_persisted_facets(case) -> None:
    """get_item returns status plus exactly the persisted facets (Req 1.4)."""

    repo, item_id, expected = case
    svc = ItemService(item_repo=repo)

    aggregate = svc.get_item(item_id)

    # The Item status is always returned.
    assert aggregate.meta.item_id == item_id
    assert aggregate.meta.status is ItemStatus.CREATED

    # Each facet is present iff it was persisted, and equals what was stored.
    assert aggregate.grade == expected["grade"]
    assert aggregate.card == expected["card"]
    assert aggregate.decision == expected["decision"]
    assert aggregate.listing == expected["listing"]

    # Restated as an exact-subset invariant: the set of present facet names
    # equals the set of facet names that were persisted.
    present = {
        name
        for name in ("grade", "card", "decision", "listing")
        if getattr(aggregate, name) is not None
    }
    persisted = {name for name, value in expected.items() if value is not None}
    assert present == persisted
