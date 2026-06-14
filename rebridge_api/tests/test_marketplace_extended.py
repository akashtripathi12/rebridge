"""API tests for the extended marketplace response (G3/G4/G9).

Verifies each listing now carries grade/distance_km/price_new/health_card_id/
title/thumb_key/listing_id alongside the existing fields, and that
``category=all`` returns listings across multiple categories.
"""

from __future__ import annotations

from rebridge_data.models import CardRecord, GradeRecord

from tests.conftest import Harness


def _list_item(client, harness: Harness, *, category: str, price: str, geohash5="9q8yy") -> str:
    resp = client.post(
        "/items",
        json={"context_source": "manual", "category": category, "age_months": 10},
    )
    item_id = resp.json()["item_id"]
    harness.item_repo.put_grade(
        item_id, GradeRecord(grade="Good", confidence=0.9, summary="solid")
    )
    created = client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": category,
            "price": price,
            "geohash5": geohash5,
        },
    )
    assert created.status_code == 201, created.text
    return item_id


def test_marketplace_listing_carries_enriched_fields(client, harness):
    item_id = _list_item(client, harness, category="electronics", price="340.00")
    # Attach a health card so health_card_id is populated.
    harness.item_repo.put_card(
        item_id,
        CardRecord(
            card_id="card_xyz",
            item_id=item_id,
            signature="sig",
            qr_target="https://verify/card_xyz",
            graded_at="2026-06-14T00:00:00Z",
            warranty_stance="as-is",
        ),
    )

    resp = client.get("/marketplace", params={"category": "electronics"})
    assert resp.status_code == 200, resp.text
    listing = resp.json()["listings"][0]

    assert listing["item_id"] == item_id
    assert listing["listing_id"] == f"lst_{item_id}"
    assert listing["grade"] == "Good"
    assert isinstance(listing["distance_km"], (int, float))
    assert listing["price"] == "340.00"
    # price_new = round(price * 1.5, 2) = 510.00
    assert listing["price_new"] == "510.00"
    assert listing["health_card_id"] == "card_xyz"
    assert listing["title"] == "electronics"
    assert listing["thumb_key"] == "electronics"
    assert listing["category"] == "electronics"


def test_marketplace_grade_and_card_null_when_absent(client, harness):
    # List an item without persisting a card; grade is present from listing flow.
    item_id = _list_item(client, harness, category="books", price="100.00")
    listing = client.get("/marketplace", params={"category": "books"}).json()["listings"][0]
    assert listing["grade"] == "Good"
    assert listing["health_card_id"] is None


def test_marketplace_distance_uses_geo_when_provided(client, harness):
    _list_item(client, harness, category="tech", price="200.00", geohash5="9q8yy")
    listing = client.get(
        "/marketplace", params={"category": "tech", "geo": "9q8yy"}
    ).json()["listings"][0]
    # Same geohash as the query -> zero distance.
    assert listing["distance_km"] == 0.0


def test_marketplace_category_all_returns_multiple_categories(client, harness):
    _list_item(client, harness, category="shoes", price="340.00")
    _list_item(client, harness, category="baby", price="500.00")
    _list_item(client, harness, category="tech", price="900.00")

    resp = client.get("/marketplace", params={"category": "all"})
    assert resp.status_code == 200, resp.text
    listings = resp.json()["listings"]
    categories = {listing["category"] for listing in listings}
    assert {"shoes", "baby", "tech"} <= categories
