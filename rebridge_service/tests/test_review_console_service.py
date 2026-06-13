"""Unit tests for the ReviewConsoleService (task 13.1).

Covers Requirement 14:
- 14.1: the queue lists pending grades ordered by value x uncertainty desc.
- 14.2: confirm persists the grade as confirmed and sets status GRADED.
- 14.3: override persists the overriding grade, sets GRADED, and stores a
  training signal; confirm/override both remove the Item from the queue.
- 14.4: confirm/override on an Item not in the queue is rejected with a
  not-pending-review error.

These exercise real business logic against the in-memory fakes (no AWS calls).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from rebridge_data.models import (
    GradeRecord,
    ItemMeta,
    ItemStatus,
    ReviewQueueEntry,
)
from rebridge_service.review_console_service import (
    InMemoryTrainingSignalSink,
    MissingGrade,
    NotPendingReview,
    ReviewConsoleService,
    TrainingSignal,
)

from .fakes import FakeItemRepository, FakeReviewQueueRepository


def _grade(grade: str = "Good", confidence: float = 0.4) -> GradeRecord:
    return GradeRecord(grade=grade, confidence=confidence, summary=f"{grade} item")


def _seed_pending(
    items: FakeItemRepository,
    queue: FakeReviewQueueRepository,
    item_id: str,
    *,
    value: Decimal,
    confidence: float,
    grade: str = "Good",
) -> GradeRecord:
    """Seed an Item in PENDING_REVIEW with a grade and a queue entry."""

    meta = ItemMeta(
        item_id=item_id,
        status=ItemStatus.PENDING_REVIEW,
        category="electronics",
        age_months=12,
        context_source="manual",
        created_at="2024-01-01T00:00:00Z",
    )
    items.put_item_meta(meta)
    grade_record = _grade(grade=grade, confidence=confidence)
    items.put_grade(item_id, grade_record)
    queue.enqueue(
        ReviewQueueEntry(
            item_id=item_id,
            value=value,
            confidence=confidence,
            priority=float(value) * (1.0 - confidence),
            grade=grade_record,
        )
    )
    return grade_record


def _service() -> tuple[ReviewConsoleService, FakeItemRepository, FakeReviewQueueRepository, InMemoryTrainingSignalSink]:
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    sink = InMemoryTrainingSignalSink()
    svc = ReviewConsoleService(items, queue, training_sink=sink)
    return svc, items, queue, sink


# -- 14.1: ordering --------------------------------------------------------
def test_list_pending_orders_by_value_times_uncertainty_desc():
    svc, items, queue, _ = _service()
    # priority = value * (1 - confidence)
    # low:  value 100, conf 0.9  -> 10.0
    # mid:  value 100, conf 0.5  -> 50.0
    # high: value 400, conf 0.7  -> 120.0
    _seed_pending(items, queue, "low", value=Decimal("100"), confidence=0.9)
    _seed_pending(items, queue, "mid", value=Decimal("100"), confidence=0.5)
    _seed_pending(items, queue, "high", value=Decimal("400"), confidence=0.7)

    ordered = svc.list_pending()
    ids = [e.item_id for e in ordered]
    assert ids == ["high", "mid", "low"]
    priorities = [e.priority for e in ordered]
    assert priorities == sorted(priorities, reverse=True)


def test_list_pending_respects_limit():
    svc, items, queue, _ = _service()
    _seed_pending(items, queue, "a", value=Decimal("100"), confidence=0.9)
    _seed_pending(items, queue, "b", value=Decimal("100"), confidence=0.5)
    _seed_pending(items, queue, "c", value=Decimal("100"), confidence=0.1)

    top = svc.list_pending(limit=2)
    assert len(top) == 2
    assert [e.item_id for e in top] == ["c", "b"]


def test_list_pending_empty_queue_returns_empty():
    svc, _, _, _ = _service()
    assert svc.list_pending() == []


# -- 14.2: confirm ---------------------------------------------------------
def test_confirm_persists_confirmed_grade_and_sets_graded():
    svc, items, queue, _ = _service()
    _seed_pending(items, queue, "item-1", value=Decimal("200"), confidence=0.4)

    result = svc.confirm("item-1")

    assert result.confirmed is True
    stored = items.get_grade("item-1")
    assert stored.confirmed is True
    assert items.get_item("item-1").meta.status is ItemStatus.GRADED
    # Removed from the queue (14.2 + transition removes the item).
    assert queue.get("item-1") is None


def test_confirm_preserves_grade_value():
    svc, items, queue, _ = _service()
    _seed_pending(items, queue, "item-1", value=Decimal("200"), confidence=0.4, grade="Very Good")

    result = svc.confirm("item-1")
    assert result.grade == "Very Good"


# -- 14.3: override --------------------------------------------------------
def test_override_persists_new_grade_sets_graded_and_records_signal():
    svc, items, queue, sink = _service()
    _seed_pending(items, queue, "item-2", value=Decimal("300"), confidence=0.3, grade="Good")

    new_grade = GradeRecord(grade="Acceptable", confidence=1.0, summary="reviewer override")
    result = svc.override("item-2", new_grade)

    # Overriding grade persisted (confirmed) and status GRADED.
    assert result.grade == "Acceptable"
    assert result.confirmed is True
    stored = items.get_grade("item-2")
    assert stored.grade == "Acceptable"
    assert items.get_item("item-2").meta.status is ItemStatus.GRADED
    # Removed from the queue.
    assert queue.get("item-2") is None

    # Training signal recorded: original vs overriding grade.
    assert len(sink.signals) == 1
    signal = sink.signals[0]
    assert isinstance(signal, TrainingSignal)
    assert signal.item_id == "item-2"
    assert signal.original_grade.grade == "Good"
    assert signal.overriding_grade.grade == "Acceptable"


def test_override_default_sink_collects_signal():
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    svc = ReviewConsoleService(items, queue)  # default InMemory sink
    _seed_pending(items, queue, "item-3", value=Decimal("50"), confidence=0.2)

    svc.override("item-3", GradeRecord(grade="Unsellable", confidence=0.95, summary="x"))
    assert len(svc.training_sink.signals) == 1


# -- 14.4: rejection -------------------------------------------------------
def test_confirm_non_pending_item_raises_not_pending_review():
    svc, items, _, _ = _service()
    # Item exists and is graded, but is NOT in the review queue.
    items.put_item_meta(
        ItemMeta(
            item_id="not-pending",
            status=ItemStatus.GRADED,
            category="electronics",
            age_months=6,
            context_source="manual",
            created_at="2024-01-01T00:00:00Z",
        )
    )
    with pytest.raises(NotPendingReview) as exc:
        svc.confirm("not-pending")
    assert exc.value.item_id == "not-pending"


def test_override_non_pending_item_raises_not_pending_review():
    svc, _, _, sink = _service()
    with pytest.raises(NotPendingReview):
        svc.override("ghost", GradeRecord(grade="Good", confidence=0.9, summary="x"))
    # No training signal recorded on a rejected action.
    assert sink.signals == []


def test_confirm_twice_second_call_rejected():
    svc, items, queue, _ = _service()
    _seed_pending(items, queue, "item-4", value=Decimal("100"), confidence=0.5)
    svc.confirm("item-4")
    with pytest.raises(NotPendingReview):
        svc.confirm("item-4")


def test_override_validates_grade_type():
    svc, items, queue, _ = _service()
    _seed_pending(items, queue, "item-5", value=Decimal("100"), confidence=0.5)
    with pytest.raises(ValueError):
        svc.override("item-5", "not-a-grade-record")  # type: ignore[arg-type]


def test_confirm_falls_back_to_entry_grade_when_facet_absent():
    # Defensive path: queue entry carries the grade snapshot but the GRADE
    # facet is somehow absent; confirm uses the snapshot.
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    svc = ReviewConsoleService(items, queue)
    items.put_item_meta(
        ItemMeta(
            item_id="snap",
            status=ItemStatus.PENDING_REVIEW,
            category="electronics",
            age_months=6,
            context_source="manual",
            created_at="2024-01-01T00:00:00Z",
        )
    )
    snapshot = GradeRecord(grade="Good", confidence=0.4, summary="snap")
    queue.enqueue(
        ReviewQueueEntry(
            item_id="snap",
            value=Decimal("100"),
            confidence=0.4,
            priority=60.0,
            grade=snapshot,
        )
    )
    result = svc.confirm("snap")
    assert result.grade == "Good"
    assert result.confirmed is True


def test_confirm_missing_grade_entirely_raises():
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    svc = ReviewConsoleService(items, queue)
    items.put_item_meta(
        ItemMeta(
            item_id="bare",
            status=ItemStatus.PENDING_REVIEW,
            category="electronics",
            age_months=6,
            context_source="manual",
            created_at="2024-01-01T00:00:00Z",
        )
    )
    queue.enqueue(
        ReviewQueueEntry(
            item_id="bare",
            value=Decimal("100"),
            confidence=0.4,
            priority=60.0,
            grade=None,
        )
    )
    with pytest.raises(MissingGrade):
        svc.confirm("bare")
