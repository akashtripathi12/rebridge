"""Minimal in-memory data-layer fakes for API-layer tests.

These mirror the fakes in ``rebridge_service/tests`` but are kept local to the
``rebridge_api`` test suite because the service package's ``tests`` directory is
not an importable installed package. They honor the same
:mod:`rebridge_data.interfaces` contracts so the API can be exercised against
real service-layer logic with no AWS calls.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
from dataclasses import replace

from rebridge_data.interfaces import (
    BuyerNotifier,
    CardSigner,
    EventPublisher,
    ItemRepository,
    ObjectStore,
    QueueClient,
    ReviewQueueRepository,
    SecondChanceShelf,
)
from rebridge_data.models import (
    CardRecord,
    DecisionRecord,
    GradeRecord,
    GradingMessage,
    ItemAggregate,
    ItemMeta,
    ItemStatus,
    LifecycleEvent,
    ListingPatch,
    ListingRecord,
    PresignedUrl,
    ReviewQueueEntry,
)

__all__ = [
    "FakeItemRepository",
    "FakeObjectStore",
    "FakeQueueClient",
    "FakeEventPublisher",
    "FakeCardSigner",
    "FakeReviewQueueRepository",
    "FakeBuyerNotifier",
    "FakeSecondChanceShelf",
]


class FakeItemRepository(ItemRepository):
    """In-memory single-table store keyed by ``item_id``."""

    def __init__(self) -> None:
        self._meta: dict[str, ItemMeta] = {}
        self._grades: dict[str, GradeRecord] = {}
        self._cards_by_item: dict[str, CardRecord] = {}
        self._cards_by_id: dict[str, CardRecord] = {}
        self._decisions: dict[str, DecisionRecord] = {}
        self._listings: dict[str, ListingRecord] = {}
        self._idem_keys: dict[str, str] = {}

    def put_item_meta(self, item: ItemMeta) -> None:
        self._meta[item.item_id] = copy.deepcopy(item)

    def get_item(self, item_id: str) -> ItemAggregate | None:
        meta = self._meta.get(item_id)
        if meta is None:
            return None
        return ItemAggregate(
            meta=copy.deepcopy(meta),
            grade=copy.deepcopy(self._grades.get(item_id)),
            card=copy.deepcopy(self._cards_by_item.get(item_id)),
            decision=copy.deepcopy(self._decisions.get(item_id)),
            listing=copy.deepcopy(self._listings.get(item_id)),
        )

    def update_status(self, item_id: str, status: ItemStatus, expected_status: ItemStatus | None = None) -> None:
        meta = self._meta.get(item_id)
        if meta is None:
            raise KeyError(f"unknown item: {item_id}")
        if expected_status is not None and meta.status != expected_status:
            from rebridge_data.interfaces import ConditionCheckFailed
            raise ConditionCheckFailed(f"Status {meta.status} != {expected_status}")
        self._meta[item_id] = replace(meta, status=status)

    def put_grade(self, item_id: str, grade: GradeRecord) -> None:
        stored = copy.deepcopy(grade)
        self._grades[item_id] = stored
        if stored.idem_key is not None:
            self._idem_keys[stored.idem_key] = item_id

    def get_grade(self, item_id: str) -> GradeRecord | None:
        return copy.deepcopy(self._grades.get(item_id))

    def put_grade_if_absent(self, item_id: str, idem_key: str, grade: GradeRecord) -> bool:
        existing = self._grades.get(item_id)
        if existing is not None and existing.confirmed:
            return False
        stored = copy.deepcopy(grade)
        stored.idem_key = idem_key
        self._grades[item_id] = stored
        self._idem_keys[idem_key] = item_id
        return True

    def put_card(self, item_id: str, card: CardRecord) -> None:
        stored = copy.deepcopy(card)
        self._cards_by_item[item_id] = stored
        self._cards_by_id[stored.card_id] = stored

    def get_card(self, card_id: str) -> CardRecord | None:
        return copy.deepcopy(self._cards_by_id.get(card_id))

    def put_decision(self, item_id: str, decision: DecisionRecord) -> None:
        self._decisions[item_id] = copy.deepcopy(decision)

    def put_listing(self, item_id: str, listing: ListingRecord) -> None:
        self._listings[item_id] = copy.deepcopy(listing)

    def update_listing(self, item_id: str, patch: ListingPatch) -> ListingRecord:
        current = self._listings.get(item_id)
        if current is None:
            raise KeyError(f"no listing for item: {item_id}")
        updated = replace(
            current,
            status=patch.status if patch.status is not None else current.status,
            category=patch.category if patch.category is not None else current.category,
            price=patch.price if patch.price is not None else current.price,
            geohash5=patch.geohash5 if patch.geohash5 is not None else current.geohash5,
        )
        self._listings[item_id] = updated
        return copy.deepcopy(updated)

    def get_listing(self, item_id: str) -> ListingRecord | None:
        return copy.deepcopy(self._listings.get(item_id))

    def delete_listing(self, item_id: str) -> None:
        self._listings.pop(item_id, None)

    def query_marketplace(
        self, category: str, geo: str | None = None, limit: int = 50
    ) -> list[ListingRecord]:
        results = [
            copy.deepcopy(listing)
            for listing in self._listings.values()
            if listing.category == category
            and (geo is None or listing.geohash5.startswith(geo))
        ]
        return results[:limit]

    def batch_get_items(self, item_ids: list[str]) -> list[ItemAggregate]:
        results = []
        for item_id in item_ids:
            item = self.get_item(item_id)
            if item is not None:
                results.append(item)
        return results


class FakeObjectStore(ObjectStore):
    """In-memory object store with presigned-URL issuance."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.presigned: list[PresignedUrl] = []

    def put_object(self, key: str, data: bytes) -> None:
        self._objects[key] = data

    def presign_put(self, key: str, ttl_seconds: int = 300) -> PresignedUrl:
        url = PresignedUrl(
            url=f"https://fake-bucket.local/{key}",
            method="PUT",
            headers={},
            expires_in=ttl_seconds,
        )
        self.presigned.append(url)
        return url

    def get_bytes(self, key: str) -> bytes:
        return self._objects[key]


class FakeQueueClient(QueueClient):
    """In-memory grading work queue capturing enqueued messages."""

    def __init__(self) -> None:
        self.messages: list[GradingMessage] = []

    def send_grading_message(self, msg: GradingMessage) -> None:
        self.messages.append(copy.deepcopy(msg))


class FakeEventPublisher(EventPublisher):
    """In-memory lifecycle event sink."""

    def __init__(self) -> None:
        self.events: list[LifecycleEvent] = []

    def publish(self, event: LifecycleEvent) -> None:
        self.events.append(copy.deepcopy(event))

    def events_of(self, event_type: str) -> list[LifecycleEvent]:
        return [e for e in self.events if e.event_type == event_type]


class FakeCardSigner(CardSigner):
    """HMAC-SHA256 signer with an in-memory key."""

    def __init__(self, key: bytes = b"rebridge-test-hmac-key") -> None:
        self._key = key

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(payload), signature)


class FakeReviewQueueRepository(ReviewQueueRepository):
    """In-memory prioritized review queue (Requirement 14.1)."""

    def __init__(self) -> None:
        self._entries: dict[str, ReviewQueueEntry] = {}

    def enqueue(self, entry: ReviewQueueEntry) -> None:
        self._entries[entry.item_id] = copy.deepcopy(entry)

    def list_pending(self, limit: int) -> list[ReviewQueueEntry]:
        ordered = sorted(
            self._entries.values(),
            key=lambda e: e.priority,
            reverse=True,
        )
        return [copy.deepcopy(e) for e in ordered[:limit]]

    def get(self, item_id: str) -> ReviewQueueEntry | None:
        return copy.deepcopy(self._entries.get(item_id))

    def resolve(self, item_id: str) -> None:
        self._entries.pop(item_id, None)


class FakeBuyerNotifier(BuyerNotifier):
    """Records the (buyer_id, item_id) pushes the demand engine makes."""

    def __init__(self) -> None:
        self.notifications: list[tuple[str, str]] = []

    def notify(self, buyer_id: str, item_id: str) -> None:
        self.notifications.append((buyer_id, item_id))

    def buyers_for(self, item_id: str) -> list[str]:
        return [b for b, i in self.notifications if i == item_id]


class FakeSecondChanceShelf(SecondChanceShelf):
    """Records idempotent Second-Chance shelf placements by item id."""

    def __init__(self) -> None:
        self.upsert_counts: dict[str, int] = {}

    def upsert(self, item_id: str) -> None:
        self.upsert_counts[item_id] = self.upsert_counts.get(item_id, 0) + 1

    def __contains__(self, item_id: object) -> bool:
        return item_id in self.upsert_counts
