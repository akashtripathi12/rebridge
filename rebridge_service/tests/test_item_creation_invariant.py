"""Property-based test for the item creation invariant.

# Feature: rebridge-backend, Property 1: Item creation invariant

Property 1 (design.md): *For any* valid item-creation request (order-scan or
manual context), the created Item SHALL have a unique item identifier and an
initial status of CREATED.

**Validates: Requirements 1.1, 1.2**

The strategy below generates only *valid* creation requests in either of the
two allowed context shapes (``order_scan`` requires ``order_id`` in addition to
the common ``category``/``age_months`` fields; ``manual`` requires only the
common fields). Each generated request is constrained to the valid input space
so every ``create_item`` call is expected to succeed. The test asserts the
per-item invariant (status CREATED, an id assigned, the persisted item
retrievable) and, by creating a whole batch of requests against one repository,
the cross-item uniqueness of the assigned identifiers.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import ItemStatus

from rebridge_service.item_service import ItemService

from tests.fakes import FakeItemRepository

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

# Non-empty category labels (a required field for both context shapes).
_category = st.text(min_size=1, max_size=30)

# Item age in whole months; a non-negative required field for both shapes.
_age_months = st.integers(min_value=0, max_value=600)

# Non-empty scanned-order reference, required only for the order-scan shape.
_order_id = st.text(min_size=1, max_size=30)


@st.composite
def order_scan_requests(draw: st.DrawFn) -> dict:
    """Generate a valid order-scan creation request (Requirement 1.1)."""

    return {
        "context_source": "order_scan",
        "category": draw(_category),
        "age_months": draw(_age_months),
        "order_id": draw(_order_id),
    }


@st.composite
def manual_requests(draw: st.DrawFn) -> dict:
    """Generate a valid manual-context creation request (Requirement 1.2)."""

    return {
        "context_source": "manual",
        "category": draw(_category),
        "age_months": draw(_age_months),
    }


# Either valid context shape (covers Requirements 1.1 and 1.2 together).
valid_requests = st.one_of(order_scan_requests(), manual_requests())


@settings(max_examples=_ITERATIONS)
@given(valid_requests)
def test_creation_yields_created_status_and_retrievable_item(request: dict) -> None:
    """A valid request yields an item with an id, status CREATED, retrievable.

    Validates Requirements 1.1 (order-scan) and 1.2 (manual): the created Item
    has a unique item identifier and an initial status of CREATED.
    """

    svc = ItemService(item_repo=FakeItemRepository())
    meta = svc.create_item(request)

    # An item identifier is assigned.
    assert isinstance(meta.item_id, str)
    assert meta.item_id != ""

    # Initial status is CREATED.
    assert meta.status is ItemStatus.CREATED

    # The context shape is preserved as requested.
    assert meta.context_source == request["context_source"]

    # The persisted item is retrievable and reports the same id and status.
    stored = svc.get_item(meta.item_id)
    assert stored.meta.item_id == meta.item_id
    assert stored.meta.status is ItemStatus.CREATED


@settings(max_examples=_ITERATIONS)
@given(st.lists(valid_requests, min_size=1, max_size=25))
def test_identifiers_are_unique_across_creations(requests: list[dict]) -> None:
    """Distinct creations receive distinct, unique item identifiers.

    Creating an arbitrary batch of valid requests against one repository yields
    one item per request, each with a CREATED status and an id unique across the
    batch (Requirements 1.1, 1.2).
    """

    svc = ItemService(item_repo=FakeItemRepository())
    ids = []
    for request in requests:
        meta = svc.create_item(request)
        assert meta.status is ItemStatus.CREATED
        # Each created item is independently retrievable.
        assert svc.get_item(meta.item_id).meta.item_id == meta.item_id
        ids.append(meta.item_id)

    # Uniqueness: no identifier collides across the batch.
    assert len(set(ids)) == len(requests)
