"""API-layer unit tests for the routers wired to in-memory fakes (task 17.1).

Exercises the API contract with FastAPI's TestClient against real service-layer
logic backed by in-memory fakes (no AWS). Covers item create/retrieve/presign/
grade-enqueue/route, listing CRUD with the grade-required guard, the marketplace
query, and the simulated checkout that emits SOLD.
"""

from __future__ import annotations

from decimal import Decimal

from rebridge_data.models import GradeRecord

from tests.conftest import Harness


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _create_item(client, *, category="electronics", age_months=10) -> str:
    resp = client.post(
        "/items",
        json={
            "context_source": "manual",
            "category": category,
            "age_months": age_months,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["item_id"]


def _seed_grade(harness: Harness, item_id: str, *, grade="Good", confidence=0.9) -> None:
    harness.item_repo.put_grade(
        item_id,
        GradeRecord(grade=grade, confidence=confidence, summary="solid condition"),
    )


# ---------------------------------------------------------------------------
# items: create / retrieve
# ---------------------------------------------------------------------------


def test_create_item_returns_201_with_created_status(client):
    """Req 1.1, 1.2: created item has a unique id and status CREATED."""
    resp = client.post(
        "/items",
        json={"context_source": "manual", "category": "electronics", "age_months": 8},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["item_id"]
    assert body["status"] == "CREATED"
    assert body["category"] == "electronics"


def test_create_order_scan_requires_order_id_422_naming_field(client):
    """Req 1.3: a missing required field is rejected with a 422 naming it."""
    resp = client.post(
        "/items",
        json={"context_source": "order_scan", "category": "electronics", "age_months": 8},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["field"] == "order_id"
    assert "order_id" in body["detail"]


def test_get_unknown_item_returns_404(client):
    """Req 1.5: unknown item id yields a 404 not-found."""
    resp = client.get("/items/does-not-exist")
    assert resp.status_code == 404


def test_get_item_returns_exactly_persisted_facets(client, harness):
    """Req 1.4: retrieval returns the status plus exactly the persisted facets."""
    item_id = _create_item(client)
    # Only a GRADE facet is persisted; CARD/DECISION/LISTING remain absent.
    _seed_grade(harness, item_id)

    resp = client.get(f"/items/{item_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["status"] == "CREATED"
    assert body["grade"] is not None
    assert body["grade"]["grade"] == "Good"
    assert body["card"] is None
    assert body["decision"] is None
    assert body["listing"] is None


# ---------------------------------------------------------------------------
# presign
# ---------------------------------------------------------------------------


def test_presign_returns_n_urls_for_valid_count(client):
    """Req 2.1: a valid count yields exactly that many presigned URLs (5-min TTL)."""
    item_id = _create_item(client)
    resp = client.post(f"/items/{item_id}/photos:presign", json={"count": 3})
    assert resp.status_code == 200
    urls = resp.json()["urls"]
    assert len(urls) == 3
    assert all(u["expires_in"] == 300 for u in urls)


def test_presign_rejects_out_of_range_count_422(client):
    """Req 2.4: a count outside 2-4 is rejected with a 422 range error."""
    item_id = _create_item(client)
    resp = client.post(f"/items/{item_id}/photos:presign", json={"count": 5})
    assert resp.status_code == 422
    assert "2 to 4" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# grade (async enqueue)
# ---------------------------------------------------------------------------


def test_grade_returns_202_with_idempotency_key_header_and_enqueues(client, harness):
    """Req 7.1, 7.2: grade enqueues a message and returns 202 + Idempotency-Key."""
    item_id = _create_item(client)
    resp = client.post(
        f"/items/{item_id}/grade",
        json={"photo_keys": ["k1", "k2", "k3"]},
    )
    assert resp.status_code == 202
    key = resp.headers.get("Idempotency-Key")
    assert key
    assert resp.json()["idempotency_key"] == key
    # Exactly one grading message was enqueued for this item with the same key.
    assert len(harness.queue.messages) == 1
    msg = harness.queue.messages[0]
    assert msg.item_id == item_id
    assert msg.idem_key == key
    assert msg.photo_keys == ["k1", "k2", "k3"]


def test_grade_key_is_deterministic_for_same_photo_set(client):
    """Req 7.2: the derived key is deterministic for the same item + photo set."""
    item_id = _create_item(client)
    first = client.post(f"/items/{item_id}/grade", json={"photo_keys": ["a", "b"]})
    second = client.post(f"/items/{item_id}/grade", json={"photo_keys": ["b", "a"]})
    assert first.headers["Idempotency-Key"] == second.headers["Idempotency-Key"]


def test_grade_unknown_item_404(client):
    item_id = "nope"
    resp = client.post(f"/items/{item_id}/grade", json={"photo_keys": ["a", "b"]})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------


def test_route_graded_item_returns_decision(client, harness):
    """Req 10.1, 10.7: routing returns a disposition + unit-economics rationale."""
    item_id = _create_item(client)
    _seed_grade(harness, item_id, grade="Good")
    resp = client.post(f"/items/{item_id}/route", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["disposition"] in {"RESELL", "REFURB", "P2P", "DONATE"}
    assert "margin" in body["rationale"]
    # A ROUTED event identifying the item was emitted.
    routed = harness.publisher.events_of("ROUTED")
    assert len(routed) == 1
    assert routed[0].item_id == item_id


def test_route_ungraded_item_409(client):
    item_id = _create_item(client)
    resp = client.post(f"/items/{item_id}/route", json={})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# listings CRUD + grade guard
# ---------------------------------------------------------------------------


def test_create_listing_requires_grade_409(client):
    """Req 3.5: listing an ungraded item is rejected with 409 grade-required."""
    item_id = _create_item(client)
    resp = client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": "electronics",
            "price": "120.00",
            "geohash5": "9q8yy",
        },
    )
    assert resp.status_code == 409


def test_listing_crud_round_trip_and_listed_event(client, harness):
    """Req 3.1-3.4, 15.3: create/get/update/delete a listing; LISTED is emitted."""
    item_id = _create_item(client)
    _seed_grade(harness, item_id)

    # create
    created = client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": "electronics",
            "price": "120.00",
            "geohash5": "9q8yy",
        },
    )
    assert created.status_code == 201
    assert created.json()["category"] == "electronics"
    assert harness.publisher.events_of("LISTED")[0].item_id == item_id

    # get
    got = client.get(f"/listings/{item_id}")
    assert got.status_code == 200
    assert Decimal(str(got.json()["price"])) == Decimal("120.00")

    # update
    updated = client.put(f"/listings/{item_id}", json={"price": "99.50"})
    assert updated.status_code == 200
    assert Decimal(str(updated.json()["price"])) == Decimal("99.50")

    # delete
    deleted = client.delete(f"/listings/{item_id}")
    assert deleted.status_code == 204
    assert client.get(f"/listings/{item_id}").status_code == 404


# ---------------------------------------------------------------------------
# marketplace
# ---------------------------------------------------------------------------


def test_marketplace_returns_listed_items(client, harness):
    """Req 3.3, 13: the marketplace query returns matching listings."""
    item_id = _create_item(client)
    _seed_grade(harness, item_id)
    client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": "electronics",
            "price": "120.00",
            "geohash5": "9q8yy",
        },
    )
    resp = client.get("/marketplace", params={"category": "electronics"})
    assert resp.status_code == 200
    listings = resp.json()["listings"]
    assert len(listings) == 1
    assert listings[0]["item_id"] == item_id


# ---------------------------------------------------------------------------
# simulated checkout
# ---------------------------------------------------------------------------


def test_buy_emits_sold_and_marks_item_sold(client, harness):
    """Req 15.5, 18.4: simulated checkout transitions to SOLD and emits SOLD."""
    item_id = _create_item(client)
    _seed_grade(harness, item_id)
    client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": "electronics",
            "price": "120.00",
            "geohash5": "9q8yy",
        },
    )

    resp = client.post(f"/listings/{item_id}/buy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "SOLD"
    assert body["simulated"] is True
    assert body["order_id"]

    sold = harness.publisher.events_of("SOLD")
    assert len(sold) == 1 and sold[0].item_id == item_id
    # The item's lifecycle status is now SOLD.
    assert client.get(f"/items/{item_id}").json()["meta"]["status"] == "SOLD"


def test_buy_unknown_listing_404(client):
    item_id = _create_item(client)  # graded? no listing -> 404
    resp = client.post(f"/listings/{item_id}/buy")
    assert resp.status_code == 404
