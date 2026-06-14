"""API tests for the review queue routes (G2).

Exercises GET /review/queue and POST /review/{item_id} against real
service-layer logic (ReviewConsoleService over fake item + review-queue repos):
- the queue returns sorted items with priority tiers and a total;
- CONFIRM advances the item to GRADED and returns the aggregate;
- OVERRIDE returns the overriding grade in the aggregate;
- an action on a non-pending item is a 409;
- an invalid override grade is a 422.
"""

from __future__ import annotations

from decimal import Decimal

from rebridge_data.models import (
    GradeRecord,
    ItemMeta,
    ItemStatus,
    ReviewQueueEntry,
)

from tests.conftest import Harness


def _seed_pending(
    harness: Harness,
    item_id: str,
    *,
    value: str,
    confidence: float,
    grade: str = "Good",
    category: str = "electronics",
    created_at: str = "2026-06-14T08:40:00Z",
) -> None:
    harness.item_repo.put_item_meta(
        ItemMeta(
            item_id=item_id,
            status=ItemStatus.PENDING_REVIEW,
            category=category,
            age_months=12,
            context_source="manual",
            created_at=created_at,
        )
    )
    grade_record = GradeRecord(grade=grade, confidence=confidence, summary="ai grade")
    harness.item_repo.put_grade(item_id, grade_record)
    value_dec = Decimal(value)
    harness.review_repo.enqueue(
        ReviewQueueEntry(
            item_id=item_id,
            value=value_dec,
            confidence=confidence,
            priority=float(value_dec) * (1.0 - confidence),
            grade=grade_record,
        )
    )


def test_queue_returns_sorted_items_with_tiers_and_total(client, harness):
    _seed_pending(harness, "itm_mixer", value="1900.00", confidence=0.64)   # 684 HIGH
    _seed_pending(harness, "itm_case", value="240.00", confidence=0.77)     # 55 MEDIUM
    _seed_pending(harness, "itm_low", value="100.00", confidence=0.95)      # 5 LOW

    resp = client.get("/review/queue")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 3
    order = [q["item_id"] for q in body["queue"]]
    assert order == ["itm_mixer", "itm_case", "itm_low"]

    mixer = body["queue"][0]
    assert mixer["priority"] == "HIGH"
    assert mixer["ai_grade"] == "Good"
    assert mixer["confidence"] == 0.64
    assert mixer["est_value"] == "1900.00"
    assert mixer["title"] == "electronics"
    assert mixer["created_at"] == "2026-06-14T08:40:00Z"
    assert mixer["photo_keys"] == ["items/itm_mixer/photo-1"]

    assert body["queue"][1]["priority"] == "MEDIUM"
    assert body["queue"][2]["priority"] == "LOW"


def test_confirm_advances_to_graded_and_returns_aggregate(client, harness):
    _seed_pending(harness, "itm_x", value="1000.00", confidence=0.6, grade="Good")

    resp = client.post("/review/itm_x", json={"action": "CONFIRM", "override_grade": None})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["status"] == "GRADED"
    assert body["grade"]["grade"] == "Good"
    assert body["grade"]["confirmed"] is True
    # Removed from the queue.
    assert harness.review_repo.get("itm_x") is None


def test_override_returns_overriding_grade(client, harness):
    _seed_pending(harness, "itm_y", value="1000.00", confidence=0.6, grade="Good")

    resp = client.post(
        "/review/itm_y",
        json={"action": "OVERRIDE", "override_grade": "Very Good"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["status"] == "GRADED"
    assert body["grade"]["grade"] == "Very Good"
    # Carries the original confidence/summary forward.
    assert body["grade"]["confidence"] == 0.6


def test_action_on_non_pending_item_409(client, harness):
    # Item exists but is not in the review queue.
    harness.item_repo.put_item_meta(
        ItemMeta(
            item_id="itm_np",
            status=ItemStatus.GRADED,
            category="electronics",
            age_months=12,
            context_source="manual",
            created_at="2026-06-14T08:40:00Z",
        )
    )
    resp = client.post("/review/itm_np", json={"action": "CONFIRM", "override_grade": None})
    assert resp.status_code == 409


def test_invalid_override_grade_422(client, harness):
    _seed_pending(harness, "itm_bad", value="1000.00", confidence=0.6)
    resp = client.post(
        "/review/itm_bad",
        json={"action": "OVERRIDE", "override_grade": "Excellent"},
    )
    assert resp.status_code == 422


def test_invalid_action_422(client, harness):
    _seed_pending(harness, "itm_act", value="1000.00", confidence=0.6)
    resp = client.post("/review/itm_act", json={"action": "MAYBE", "override_grade": None})
    assert resp.status_code == 422


def test_queue_requires_auth(harness):
    from fastapi.testclient import TestClient

    app = harness.app
    app.dependency_overrides.clear()
    unauth = TestClient(app)
    assert unauth.get("/review/queue").status_code == 401
