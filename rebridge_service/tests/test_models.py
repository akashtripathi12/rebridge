"""Unit tests for the framework-free service-layer domain models.

These cover the two invariants the task calls out explicitly:
- ``Grade`` has exactly the five allowed values (Requirement 5.1).
- ``GradeAssessment.confidence`` is a float in the closed interval [0, 1]
  (Requirement 5.4).
Plus light construction checks for the other models.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from rebridge_service.models import (
    BuyerPersona,
    CompletenessResult,
    Defect,
    Disposition,
    EventType,
    Grade,
    GradeAssessment,
    HealthCard,
    ItemStatus,
    LifecycleEvent,
    ListingRecord,
    ReviewQueueEntry,
    RoutingDecision,
)


def test_grade_has_exactly_five_allowed_values():
    assert {g.value for g in Grade} == {
        "Like New",
        "Very Good",
        "Good",
        "Acceptable",
        "Unsellable",
    }
    assert len(list(Grade)) == 5


def test_item_status_values():
    assert {s.name for s in ItemStatus} == {
        "CREATED",
        "RETAKE_REQUIRED",
        "GRADING",
        "PENDING_REVIEW",
        "GRADED",
        "LISTED",
        "SOLD",
    }


def test_disposition_values():
    assert {d.name for d in Disposition} == {"RESELL", "REFURB", "P2P", "DONATE"}


def _assessment(confidence: float) -> GradeAssessment:
    return GradeAssessment(
        grade=Grade.GOOD,
        defects=[Defect(location="corner", severity="minor")],
        completeness=CompletenessResult(is_complete=True),
        confidence=confidence,
        summary="Light wear on one corner.",
    )


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_accepts_closed_interval_bounds(confidence):
    assert _assessment(confidence).confidence == confidence


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0, -1.0])
def test_confidence_rejects_out_of_range(confidence):
    with pytest.raises(ValueError):
        _assessment(confidence)


def test_confidence_rejects_non_float():
    with pytest.raises(ValueError):
        _assessment("high")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _assessment(True)  # bool is not a valid confidence


def test_grade_assessment_rejects_non_grade():
    with pytest.raises(ValueError):
        GradeAssessment(
            grade="Good",  # type: ignore[arg-type]
            defects=[],
            completeness=CompletenessResult(is_complete=True),
            confidence=0.9,
            summary="x",
        )


def test_review_queue_entry_derives_priority():
    entry = ReviewQueueEntry(
        item_id="i1",
        grade=Grade.ACCEPTABLE,
        value=Decimal("100"),
        confidence=0.25,
    )
    assert entry.priority == pytest.approx(75.0)


def test_routing_decision_rejects_non_disposition():
    with pytest.raises(ValueError):
        RoutingDecision(
            disposition="RESELL",  # type: ignore[arg-type]
            price=Decimal("10"),
            value=Decimal("20"),
            cost=Decimal("5"),
            margin=Decimal("15"),
            rationale="value 20, cost 5, margin 15",
        )


def test_lifecycle_event_requires_event_type_enum():
    with pytest.raises(ValueError):
        LifecycleEvent(event_type="GRADED", item_id="i1")  # type: ignore[arg-type]
    evt = LifecycleEvent(
        event_type=EventType.ROUTED, item_id="i1", disposition=Disposition.RESELL
    )
    assert evt.disposition is Disposition.RESELL


def test_health_card_and_listing_construct():
    card = HealthCard(
        card_id="c1",
        item_id="i1",
        grade=Grade.LIKE_NEW,
        graded_at="2024-01-01T00:00:00Z",
        defect_summary="No visible defects.",
        warranty_stance="30-day",
        annotated_photo_keys=["k1", "k2"],
    )
    assert card.grade is Grade.LIKE_NEW

    listing = ListingRecord(
        item_id="i1",
        status="ACTIVE",
        category="electronics",
        price=Decimal("49.99"),
        geohash5="9q8yy",
        listed_at="2024-01-01T00:00:00Z",
    )
    assert listing.geohash5 == "9q8yy"


def test_buyer_persona_constructs():
    p = BuyerPersona(
        buyer_id="b1",
        geohash5="9q8yy",
        category="electronics",
        persona_type="deal-seeker",
        intent=0.8,
        lifecycle=0.5,
        geo=0.9,
        price_sensitivity=0.7,
        wishlist_categories=["electronics"],
    )
    assert p.persona_type == "deal-seeker"
