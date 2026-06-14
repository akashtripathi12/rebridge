"""ReviewConsoleService: the human review console business logic.

This implements the ``Review_Console_API`` service slice (design.md →
"Components and Interfaces → Service Layer → ReviewConsoleService") for
Requirement 14. It is programmed entirely against the abstract
:mod:`rebridge_data.interfaces` (``ReviewQueueRepository`` and
``ItemRepository``) and never imports boto3 or any web framework.

Responsibilities implemented here (task 13.1):

* List pending low-confidence grades ordered by *value x uncertainty* —
  ``value * (1 - confidence)`` — descending. The ``ReviewQueueRepository``
  already returns entries ordered by ``priority`` descending; this service
  surfaces that ordering (Requirement 14.1).
* **Confirm** a pending grade: persist the existing GRADE facet as confirmed
  (``GradeRecord.confirmed = True``), set the Item status to ``GRADED``, and
  remove the Item from the Review_Queue (Requirement 14.2).
* **Override** a pending grade: persist the overriding grade, set the Item
  status to ``GRADED``, store the override as a *training signal* (the original
  grade paired with the overriding grade), and remove the Item from the
  Review_Queue (Requirement 14.3).
* Reject a confirm or override action for an Item that is **not** in the
  Review_Queue with a not-pending-review error (Requirement 14.4).

### Training-signal sink

The override action records a :class:`TrainingSignal` (original vs overriding
grade) so corrections can feed future model training. The sink is an injected
seam: a default :class:`InMemoryTrainingSignalSink` collects signals in a list
for tests and local runs; the composition root may inject a durable sink later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from decimal import Decimal

from rebridge_data.interfaces import ItemRepository, ReviewQueueRepository
from rebridge_data.models import GradeRecord, ItemStatus, ReviewQueueEntry

__all__ = [
    "ReviewConsoleError",
    "NotPendingReview",
    "MissingGrade",
    "TrainingSignal",
    "TrainingSignalSink",
    "InMemoryTrainingSignalSink",
    "ReviewQueueItemView",
    "ReviewConsoleService",
]

# Default page size when a caller does not specify one for ``list_pending``.
DEFAULT_QUEUE_LIMIT = 50

# Priority-tier cutoffs applied to the queue entry's priority score
# (value * (1 - confidence)). Documented, configurable module constants so the
# demo data lands as intended (e.g. 1900*0.36=684 -> HIGH, 240*0.23=55 ->
# MEDIUM). A score at or above HIGH is HIGH; at or above MEDIUM is MEDIUM; else
# LOW.
PRIORITY_HIGH_CUTOFF: float = 300.0
PRIORITY_MEDIUM_CUTOFF: float = 50.0


class ReviewConsoleError(Exception):
    """Base class for all errors raised by :class:`ReviewConsoleService`."""


class NotPendingReview(ReviewConsoleError):
    """A confirm/override action targeted an Item that is not pending review.

    Validates Requirement 14.4: a confirm or override action for an Item that is
    not in the Review_Queue is rejected with a not-pending-review error.
    """

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"item {item_id!r} is not pending review")


class MissingGrade(ReviewConsoleError):
    """A pending Item unexpectedly has no grade to confirm.

    This is a defensive guard: an Item only enters the Review_Queue after a
    grade has been produced, so a confirm with neither a persisted GRADE facet
    nor a grade snapshot on the queue entry indicates an inconsistent store.
    """

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"item {item_id!r} is pending review but has no grade")


@dataclass
class TrainingSignal:
    """An override training signal: the original grade vs the human correction.

    Stored on every override (Requirement 14.3) so that reviewer corrections can
    feed future model training. ``original_grade`` is the grade the
    Grading_Engine produced (``None`` only if it could not be recovered);
    ``overriding_grade`` is the reviewer-supplied replacement that was persisted.
    """

    item_id: str
    original_grade: GradeRecord | None
    overriding_grade: GradeRecord


class TrainingSignalSink(ABC):
    """Seam for persisting override :class:`TrainingSignal` records."""

    @abstractmethod
    def record(self, signal: TrainingSignal) -> None:
        """Store an override training signal."""


class InMemoryTrainingSignalSink(TrainingSignalSink):
    """Default in-memory sink that collects training signals in a list.

    Suitable for tests and local runs; the composition root may substitute a
    durable sink without changing :class:`ReviewConsoleService`.
    """

    def __init__(self) -> None:
        self.signals: list[TrainingSignal] = []

    def record(self, signal: TrainingSignal) -> None:
        self.signals.append(signal)


@dataclass(frozen=True)
class ReviewQueueItemView:
    """A review-queue entry joined with item meta for the queue API (G2).

    ``est_value`` carries the queue entry's value (rendered as a money string at
    the transport boundary); ``priority`` is the server-computed tier
    (HIGH/MEDIUM/LOW); ``photo_keys`` is synthesized for the demo; ``title`` and
    ``created_at`` come from the item's META facet.
    """

    item_id: str
    title: str
    ai_grade: str
    confidence: float
    est_value: Decimal
    priority: str
    photo_keys: tuple[str, ...]
    created_at: str


class ReviewConsoleService:
    """Lists the Review_Queue and applies confirm/override actions.

    Collaborators (injected, all abstract): a
    :class:`~rebridge_data.interfaces.ReviewQueueRepository` for the prioritized
    queue, an :class:`~rebridge_data.interfaces.ItemRepository` for the GRADE
    facet and lifecycle status, and a :class:`TrainingSignalSink` for override
    signals (defaults to an :class:`InMemoryTrainingSignalSink`).
    """

    def __init__(
        self,
        item_repo: ItemRepository,
        review_repo: ReviewQueueRepository,
        training_sink: TrainingSignalSink | None = None,
    ) -> None:
        self._items = item_repo
        self._queue = review_repo
        self._sink: TrainingSignalSink = training_sink or InMemoryTrainingSignalSink()

    @property
    def training_sink(self) -> TrainingSignalSink:
        """The sink that receives override training signals."""

        return self._sink

    def list_pending(self, limit: int = DEFAULT_QUEUE_LIMIT) -> list[ReviewQueueEntry]:
        """Return pending entries ordered by priority (value x uncertainty) desc.

        The ``ReviewQueueRepository`` already orders entries by ``priority``
        descending, where ``priority = value * (1 - confidence)``; this method
        surfaces that ordering directly (Requirement 14.1). ``limit`` bounds the
        number of entries returned.
        """

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError(f"limit must be an int, got {type(limit).__name__}")
        if limit < 0:
            raise ValueError(f"limit must be non-negative, got {limit}")
        return self._queue.list_pending(limit)

    def list_pending_view(
        self, limit: int = DEFAULT_QUEUE_LIMIT
    ) -> list[ReviewQueueItemView]:
        """Return pending entries joined with item meta for the queue API (G2).

        Surfaces :meth:`list_pending` (already priority-desc, Requirement 14.1)
        and, for each entry, joins the item's META facet to fill ``title`` and
        ``created_at``, computes the server-side priority tier from the entry's
        priority score (``value * (1 - confidence)``), and synthesizes a demo
        ``photo_keys`` list. ``ai_grade``/``confidence``/``est_value`` come from
        the queue entry. The descending priority ordering is preserved.
        """

        entries = self.list_pending(limit)
        views: list[ReviewQueueItemView] = []
        for entry in entries:
            aggregate = self._items.get_item(entry.item_id)
            meta = aggregate.meta if aggregate is not None else None
            grade = entry.grade if entry.grade is not None else self._items.get_grade(
                entry.item_id
            )
            views.append(
                ReviewQueueItemView(
                    item_id=entry.item_id,
                    title=meta.category if meta is not None else "",
                    ai_grade=grade.grade if grade is not None else "",
                    confidence=entry.confidence,
                    est_value=entry.value,
                    priority=self._priority_tier(entry.priority),
                    photo_keys=(f"items/{entry.item_id}/photo-1",),
                    created_at=meta.created_at if meta is not None else "",
                )
            )
        return views

    @staticmethod
    def _priority_tier(priority_score: float) -> str:
        """Map a priority score (value x uncertainty) to a HIGH/MEDIUM/LOW tier."""

        if priority_score >= PRIORITY_HIGH_CUTOFF:
            return "HIGH"
        if priority_score >= PRIORITY_MEDIUM_CUTOFF:
            return "MEDIUM"
        return "LOW"

    def confirm(self, item_id: str) -> GradeRecord:
        """Confirm the pending grade for ``item_id`` (Requirement 14.2).

        Persists the existing grade as confirmed, sets the Item status to
        ``GRADED``, removes the Item from the Review_Queue, and returns the
        confirmed grade. Raises :class:`NotPendingReview` if the Item is not in
        the queue (Requirement 14.4).
        """

        entry = self._require_pending(item_id)
        current = self._current_grade(item_id, entry)
        confirmed = replace(current, confirmed=True)
        self._items.put_grade(item_id, confirmed)
        self._items.update_status(item_id, ItemStatus.GRADED)
        self._queue.resolve(item_id)
        return confirmed

    def override(self, item_id: str, new_grade: GradeRecord) -> GradeRecord:
        """Override the pending grade for ``item_id`` (Requirement 14.3).

        Persists ``new_grade`` (marked confirmed, as it is a human-verified
        correction), sets the Item status to ``GRADED``, records an override
        :class:`TrainingSignal` pairing the original grade with the override,
        removes the Item from the Review_Queue, and returns the persisted
        overriding grade. Raises :class:`NotPendingReview` if the Item is not in
        the queue (Requirement 14.4).
        """

        if not isinstance(new_grade, GradeRecord):
            raise ValueError(
                f"new_grade must be a GradeRecord, got {type(new_grade).__name__}"
            )
        entry = self._require_pending(item_id)
        # Recover the original grade for the training signal before overwriting.
        original = self._items.get_grade(item_id)
        if original is None:
            original = entry.grade
        overriding = replace(new_grade, confirmed=True)
        self._items.put_grade(item_id, overriding)
        self._items.update_status(item_id, ItemStatus.GRADED)
        self._sink.record(
            TrainingSignal(
                item_id=item_id,
                original_grade=original,
                overriding_grade=overriding,
            )
        )
        self._queue.resolve(item_id)
        return overriding

    # -- internals ---------------------------------------------------------
    def _require_pending(self, item_id: str) -> ReviewQueueEntry:
        """Return the pending queue entry or raise :class:`NotPendingReview`."""

        entry = self._queue.get(item_id)
        if entry is None:
            raise NotPendingReview(item_id)
        return entry

    def _current_grade(
        self, item_id: str, entry: ReviewQueueEntry
    ) -> GradeRecord:
        """Return the authoritative GRADE facet, falling back to the snapshot."""

        grade = self._items.get_grade(item_id)
        if grade is None:
            grade = entry.grade
        if grade is None:
            raise MissingGrade(item_id)
        return grade
