"""Property-based test for listing round-trip and the grade-required guard.

# Feature: rebridge-backend, Property 5: Listing round-trip and grade-required guard

Property 5 (design.md): *For any* graded Item and valid listing, create-then-get
SHALL return an equal listing, update-then-get SHALL reflect the patch, and
delete-then-get SHALL return none; *for any* Item without a grade, listing
creation SHALL be rejected with a grade-required error.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

The strategies below generate valid listing field-sets and arbitrary
:class:`ListingPatch` values constrained to the listing's input space. Each
scenario exercises one Item against an in-memory :class:`FakeItemRepository`
(no AWS calls), driving the four CRUD operations through :class:`ItemService`:

* create-then-get returns an equal :class:`ListingRecord` (Req 3.1, 3.3),
* update-then-get reflects exactly the patched fields and leaves the rest
  unchanged (Req 3.2),
* delete-then-get returns ``None`` (Req 3.4), and
* creating a listing for an ungraded Item raises :class:`GradeRequired` with
  nothing persisted (Req 3.5).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import GradeRecord, ListingPatch, ListingRecord

from rebridge_service.item_service import GradeRequired, ItemService

from tests.fakes import FakeItemRepository

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

# A non-empty category label.
_category = st.text(min_size=1, max_size=30)

# A non-negative monetary amount with two decimal places.
_money = st.builds(
    lambda cents: Decimal(cents) / Decimal(100),
    st.integers(min_value=0, max_value=10_000_000),
)

# A five-character geohash over the standard geohash alphabet.
_geohash5 = st.text(
    alphabet="0123456789bcdefghjkmnpqrstuvwxyz", min_size=5, max_size=5
)

# A listing status label.
_status = st.sampled_from(["ACTIVE", "PAUSED", "SOLD", "DRAFT"])


@st.composite
def listing_fields(draw: st.DrawFn) -> dict:
    """Generate a valid set of fields for a new listing (Req 3.1)."""

    return {
        "category": draw(_category),
        "price": draw(_money),
        "geohash5": draw(_geohash5),
        "status": draw(_status),
        "listed_at": "2024-01-01T00:00:00Z",
    }


@st.composite
def listing_patches(draw: st.DrawFn) -> ListingPatch:
    """Generate an arbitrary partial update (some fields possibly unset).

    Each of the four patchable fields is independently included or left
    ``None`` (unchanged), so the full power set of patched-field combinations is
    reachable.
    """

    return ListingPatch(
        status=draw(st.one_of(st.none(), _status)),
        category=draw(st.one_of(st.none(), _category)),
        price=draw(st.one_of(st.none(), _money)),
        geohash5=draw(st.one_of(st.none(), _geohash5)),
    )


def _graded_service() -> tuple[ItemService, str]:
    """Build a service over a fake repo with one created, graded Item."""

    repo = FakeItemRepository()
    svc = ItemService(item_repo=repo)
    item_id = svc.create_item(
        {"context_source": "manual", "category": "toys", "age_months": 3}
    ).item_id
    repo.put_grade(item_id, GradeRecord(grade="Good", confidence=0.9, summary="ok"))
    return svc, item_id


@settings(max_examples=_ITERATIONS)
@given(fields=listing_fields(), patch=listing_patches())
def test_listing_round_trip_create_update_delete(
    fields: dict, patch: ListingPatch
) -> None:
    """Create→get equal, update→get reflects patch, delete→get none.

    Validates Requirements 3.1 (create persists the facet), 3.3 (get returns the
    current facet), 3.2 (update applies the patch, leaving unpatched fields
    unchanged), and 3.4 (delete removes the facet).
    """

    svc, item_id = _graded_service()

    # create-then-get returns an equal listing (Req 3.1, 3.3).
    created = svc.create_listing(item_id, **fields)
    assert isinstance(created, ListingRecord)
    assert svc.get_listing(item_id) == created
    # The listing is also visible on the aggregate.
    assert svc.get_item(item_id).listing == created

    # update-then-get reflects the patch and leaves other fields unchanged (3.2).
    expected = replace(
        created,
        status=patch.status if patch.status is not None else created.status,
        category=patch.category if patch.category is not None else created.category,
        price=patch.price if patch.price is not None else created.price,
        geohash5=patch.geohash5 if patch.geohash5 is not None else created.geohash5,
    )
    updated = svc.update_listing(item_id, patch)
    assert updated == expected
    assert svc.get_listing(item_id) == expected

    # item_id and listed_at are never part of a patch, so they are preserved.
    assert updated.item_id == created.item_id
    assert updated.listed_at == created.listed_at

    # delete-then-get returns none (Req 3.4).
    svc.delete_listing(item_id)
    assert svc.get_listing(item_id) is None
    assert svc.get_item(item_id).listing is None


@settings(max_examples=_ITERATIONS)
@given(fields=listing_fields())
def test_create_listing_without_grade_is_rejected_and_persists_nothing(
    fields: dict,
) -> None:
    """Listing an ungraded Item raises GradeRequired with nothing persisted (3.5)."""

    repo = FakeItemRepository()
    svc = ItemService(item_repo=repo)
    item_id = svc.create_item(
        {"context_source": "manual", "category": "toys", "age_months": 3}
    ).item_id  # no grade persisted

    with pytest.raises(GradeRequired) as exc:
        svc.create_listing(item_id, **fields)

    assert exc.value.item_id == item_id
    # Nothing was persisted: no LISTING facet exists on the Item.
    assert repo.get_listing(item_id) is None
    assert svc.get_item(item_id).listing is None
