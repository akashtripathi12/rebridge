"""Property-based test for review confirm/override transitions.

# Feature: rebridge-backend, Property 25: Review confirm and override transitions

Property 25 (design.md): *For any* Item pending review, confirming SHALL
persist the grade as confirmed and set status GRADED; overriding SHALL persist
the overriding grade, set status GRADED, and store an override training signal;
both SHALL remove the Item from the Review_Queue.

**Validates: Requirements 14.2, 14.3**

This drives :class:`ReviewConsoleService` against the in-memory fakes (no AWS
calls). For an arbitrary pending Item it asserts:

* **confirm** -> the persisted GRADE is marked ``confirmed``, the Item status is
  ``GRADED``, and the Item is removed from the Review_Queue (Requirement 14.2).
* **override** with an arbitrary new grade -> the overriding grade is persisted
  (and marked confirmed), the Item status is ``GRADED``, a training signal
  recording the original vs overriding grade is stored, and the Item is removed
  from the Review_Queue (Requirement 14.3).
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import (
    GradeRecord,
    ItemMeta,
    ItemStatus,
    ReviewQueueEntry,
)

from rebridge_service.review_console_service import (
    InMemoryTrainingSignalSink,
    ReviewConsoleService,
)

from .fakes import FakeItemRepository, FakeReviewQueueRepository

# The five allowed grade values (requirements glossary / Grade enum).
_GRADES = ["Like New", "Very Good", "Good", "Acceptable", "Unsellable"]

# A grade-confidence value in the valid closed interval [0, 1].
_confidence = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)

# A recoverable value: non-negative with cents precision.
_value = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100000"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# A short, non-empty item identifier.
_item_id = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=12,
)


def _seed_pending(
    items: FakeItemRepository,
    queue: FakeReviewQueueRepository,
    item_id: str,
    value: Decimal,
    confidence: float,
    grade: str,
) -> GradeRecord:
    """Seed an Item in PENDING_REVIEW with a grade and a queue entry."""

    items.put_item_meta(
        ItemMeta(
            item_id=item_id,
            status=ItemStatus.PENDING_REVIEW,
            category="electronics",
            age_months=12,
            context_source="manual",
            created_at="2024-01-01T00:00:00Z",
        )
    )
    grade_record = GradeRecord(
        grade=grade, confidence=confidence, summary=f"{grade} item"
    )
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


@settings(max_examples=200)
@given(
    item_id=_item_id,
    value=_value,
    confidence=_confidence,
    grade=st.sampled_from(_GRADES),
)
def test_confirm_persists_confirmed_grade_sets_graded_and_dequeues(
    item_id, value, confidence, grade
):
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    svc = ReviewConsoleService(items, queue)

    _seed_pending(items, queue, item_id, value, confidence, grade)

    result = svc.confirm(item_id)

    # Persisted grade is marked confirmed and preserves the original grade.
    assert result.confirmed is True
    assert result.grade == grade
    stored = items.get_grade(item_id)
    assert stored is not None
    assert stored.confirmed is True
    assert stored.grade == grade

    # Status transitioned to GRADED.
    assert items.get_item(item_id).meta.status is ItemStatus.GRADED

    # Item removed from the Review_Queue.
    assert queue.get(item_id) is None


@settings(max_examples=200)
@given(
    item_id=_item_id,
    value=_value,
    confidence=_confidence,
    original_grade=st.sampled_from(_GRADES),
    new_grade=st.sampled_from(_GRADES),
    new_confidence=_confidence,
)
def test_override_persists_new_grade_sets_graded_records_signal_and_dequeues(
    item_id, value, confidence, original_grade, new_grade, new_confidence
):
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    sink = InMemoryTrainingSignalSink()
    svc = ReviewConsoleService(items, queue, training_sink=sink)

    _seed_pending(items, queue, item_id, value, confidence, original_grade)

    overriding = GradeRecord(
        grade=new_grade, confidence=new_confidence, summary="reviewer override"
    )
    result = svc.override(item_id, overriding)

    # Overriding grade persisted (marked confirmed) and reflected in the store.
    assert result.grade == new_grade
    assert result.confirmed is True
    stored = items.get_grade(item_id)
    assert stored is not None
    assert stored.grade == new_grade
    assert stored.confirmed is True

    # Status transitioned to GRADED.
    assert items.get_item(item_id).meta.status is ItemStatus.GRADED

    # Exactly one training signal recording original vs overriding grade.
    assert len(sink.signals) == 1
    signal = sink.signals[0]
    assert signal.item_id == item_id
    assert signal.original_grade is not None
    assert signal.original_grade.grade == original_grade
    assert signal.overriding_grade.grade == new_grade

    # Item removed from the Review_Queue.
    assert queue.get(item_id) is None
