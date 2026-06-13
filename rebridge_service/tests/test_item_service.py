"""Unit tests for :class:`rebridge_service.item_service.ItemService`.

Covers task 4.1 behaviors against the in-memory :class:`FakeItemRepository`:

* creation from order-scan and manual contexts yields a unique id + status
  CREATED (Requirements 1.1, 1.2),
* missing required fields are rejected with the field named (Requirement 1.3),
* aggregate retrieval returns exactly the persisted facets (Requirement 1.4),
* unknown ids raise a not-found error (Requirement 1.5).

Property-based coverage lives in the separate property-test tasks (4.2-4.4).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from rebridge_data.models import (
    CardRecord,
    DecisionRecord,
    GradeRecord,
    ItemStatus,
    ListingRecord,
)

from rebridge_service.item_service import (
    InvalidField,
    InvalidPhotoCount,
    ItemNotFound,
    ItemService,
    MissingField,
    ObjectStoreNotConfigured,
    GradeRequired,
    ListingNotFound,
    DEFAULT_LISTING_STATUS,
    PHOTO_UPLOAD_TTL_SECONDS,
)

from rebridge_data.models import ListingPatch

from tests.fakes import FakeItemRepository, FakeObjectStore


def _service() -> ItemService:
    return ItemService(item_repo=FakeItemRepository(), object_store=FakeObjectStore())


def _order_scan_request() -> dict:
    return {
        "context_source": "order_scan",
        "category": "electronics",
        "age_months": 12,
        "order_id": "ORD-123",
    }


def _manual_request() -> dict:
    return {
        "context_source": "manual",
        "category": "toys",
        "age_months": 3,
    }


# -- creation (1.1, 1.2) --------------------------------------------------
def test_create_from_order_scan_context_assigns_id_and_created_status():
    svc = _service()
    meta = svc.create_item(_order_scan_request())

    assert meta.item_id  # unique identifier assigned
    assert meta.status is ItemStatus.CREATED
    assert meta.context_source == "order_scan"
    assert meta.context_ref == "ORD-123"
    assert meta.created_at  # timestamp recorded

    # Persisted and retrievable.
    stored = svc.get_item(meta.item_id)
    assert stored.meta.item_id == meta.item_id
    assert stored.meta.status is ItemStatus.CREATED


def test_create_from_manual_context_assigns_id_and_created_status():
    svc = _service()
    meta = svc.create_item(_manual_request())

    assert meta.item_id
    assert meta.status is ItemStatus.CREATED
    assert meta.context_source == "manual"
    assert meta.context_ref is None


def test_each_creation_gets_a_unique_identifier():
    svc = _service()
    ids = {svc.create_item(_manual_request()).item_id for _ in range(50)}
    assert len(ids) == 50


def test_injectable_id_and_clock_make_creation_deterministic():
    repo = FakeItemRepository()
    svc = ItemService(
        item_repo=repo,
        id_factory=lambda: "fixed-id",
        clock=lambda: __import__("datetime").datetime(2024, 1, 1),
    )
    meta = svc.create_item(_manual_request())
    assert meta.item_id == "fixed-id"
    assert meta.created_at == "2024-01-01T00:00:00"


# -- missing/invalid fields (1.3) -----------------------------------------
@pytest.mark.parametrize("field", ["context_source", "category", "age_months"])
def test_missing_common_field_is_rejected_naming_the_field(field):
    svc = _service()
    request = _manual_request()
    del request[field]
    with pytest.raises(MissingField) as exc:
        svc.create_item(request)
    assert exc.value.field == field
    assert field in str(exc.value)


def test_missing_order_scan_specific_field_is_rejected():
    svc = _service()
    request = _order_scan_request()
    del request["order_id"]
    with pytest.raises(MissingField) as exc:
        svc.create_item(request)
    assert exc.value.field == "order_id"


def test_none_valued_required_field_is_treated_as_missing():
    svc = _service()
    request = _manual_request()
    request["category"] = None
    with pytest.raises(MissingField) as exc:
        svc.create_item(request)
    assert exc.value.field == "category"


def test_unknown_context_source_is_rejected_as_invalid():
    svc = _service()
    request = _manual_request()
    request["context_source"] = "carrier_pigeon"
    with pytest.raises(InvalidField) as exc:
        svc.create_item(request)
    assert exc.value.field == "context_source"


def test_manual_context_does_not_require_order_id():
    svc = _service()
    # No order_id present; manual creation should still succeed.
    meta = svc.create_item(_manual_request())
    assert meta.context_ref is None


# -- aggregate retrieval (1.4) --------------------------------------------
def test_get_item_returns_only_persisted_facets():
    repo = FakeItemRepository()
    svc = ItemService(item_repo=repo)
    meta = svc.create_item(_manual_request())
    item_id = meta.item_id

    # Initially only META exists.
    agg = svc.get_item(item_id)
    assert agg.grade is None
    assert agg.card is None
    assert agg.decision is None
    assert agg.listing is None

    # Persist a subset of facets directly via the repository.
    repo.put_grade(item_id, GradeRecord(grade="Good", confidence=0.9, summary="ok"))
    repo.put_listing(
        item_id,
        ListingRecord(
            item_id=item_id,
            status="ACTIVE",
            category="toys",
            price=Decimal("9.99"),
            geohash5="9q8yy",
            listed_at="2024-01-01T00:00:00Z",
        ),
    )

    agg = svc.get_item(item_id)
    assert agg.grade is not None
    assert agg.listing is not None
    assert agg.card is None  # not persisted
    assert agg.decision is None  # not persisted
    assert agg.meta.status is ItemStatus.CREATED


def test_get_item_returns_all_facets_when_all_present():
    repo = FakeItemRepository()
    svc = ItemService(item_repo=repo)
    item_id = svc.create_item(_manual_request()).item_id

    repo.put_grade(item_id, GradeRecord(grade="Good", confidence=0.9, summary="ok"))
    repo.put_card(
        item_id,
        CardRecord(
            card_id="card-1",
            item_id=item_id,
            signature="sig",
            qr_target="/cards/card-1/verify",
            graded_at="2024-01-01T00:00:00Z",
            warranty_stance="30-day",
        ),
    )
    repo.put_decision(
        item_id,
        DecisionRecord(
            disposition="RESELL",
            price=Decimal("20"),
            value=Decimal("30"),
            cost=Decimal("10"),
            margin=Decimal("20"),
            rationale="value 30, cost 10, margin 20",
        ),
    )
    repo.put_listing(
        item_id,
        ListingRecord(
            item_id=item_id,
            status="ACTIVE",
            category="toys",
            price=Decimal("9.99"),
            geohash5="9q8yy",
            listed_at="2024-01-01T00:00:00Z",
        ),
    )

    agg = svc.get_item(item_id)
    assert agg.grade is not None
    assert agg.card is not None
    assert agg.decision is not None
    assert agg.listing is not None


# -- not found (1.5) ------------------------------------------------------
def test_get_unknown_item_raises_not_found():
    svc = _service()
    with pytest.raises(ItemNotFound) as exc:
        svc.get_item("does-not-exist")
    assert exc.value.item_id == "does-not-exist"


# -- presigned photo upload (2.1, 2.2, 2.3, 2.4) --------------------------
def _service_with_item() -> tuple[ItemService, str]:
    """Build a service over a fake store and return it with one created item."""
    svc = ItemService(item_repo=FakeItemRepository(), object_store=FakeObjectStore())
    item_id = svc.create_item(_manual_request()).item_id
    return svc, item_id


@pytest.mark.parametrize("count", [2, 3, 4])
def test_valid_count_returns_one_presigned_url_per_slot(count):
    # Req 2.1: one presigned URL per requested slot for 2..4 photos.
    svc, item_id = _service_with_item()
    urls = svc.request_photo_upload_urls(item_id, count)

    assert len(urls) == count
    # Each URL targets a distinct, stable per-slot object key.
    targets = [u.url for u in urls]
    assert len(set(targets)) == count
    for slot in range(1, count + 1):
        assert any(f"items/{item_id}/photo-{slot}" in t for t in targets)


def test_presigned_urls_expire_after_five_minutes():
    # Req 2.2: URLs expire 5 minutes (300s) after issuance.
    svc, item_id = _service_with_item()
    urls = svc.request_photo_upload_urls(item_id, 3)
    assert PHOTO_UPLOAD_TTL_SECONDS == 300
    assert all(u.expires_in == 300 for u in urls)


def test_presigned_request_does_not_proxy_photo_bytes():
    # Req 2.3: only upload targets are returned; method takes no image bytes.
    svc, item_id = _service_with_item()
    urls = svc.request_photo_upload_urls(item_id, 2)
    # Returned values are upload descriptors (PUT URLs), never raw bytes.
    assert all(u.method == "PUT" for u in urls)
    assert all(isinstance(u.url, str) for u in urls)


@pytest.mark.parametrize("count", [1, 5])
def test_out_of_range_count_is_rejected(count):
    # Req 2.4: fewer than 2 or more than 4 is a range error.
    svc, item_id = _service_with_item()
    with pytest.raises(InvalidPhotoCount) as exc:
        svc.request_photo_upload_urls(item_id, count)
    assert exc.value.count == count
    assert exc.value.minimum == 2
    assert exc.value.maximum == 4
    assert "2" in str(exc.value) and "4" in str(exc.value)


@pytest.mark.parametrize("count", [0, -1, 1, 5, 10])
def test_out_of_range_count_issues_no_urls(count):
    # Rejection happens before any URL is minted.
    store = FakeObjectStore()
    svc = ItemService(item_repo=FakeItemRepository(), object_store=store)
    item_id = svc.create_item(_manual_request()).item_id
    with pytest.raises(InvalidPhotoCount):
        svc.request_photo_upload_urls(item_id, count)
    assert store.presigned == []


def test_presign_for_unknown_item_raises_not_found():
    # Req 2.1 applies to an existing Item.
    svc, _ = _service_with_item()
    with pytest.raises(ItemNotFound):
        svc.request_photo_upload_urls("nope", 3)


def test_presign_without_object_store_raises_configuration_error():
    svc = ItemService(item_repo=FakeItemRepository())  # no object_store injected
    item_id = svc.create_item(_manual_request()).item_id
    with pytest.raises(ObjectStoreNotConfigured):
        svc.request_photo_upload_urls(item_id, 3)


# -- listing CRUD with grade-required guard (3.1-3.5) ---------------------
def _graded_item() -> tuple[ItemService, FakeItemRepository, str]:
    """Build a service over a fake repo with one created, graded item."""
    repo = FakeItemRepository()
    svc = ItemService(item_repo=repo)
    item_id = svc.create_item(_manual_request()).item_id
    repo.put_grade(item_id, GradeRecord(grade="Good", confidence=0.9, summary="ok"))
    return svc, repo, item_id


def test_create_listing_on_graded_item_persists_facet():
    # Req 3.1: a valid listing creation request creates the LISTING facet.
    svc, _, item_id = _graded_item()
    listing = svc.create_listing(
        item_id,
        category="toys",
        price=Decimal("9.99"),
        geohash5="9q8yy",
        listed_at="2024-01-01T00:00:00Z",
    )

    assert listing.item_id == item_id
    assert listing.category == "toys"
    assert listing.price == Decimal("9.99")
    assert listing.geohash5 == "9q8yy"
    assert listing.status == DEFAULT_LISTING_STATUS

    # Round-trip: create-then-get returns an equal listing (Req 3.1, 3.3).
    fetched = svc.get_listing(item_id)
    assert fetched == listing
    # Also visible on the aggregate.
    assert svc.get_item(item_id).listing == listing


def test_create_listing_defaults_listed_at_from_clock():
    repo = FakeItemRepository()
    svc = ItemService(
        item_repo=repo,
        clock=lambda: __import__("datetime").datetime(2024, 6, 1),
    )
    item_id = svc.create_item(_manual_request()).item_id
    repo.put_grade(item_id, GradeRecord(grade="Good", confidence=0.9, summary="ok"))

    listing = svc.create_listing(
        item_id, category="toys", price=Decimal("5"), geohash5="9q8yy"
    )
    assert listing.listed_at == "2024-06-01T00:00:00"


def test_create_listing_without_grade_is_rejected():
    # Req 3.5: creating a listing for an item with no grade is rejected.
    repo = FakeItemRepository()
    svc = ItemService(item_repo=repo)
    item_id = svc.create_item(_manual_request()).item_id  # no grade persisted

    with pytest.raises(GradeRequired) as exc:
        svc.create_listing(
            item_id, category="toys", price=Decimal("9.99"), geohash5="9q8yy"
        )
    assert exc.value.item_id == item_id
    assert "grade is required" in str(exc.value)
    # Nothing was persisted.
    assert repo.get_listing(item_id) is None


def test_create_listing_for_unknown_item_raises_not_found():
    svc = ItemService(item_repo=FakeItemRepository())
    with pytest.raises(ItemNotFound):
        svc.create_listing(
            "nope", category="toys", price=Decimal("1"), geohash5="9q8yy"
        )


def test_update_listing_applies_patch():
    # Req 3.2: a valid update applies the requested changes to the facet.
    svc, _, item_id = _graded_item()
    svc.create_listing(
        item_id, category="toys", price=Decimal("9.99"), geohash5="9q8yy"
    )

    updated = svc.update_listing(
        item_id, ListingPatch(price=Decimal("7.50"), status="PAUSED")
    )
    assert updated.price == Decimal("7.50")
    assert updated.status == "PAUSED"
    # Unpatched fields are unchanged.
    assert updated.category == "toys"
    assert updated.geohash5 == "9q8yy"

    # update-then-get reflects the patch (Req 3.2, 3.3).
    assert svc.get_listing(item_id) == updated


def test_update_listing_without_existing_listing_raises():
    svc, _, item_id = _graded_item()  # graded but no listing yet
    with pytest.raises(ListingNotFound):
        svc.update_listing(item_id, ListingPatch(price=Decimal("1")))


def test_update_listing_for_unknown_item_raises_not_found():
    svc = ItemService(item_repo=FakeItemRepository())
    with pytest.raises(ItemNotFound):
        svc.update_listing("nope", ListingPatch(price=Decimal("1")))


def test_get_listing_returns_none_when_no_listing():
    svc, _, item_id = _graded_item()
    assert svc.get_listing(item_id) is None


def test_get_listing_for_unknown_item_raises_not_found():
    svc = ItemService(item_repo=FakeItemRepository())
    with pytest.raises(ItemNotFound):
        svc.get_listing("nope")


def test_delete_listing_removes_facet():
    # Req 3.4: deletion removes the LISTING facet.
    svc, _, item_id = _graded_item()
    svc.create_listing(
        item_id, category="toys", price=Decimal("9.99"), geohash5="9q8yy"
    )
    assert svc.get_listing(item_id) is not None

    svc.delete_listing(item_id)
    # delete-then-get returns none (Req 3.4).
    assert svc.get_listing(item_id) is None


def test_delete_listing_is_idempotent_for_existing_item():
    svc, _, item_id = _graded_item()  # no listing created
    # Deleting an absent listing on a known item is a no-op, not an error.
    svc.delete_listing(item_id)
    assert svc.get_listing(item_id) is None


def test_delete_listing_for_unknown_item_raises_not_found():
    svc = ItemService(item_repo=FakeItemRepository())
    with pytest.raises(ItemNotFound):
        svc.delete_listing("nope")


def test_listing_full_round_trip_create_update_get_delete():
    # End-to-end round trip across all four operations (Req 3.1-3.4).
    svc, _, item_id = _graded_item()

    created = svc.create_listing(
        item_id, category="toys", price=Decimal("20"), geohash5="9q8yy"
    )
    assert svc.get_listing(item_id) == created

    svc.update_listing(item_id, ListingPatch(category="games", price=Decimal("18")))
    after_update = svc.get_listing(item_id)
    assert after_update.category == "games"
    assert after_update.price == Decimal("18")

    svc.delete_listing(item_id)
    assert svc.get_listing(item_id) is None
