"""Property-based test for review queue priority ordering.

# Feature: rebridge-backend, Property 24: Review queue priority ordering

Property 24 (design.md): *For any* set of pending grade records, the
Review_Console_API SHALL return them ordered non-increasing by value
multiplied by uncertainty (value x (1 - confidence)).

**Validates: Requirements 14.1**

The queue priority is ``value * (1 - confidence)``. This test enqueues an
arbitrary set of pending entries with varied value and confidence into the
in-memory :class:`FakeReviewQueueRepository`, then asserts that
``ReviewConsoleService.list_pending`` returns exactly those entries (a
permutation of the input) ordered non-increasing by ``value * (1 - confidence)``.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import GradeRecord, ReviewQueueEntry

from rebridge_service.review_console_service import ReviewConsoleService

from .fakes import FakeItemRepository, FakeReviewQueueRepository


def _uncertainty_priority(value: Decimal, confidence: float) -> float:
    """The queue ordering key: value x uncertainty = value * (1 - confidence)."""

    return float(value) * (1.0 - confidence)


# A single pending entry: a distinct item id, a non-negative value, and a
# confidence in [0, 1]. Confidence is bounded to the valid grade-confidence
# domain; value spans a wide non-negative range with cents precision.
_pending_entries = st.lists(
    st.tuples(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=1,
            max_size=12,
        ),
        st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("100000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    ),
    # Distinct item ids so the queue holds one entry per id (enqueue is keyed
    # by item id) and the result is a true permutation of the input set.
    unique_by=lambda triple: triple[0],
    max_size=40,
)


@settings(max_examples=200)
@given(entries=_pending_entries)
def test_list_pending_orders_by_value_times_uncertainty_desc(entries):
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    svc = ReviewConsoleService(items, queue)

    expected_ids = set()
    for item_id, value, confidence in entries:
        expected_ids.add(item_id)
        queue.enqueue(
            ReviewQueueEntry(
                item_id=item_id,
                value=value,
                confidence=confidence,
                priority=_uncertainty_priority(value, confidence),
                grade=GradeRecord(grade="Good", confidence=confidence, summary="x"),
            )
        )

    # Ask for at least as many as were enqueued so nothing is truncated.
    result = svc.list_pending(limit=len(entries) + 1)

    # 1) The result is a permutation of the enqueued set (no loss, no dupes).
    result_ids = [e.item_id for e in result]
    assert len(result_ids) == len(expected_ids)
    assert set(result_ids) == expected_ids

    # 2) Recomputing the ordering key from each returned entry yields a
    #    non-increasing sequence (ordered by value x uncertainty descending).
    keys = [_uncertainty_priority(e.value, e.confidence) for e in result]
    assert keys == sorted(keys, reverse=True)
