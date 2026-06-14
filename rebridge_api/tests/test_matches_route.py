"""API tests for GET /items/{item_id}/matches (G1).

Exercises the matches route against real service-layer logic (the
DemandMatchingEngine over a seeded persona repo) wired through the test harness:
- a graded item returns ranked matches with intent_tier/distance/reasons;
- match_count_within_5km counts matches within 5 km;
- an ungraded item returns an empty result;
- an unknown item is a 404;
- the route requires authentication.
"""

from __future__ import annotations

from rebridge_data.models import ItemStatus

from tests.conftest import Harness


def _graded_item(client, harness: Harness, *, category="electronics") -> str:
    resp = client.post(
        "/items",
        json={"context_source": "manual", "category": category, "age_months": 10},
    )
    assert resp.status_code == 201, resp.text
    item_id = resp.json()["item_id"]
    from rebridge_data.models import GradeRecord

    harness.item_repo.put_grade(
        item_id, GradeRecord(grade="Good", confidence=0.9, summary="solid")
    )
    harness.item_repo.update_status(item_id, ItemStatus.GRADED)
    return item_id


def test_matches_for_graded_item_returns_ranked_matches(client, harness):
    item_id = _graded_item(client, harness, category="electronics")

    resp = client.get(f"/items/{item_id}/matches")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["item_id"] == item_id
    assert body["generated_at"]
    assert len(body["matches"]) >= 1
    # electronics personas: buy_001 (deal_seeker), buy_002 (price_balker),
    # buy_003 (browser) all carry "electronics" interest.
    buyer_ids = {m["buyer_id"] for m in body["matches"]}
    assert {"buy_001", "buy_002", "buy_003"} <= buyer_ids

    top = body["matches"][0]
    assert top["intent_tier"] in {"HIGH", "MEDIUM", "LOW"}
    assert isinstance(top["distance_km"], (int, float))
    assert isinstance(top["match_score"], (int, float))
    assert top["display_label"].startswith("Buyer ")
    assert len(top["match_reasons"]) >= 1
    # Top match wishlisted electronics, so the leading reason is the wishlist one.
    assert top["match_reasons"][0] == "wishlisted this product"
    assert body["top_reason"] == "wishlisted this product"


def test_match_count_within_5km_is_consistent(client, harness):
    item_id = _graded_item(client, harness, category="electronics")
    body = client.get(f"/items/{item_id}/matches").json()
    expected = sum(1 for m in body["matches"] if m["distance_km"] <= 5.0)
    assert body["match_count_within_5km"] == expected


def test_matches_for_ungraded_item_is_empty(client, harness):
    resp = client.post(
        "/items",
        json={"context_source": "manual", "category": "electronics", "age_months": 5},
    )
    item_id = resp.json()["item_id"]

    body = client.get(f"/items/{item_id}/matches").json()
    assert body["matches"] == []
    assert body["match_count_within_5km"] == 0
    assert body["top_reason"] is None


def test_matches_for_unknown_item_404(client):
    resp = client.get("/items/does-not-exist/matches")
    assert resp.status_code == 404


def test_matches_requires_auth(harness):
    # A client without the auth override must be rejected (no verifier wired).
    from fastapi.testclient import TestClient

    app = harness.app
    app.dependency_overrides.clear()
    unauth = TestClient(app)
    resp = unauth.get("/items/whatever/matches")
    assert resp.status_code == 401
