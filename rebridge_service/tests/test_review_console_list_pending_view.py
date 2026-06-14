"""Unit tests for ReviewConsoleService.list_pending_view (G2 queue view).

Covers the queue-view derivation layered on top of list_pending:
- entries are joined with item META for title + created_at;
- priority tier is computed from the entry priority (value x uncertainty) with
  the documented cutoffs (HIGH >= 300, MEDIUM >= 50, else LOW);
- ai_grade/confidence/est_value come from the queue entry;
- photo_keys are synthesized for the demo;
- the descending priority ordering is preserved.
"""

from __future__ import annotations

from decimal import Decimal

from rebridge_data.models import (
    GradeRecord,
    ItemMeta,
    ItemStatus,
    ReviewQueueEntry,
)

from rebridge_service.review_console_service import (
    ReviewConsoleService,
    ReviewQueueItemView,
)

from .fakes import FakeItemRepository, FakeReviewQueueRepository


def _seed(
    items: FakeItemRepository,
    queue: FakeReviewQueueRepository,
    item_id: str,
    *,
    value: str,
    confidence: float,
    grade: str = "Good",
    category: str = "electronics",
    created_at: str = "2026-06-14T08:40:00Z",
) -> None:
    items.put_item_meta(
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
    items.put_grade(item_id, grade_record)
    value_dec = Decimal(value)
    queue.enqueue(
        ReviewQueueEntry(
            item_id=item_id,
            value=value_dec,
            confidence=confidence,
            priority=float(value_dec) * (1.0 - confidence),
            grade=grade_record,
        )
    )


def _service() -> tuple[ReviewConsoleService, FakeItemRepository, FakeReviewQueueRepository]:
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    return ReviewConsoleService(items, queue), items, queue


def test_view_fields_and_priority_tiers_match_contract_examples():
    svc, items, queue = _service()
    # 1900 * (1 - 0.64) = 684 -> HIGH
    _seed(items, queue, "itm_mixer", value="1900.00", confidence=0.64, grade="Good")
    # 240 * (1 - 0.77) = 55.2 -> MEDIUM
    _seed(items, queue, "itm_case", value="240.00", confidence=0.77, grade="Like New")

    views = svc.list_pending_view()
    by_id = {v.item_id: v for v in views}

    mixer = by_id["itm_mixer"]
    assert isinstance(mixer, ReviewQueueItemView)
    assert mixer.priority == "HIGH"
    assert mixer.ai_grade == "Good"
    assert mixer.confidence == 0.64
    assert mixer.est_value == Decimal("1900.00")
    assert mixer.title == "electronics"
    assert mixer.created_at == "2026-06-14T08:40:00Z"
    assert mixer.photo_keys == ("items/itm_mixer/photo-1",)

    assert by_id["itm_case"].priority == "MEDIUM"


def test_low_priority_tier():
    svc, items, queue = _service()
    # 100 * (1 - 0.9) = 10 -> LOW
    _seed(items, queue, "itm_low", value="100.00", confidence=0.9)
    view = svc.list_pending_view()[0]
    assert view.priority == "LOW"


def test_ordering_is_priority_descending():
    svc, items, queue = _service()
    _seed(items, queue, "low", value="100.00", confidence=0.9)      # 10
    _seed(items, queue, "high", value="1900.00", confidence=0.64)   # 684
    _seed(items, queue, "mid", value="240.00", confidence=0.77)     # 55.2

    order = [v.item_id for v in svc.list_pending_view()]
    assert order == ["high", "mid", "low"]


def test_empty_queue_returns_empty_list():
    svc, _items, _queue = _service()
    assert svc.list_pending_view() == []
