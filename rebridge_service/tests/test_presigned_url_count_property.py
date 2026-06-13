"""Property-based test for presigned photo-upload URL count validation.

# Feature: rebridge-backend, Property 4: Presigned URL count matches valid request and rejects out-of-range counts

Property 4 (design.md): *For any* requested photo-slot count n, the Item_API
SHALL return n presigned URLs when 2 <= n <= 4, and SHALL reject with a
2-to-4 range error otherwise.

**Validates: Requirements 2.1, 2.4**

The strategies split the integer input space into the two regions the property
distinguishes:

* the in-range region ``2 <= n <= 4`` (Requirement 2.1) - the service must mint
  exactly ``n`` presigned upload targets, one per slot, each with a 300-second
  TTL; and
* the out-of-range region ``n < 2`` or ``n > 4`` (Requirement 2.4) - the service
  must reject the request with :class:`InvalidPhotoCount` and mint no URLs at
  all.

Each example is exercised against the in-memory :class:`FakeObjectStore`, whose
``presigned`` list records every URL it issues, so the test can assert that a
rejected request has zero side effects on the store.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.item_service import (
    InvalidPhotoCount,
    ItemService,
    MAX_PHOTOS,
    MIN_PHOTOS,
    PHOTO_UPLOAD_TTL_SECONDS,
)

from tests.fakes import FakeItemRepository, FakeObjectStore

# Minimum iterations per the spec's property-testing guideline (>= 100).
_ITERATIONS = 200

# Valid photo-slot counts: the inclusive 2..4 range (Requirement 2.1).
_in_range_counts = st.integers(min_value=MIN_PHOTOS, max_value=MAX_PHOTOS)

# Out-of-range counts: ints below 2 and ints above 4 (Requirement 2.4).
_below_range_counts = st.integers(max_value=MIN_PHOTOS - 1)
_above_range_counts = st.integers(min_value=MAX_PHOTOS + 1)
_out_of_range_counts = st.one_of(_below_range_counts, _above_range_counts)


def _service_with_item() -> tuple[ItemService, FakeObjectStore, str]:
    """Build a service over fresh fakes and return it with one created item."""
    store = FakeObjectStore()
    svc = ItemService(item_repo=FakeItemRepository(), object_store=store)
    item_id = svc.create_item(
        {"context_source": "manual", "category": "toys", "age_months": 1}
    ).item_id
    return svc, store, item_id


@settings(max_examples=_ITERATIONS)
@given(_in_range_counts)
def test_in_range_count_returns_exactly_n_urls_with_300s_ttl(count: int) -> None:
    """A 2..4 count yields exactly ``count`` distinct URLs, each TTL 300.

    Validates Requirement 2.1: one presigned URL per requested photo slot for an
    existing Item, each expiring 300 seconds after issuance (Requirement 2.2 is
    relied upon by 2.1's per-slot contract).
    """
    svc, store, item_id = _service_with_item()

    urls = svc.request_photo_upload_urls(item_id, count)

    # Exactly one URL per requested slot.
    assert len(urls) == count
    # Each URL addresses a distinct upload target.
    assert len({u.url for u in urls}) == count
    # Every minted URL carries the 300-second TTL.
    assert PHOTO_UPLOAD_TTL_SECONDS == 300
    assert all(u.expires_in == 300 for u in urls)
    # The store issued exactly those URLs and no more.
    assert len(store.presigned) == count


@settings(max_examples=_ITERATIONS)
@given(_out_of_range_counts)
def test_out_of_range_count_is_rejected_and_mints_no_urls(count: int) -> None:
    """A count outside 2..4 raises a range error and issues no URLs.

    Validates Requirement 2.4: requesting fewer than 2 or more than 4 photo
    upload URLs is rejected with :class:`InvalidPhotoCount` stating the allowed
    2-to-4 range, and the rejection happens before any URL is minted.
    """
    svc, store, item_id = _service_with_item()

    try:
        svc.request_photo_upload_urls(item_id, count)
    except InvalidPhotoCount as exc:
        # The error reports the offending count and the allowed bounds.
        assert exc.count == count
        assert exc.minimum == MIN_PHOTOS
        assert exc.maximum == MAX_PHOTOS
        assert "2" in str(exc) and "4" in str(exc)
    else:
        raise AssertionError(
            f"expected InvalidPhotoCount for out-of-range count {count}, "
            "but the request succeeded"
        )

    # No presigned URL was minted as a side effect of the rejected request.
    assert store.presigned == []
