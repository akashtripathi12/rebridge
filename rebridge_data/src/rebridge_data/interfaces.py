"""Abstract data-layer interfaces.

These abstract base classes define the seams between the service layer and all
infrastructure (DynamoDB, S3, SQS, KMS, EventBridge, Bedrock, seeded buyer
data). The service layer is programmed entirely against these interfaces; the
composition root in ``rebridge_api`` is the only place concrete boto3-backed
implementations are constructed and injected.

This module MUST NOT import boto3 or any concrete AWS client. It declares
contracts only (Requirements 1.6, 8.4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from rebridge_data.models import (
    BuyerPersona,
    CardRecord,
    CatalogContext,
    DecisionRecord,
    GradeRecord,
    GradingMessage,
    ItemAggregate,
    ItemMeta,
    ItemStatus,
    LifecycleEvent,
    ListingPatch,
    ListingRecord,
    NotificationRecord,
    PresignedUrl,
    RawModelResponse,
    ReviewQueueEntry,
)

__all__ = [
    "ItemRepository",
    "ReviewQueueRepository",
    "NotificationRepository",
    "ObjectStore",
    "QueueClient",
    "CardSigner",
    "EventPublisher",
    "GradingProvider",
    "BuyerPersonaRepository",
    "BuyerNotifier",
    "SecondChanceShelf",
    "ConditionCheckFailed",
]


class ConditionCheckFailed(Exception):
    """Raised when an expected condition is not met during a write operation."""


class ItemRepository(ABC):
    """Single-table persistence for Items and their facets (Requirement 1.6)."""

    @abstractmethod
    def put_item_meta(self, item: ItemMeta) -> None:
        """Create or replace the META facet for an Item."""

    @abstractmethod
    def get_item(self, item_id: str) -> ItemAggregate | None:
        """Return the META facet plus every persisted facet, or None if unknown."""

    @abstractmethod
    def update_status(self, item_id: str, status: ItemStatus, expected_status: ItemStatus | None = None) -> None:
        """Update the lifecycle status on the META facet. If expected_status is provided, raise ConditionCheckFailed if it does not match."""

    @abstractmethod
    def put_grade(self, item_id: str, grade: GradeRecord) -> None:
        """Persist (create or replace) the GRADE facet."""

    @abstractmethod
    def get_grade(self, item_id: str) -> GradeRecord | None:
        """Return the GRADE facet, or None if not yet graded."""

    @abstractmethod
    def put_card(self, item_id: str, card: CardRecord) -> None:
        """Persist the CARD facet."""

    @abstractmethod
    def get_card(self, card_id: str) -> CardRecord | None:
        """Return a CARD facet by its card identifier, or None if unknown."""

    @abstractmethod
    def put_decision(self, item_id: str, decision: DecisionRecord) -> None:
        """Persist the DECISION facet."""

    @abstractmethod
    def put_listing(self, item_id: str, listing: ListingRecord) -> None:
        """Persist (create) the LISTING facet."""

    @abstractmethod
    def update_listing(self, item_id: str, patch: ListingPatch) -> ListingRecord:
        """Apply a partial update to the LISTING facet and return the new state."""

    @abstractmethod
    def get_listing(self, item_id: str) -> ListingRecord | None:
        """Return the LISTING facet, or None if there is none."""

    @abstractmethod
    def delete_listing(self, item_id: str) -> None:
        """Remove the LISTING facet for an Item."""

    @abstractmethod
    def query_marketplace(
        self,
        category: str,
        geo: str | None = None,
        limit: int = 50,
    ) -> list[ListingRecord]:
        """Query listed items for marketplace browse (GSI1/GSI2)."""

    @abstractmethod
    def batch_get_items(self, item_ids: list[str]) -> list[ItemAggregate]:
        """Fetch multiple items and all their facets in bulk."""

    @abstractmethod
    def put_grade_if_absent(
        self,
        item_id: str,
        idem_key: str,
        grade: GradeRecord,
    ) -> bool:
        """Idempotent conditional write of the GRADE facet.

        Returns ``True`` if the grade was written, or ``False`` if a grade for
        this idempotency key was already present and was therefore retained
        unchanged (Requirement 7.3).
        """


class ReviewQueueRepository(ABC):
    """Prioritized queue of low-confidence grades awaiting review (Requirement 14)."""

    @abstractmethod
    def enqueue(self, entry: ReviewQueueEntry) -> None:
        """Add an entry with priority = value * (1 - confidence)."""

    @abstractmethod
    def list_pending(self, limit: int) -> list[ReviewQueueEntry]:
        """Return pending entries ordered by priority descending (Requirement 14.1)."""

    @abstractmethod
    def get(self, item_id: str) -> ReviewQueueEntry | None:
        """Return the pending entry for an Item, or None if not pending."""

    @abstractmethod
    def resolve(self, item_id: str) -> None:
        """Remove an Item from the review queue."""


class ObjectStore(ABC):
    """Photo object storage gateway (S3) (Requirement 2)."""

    @abstractmethod
    def presign_put(self, key: str, ttl_seconds: int = 300) -> PresignedUrl:
        """Issue a presigned upload URL expiring after ``ttl_seconds`` (default 300)."""

    @abstractmethod
    def presign_get(self, key: str, ttl_seconds: int = 3600) -> PresignedUrl:
        """Issue a presigned download URL expiring after ``ttl_seconds`` (default 3600)."""

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        """Fetch the raw bytes of a stored object."""


class QueueClient(ABC):
    """Grading work queue gateway (SQS) (Requirement 7.1)."""

    @abstractmethod
    def send_grading_message(self, msg: GradingMessage) -> None:
        """Enqueue a grading message for the asynchronous worker."""


class CardSigner(ABC):
    """Tamper-evident signing gateway backed by a KMS-managed HMAC key (Req 11, 12)."""

    @abstractmethod
    def sign(self, payload: bytes) -> str:
        """Return the HMAC-SHA256 signature of the canonical payload."""

    @abstractmethod
    def verify(self, payload: bytes, signature: str) -> bool:
        """Recompute and compare the signature; return True when it matches."""


class EventPublisher(ABC):
    """Lifecycle event publishing gateway (EventBridge) (Requirement 15)."""

    @abstractmethod
    def publish(self, event: LifecycleEvent) -> None:
        """Emit a lifecycle event (GRADED, ROUTED, LISTED, MATCHED, SOLD)."""


class GradingProvider(ABC):
    """The swappable vision-model seam (Requirement 8.4).

    Implementations wrap a single model (e.g. Bedrock Nova Lite, Claude vision);
    the engine invokes them in cascade order.
    """

    @abstractmethod
    def grade(self, images: list[bytes], catalog: CatalogContext) -> RawModelResponse:
        """Invoke the model on the photo set and return its raw response."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier used for cascade ordering and logging."""


class BuyerPersonaRepository(ABC):
    """Seeded buyer persona source for demand matching (Requirement 13.6, 18.2)."""

    @abstractmethod
    def candidates(self, geo: str, category: str) -> list[BuyerPersona]:
        """Return seeded candidate buyers filtered by geo and category."""


class BuyerNotifier(ABC):
    """Proactive buyer-notification gateway for demand matching (Requirement 13.5).

    The Demand_Matching_Engine pushes a notification to each of the top-N ranked
    buyers when a recoverable Item is listed. The concrete implementation (push
    channel, email, in-app inbox) is built and injected by the composition root;
    the engine depends only on this contract.
    """

    @abstractmethod
    def notify(self, buyer_id: str, item_id: str) -> None:
        """Push a proactive notification to ``buyer_id`` about ``item_id``."""


class SecondChanceShelf(ABC):
    """Second-Chance PDP placement surface for matched Items (Requirement 13.5).

    Upserting is idempotent: placing the same Item more than once updates the
    existing placement rather than creating a duplicate, so repeated matches for
    one Item leave a single shelf entry.
    """

    @abstractmethod
    def upsert(self, item_id: str) -> None:
        """Create or update the Second-Chance PDP shelf placement for ``item_id``."""


class NotificationRepository(ABC):
    """Persistence for user notifications."""

    @abstractmethod
    def put_notification(self, notif: NotificationRecord) -> None:
        """Create a notification record for a user."""

    @abstractmethod
    def get_user_notifications(self, user_id: str, limit: int = 50) -> list[NotificationRecord]:
        """Return the latest notifications for a user, sorted descending by created_at."""

    @abstractmethod
    def mark_read(self, user_id: str, notif_id: str) -> None:
        """Mark a specific notification as read."""

    @abstractmethod
    def mark_all_read(self, user_id: str) -> None:
        """Mark all notifications for a user as read."""
