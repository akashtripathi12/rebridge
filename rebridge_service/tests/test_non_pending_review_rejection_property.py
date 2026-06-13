"""Property-based test for rejecting review actions on non-pending Items.

# Feature: rebridge-backend, Property 26: Review action on non-pending item is rejected

Property 26 (design.md): *For any* Item not in the Review_Queue, a confirm or
override action SHALL be rejected with a not-pending-review error.

**Validates: Requirements 14.4**

The only thing that makes an Item "pending review" is the presence of a queue
entry for it. This test drives arbitrary target item ids that are NOT in the
queue -- including items that exist in the store but were never enqueued (any
lifecycle status) and items that are wholly unknown -- and asserts that both
``confirm`` and ``override`` raise :class:`NotPendingReview` carrying the
target id. It further asserts the rejection is a pure no-op: no GRADE facet or
META status changes, no entry is added to the queue, and no override training
signal is recorded.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import GradeRecord, ItemMeta, ItemStatus

from rebridge_service.review_console_service import (
    NotPendingReview,
    ReviewConsoleService,
)

from .fakes import FakeItemRepository, FakeReviewQueueRepository

# Item-id alphabet shared by seeded and target ids so that an unknown target is
# drawn from the same space as the seeded ids (it just may or may not collide).
_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789-"
_item_ids = st.text(alphabet=_ID_ALPHABET, min_size=1, max_size=12)

# Any lifecycle status -- crucially PENDING_REVIEW is allowed too: an Item may
# carry the PENDING_REVIEW status yet have no queue entry, and it must still be
# rejected because "pending" is defined by queue membership, not the status.
_statuses = st.sampled_from(list(ItemStatus))

_grades = st.sampled_from(["Good", "Very Good", "Acceptable", "Unsellable"])
_confidences = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)

# A seeded (existing but un-enqueued) Item: id, status, grade label, confidence.
_seed_items = st.lists(
    st.tuples(_item_ids, _statuses, _grades, _confidences),
    unique_by=lambda t: t[0],
    max_size=12,
)


def _seed(items: FakeItemRepository, seed_items) -> None:
    """Persist each seeded Item's META + GRADE facet (no queue entry)."""

    for item_id, status, grade, confidence in seed_items:
        items.put_item_meta(
            ItemMeta(
                item_id=item_id,
                status=status,
                category="electronics",
                age_months=12,
                context_source="manual",
                created_at="2024-01-01T00:00:00Z",
            )
        )
        items.put_grade(
            item_id,
            GradeRecord(grade=grade, confidence=confidence, summary=f"{grade} item"),
        )


@settings(max_examples=200)
@given(
    seed_items=_seed_items,
    target=_item_ids,
    use_existing=st.booleans(),
    data=st.data(),
)
def test_review_action_on_non_pending_item_is_rejected(
    seed_items, target, use_existing, data
):
    items = FakeItemRepository()
    queue = FakeReviewQueueRepository()
    svc = ReviewConsoleService(items, queue)
    _seed(items, seed_items)

    # Choose the target id. Either an existing-but-not-enqueued Item (to cover
    # "exists but not pending") or the arbitrary `target` id (often unknown).
    if use_existing and seed_items:
        target_id = data.draw(st.sampled_from([s[0] for s in seed_items]))
    else:
        target_id = target

    # Precondition for this property: the target is NOT in the Review_Queue.
    assert queue.get(target_id) is None

    # Snapshot the full store state so we can prove the rejection is a no-op.
    before_meta = {
        s[0]: items.get_item(s[0]).meta.status for s in seed_items
    }
    before_grades = {s[0]: items.get_grade(s[0]) for s in seed_items}

    override_grade = GradeRecord(
        grade="Acceptable", confidence=1.0, summary="reviewer override"
    )

    # 1) confirm is rejected with a not-pending-review error carrying the id.
    try:
        svc.confirm(target_id)
        raised_confirm = False
    except NotPendingReview as exc:
        raised_confirm = True
        assert exc.item_id == target_id
    assert raised_confirm, "confirm() must reject a non-pending item"

    # 2) override is likewise rejected with the same error.
    try:
        svc.override(target_id, override_grade)
        raised_override = False
    except NotPendingReview as exc:
        raised_override = True
        assert exc.item_id == target_id
    assert raised_override, "override() must reject a non-pending item"

    # 3) No state change: META status and GRADE facet are untouched for every
    #    seeded Item, and an unknown target gained neither facet.
    for item_id, status in before_meta.items():
        assert items.get_item(item_id).meta.status == status
    for item_id, grade in before_grades.items():
        assert items.get_grade(item_id) == grade
    if target_id not in before_meta:
        assert items.get_item(target_id) is None
        assert items.get_grade(target_id) is None

    # 4) Nothing was enqueued and no override training signal was recorded.
    assert queue.get(target_id) is None
    assert svc.training_sink.signals == []
