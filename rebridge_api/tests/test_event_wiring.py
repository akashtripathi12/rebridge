"""Composition-level lifecycle-event wiring tests.

These guard the runtime *connections* between services that unit tests (which
exercise each service in isolation with fakes) cannot catch:

* creating a listing must trigger the Demand_Matching_Engine end to end -- the
  top-N buyers are notified, the Item is placed on the Second-Chance shelf, and
  a MATCHED event is emitted (Requirements 13.5, 15.4); and
* confirming/overriding a grade in the human-review console must emit GRADED
  (Requirement 15.1), matching the auto-grade path.

They run against the wired ``Harness`` (Services container over in-memory fakes,
with Engine B wired with a notifier + shelf), so a regression that disconnects a
service from its event/side-effect would fail here.
"""

from __future__ import annotations

from decimal import Decimal

from rebridge_data.models import (
    GradeRecord,
    ItemMeta,
    ItemStatus,
    ReviewQueueEntry,
)


def _create_graded_item(client, harness, *, category: str = "electronics") -> str:
    """Create an item via the API and seed a grade so it can be listed."""
    resp = client.post(
        "/items",
        json={"context_source": "manual", "category": category, "age_months": 6},
    )
    assert resp.status_code == 201, resp.text
    item_id = resp.json()["item_id"]
    harness.item_repo.put_grade(
        item_id,
        GradeRecord(grade="Good", confidence=0.9, summary="light wear"),
    )
    return item_id


# ---------------------------------------------------------------------------
# Listing creation connects Engine B (notify + shelf + MATCHED)
# ---------------------------------------------------------------------------


def test_create_listing_triggers_match_notify_shelf_and_matched_event(client, harness):
    item_id = _create_graded_item(client, harness, category="electronics")

    resp = client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": "electronics",
            "price": "100.00",
            "geohash5": "9q8yy",
        },
    )
    assert resp.status_code == 201, resp.text

    # LISTED then MATCHED both emitted for this item.
    assert [e.item_id for e in harness.publisher.events_of("LISTED")] == [item_id]
    matched = harness.publisher.events_of("MATCHED")
    assert [e.item_id for e in matched] == [item_id]

    # Seeded electronics buyers in the 9q8yy neighborhood were notified...
    notified = harness.notifier.buyers_for(item_id)
    assert len(notified) >= 1
    assert set(notified) <= {"buy_001", "buy_002", "buy_003"}

    # ...and the Item was placed on the Second-Chance shelf exactly once.
    assert item_id in harness.shelf
    assert harness.shelf.upsert_counts[item_id] == 1


def test_create_listing_emits_matched_even_with_no_nearby_buyers(client, harness):
    # A neighborhood with no seeded personas still reaches its placement surface:
    # MATCHED + shelf upsert happen, just with zero notifications.
    item_id = _create_graded_item(client, harness, category="electronics")

    resp = client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": "electronics",
            "price": "100.00",
            "geohash5": "zzzzz",  # no seeded persona shares this prefix
        },
    )
    assert resp.status_code == 201, resp.text

    assert [e.item_id for e in harness.publisher.events_of("MATCHED")] == [item_id]
    assert harness.notifier.buyers_for(item_id) == []
    assert item_id in harness.shelf


# ---------------------------------------------------------------------------
# Human review emits GRADED (Requirement 15.1)
# ---------------------------------------------------------------------------


def _seed_pending_review(harness, item_id: str, *, grade: str = "Good", confidence=0.6):
    harness.item_repo.put_item_meta(
        ItemMeta(
            item_id=item_id,
            status=ItemStatus.PENDING_REVIEW,
            category="electronics",
            age_months=6,
            context_source="manual",
            created_at="2026-06-14T08:00:00+00:00",
        )
    )
    grade_record = GradeRecord(grade=grade, confidence=confidence, summary="uncertain")
    harness.item_repo.put_grade(item_id, grade_record)
    harness.review_repo.enqueue(
        ReviewQueueEntry(
            item_id=item_id,
            value=Decimal("100.00"),
            confidence=confidence,
            priority=float(Decimal("100.00")) * (1.0 - confidence),
            grade=grade_record,
        )
    )


def test_review_confirm_emits_graded(client, harness):
    item_id = "itm_review_confirm"
    _seed_pending_review(harness, item_id)

    resp = client.post(f"/review/{item_id}", json={"action": "CONFIRM", "override_grade": None})
    assert resp.status_code == 200, resp.text

    assert [e.item_id for e in harness.publisher.events_of("GRADED")] == [item_id]
    assert resp.json()["meta"]["status"] == "GRADED"


def test_review_override_emits_graded_and_applies_new_grade(client, harness):
    item_id = "itm_review_override"
    _seed_pending_review(harness, item_id, grade="Good")

    resp = client.post(
        f"/review/{item_id}",
        json={"action": "OVERRIDE", "override_grade": "Very Good"},
    )
    assert resp.status_code == 200, resp.text

    assert [e.item_id for e in harness.publisher.events_of("GRADED")] == [item_id]
    body = resp.json()
    assert body["meta"]["status"] == "GRADED"
    assert body["grade"]["grade"] == "Very Good"
