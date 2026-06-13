"""In-memory fakes for the data-layer abstract interfaces.

These fakes subclass the abstract base classes declared in
:mod:`rebridge_data.interfaces` and faithfully honor each contract so the
service-layer property and unit tests can exercise real business logic without
any AWS calls (Requirements 1.6, 8.4).

Design notes / honored contracts:

* :class:`FakeItemRepository.put_grade_if_absent` implements the idempotent
  conditional-write semantics: the first write for a given ``idem_key`` wins and
  returns ``True``; any later write carrying an ``idem_key`` already seen is a
  no-op that retains the existing grade and returns ``False`` (Requirement 7.3).
* :class:`FakeReviewQueueRepository.list_pending` returns entries ordered by
  ``priority`` descending (Requirement 14.1).
* :class:`FakeObjectStore.presign_put` echoes the requested TTL onto the
  returned :class:`PresignedUrl` (Requirement 2.2).
* :class:`FakeCardSigner` signs and verifies with a real HMAC-SHA256 keyed hash
  (Requirements 11.2, 12.1).
* :class:`FakeGradingProvider` is *programmable*: it replays a scripted sequence
  of raw responses and/or exceptions so later tasks can drive cascade,
  timeout, and invalid-JSON scenarios (Requirements 8.1-8.4).

Nothing here imports boto3; everything is plain in-memory Python.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
from collections import deque
from dataclasses import replace
from typing import Iterable

from rebridge_data.interfaces import (
    BuyerPersonaRepository,
    BuyerNotifier,
    CardSigner,
    EventPublisher,
    GradingProvider,
    ItemRepository,
    ObjectStore,
    QueueClient,
    ReviewQueueRepository,
    SecondChanceShelf,
)
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
    PresignedUrl,
    RawModelResponse,
    ReviewQueueEntry,
)

__all__ = [
    "FakeItemRepository",
    "FakeReviewQueueRepository",
    "FakeObjectStore",
    "FakeQueueClient",
    "FakeCardSigner",
    "FakeEventPublisher",
    "FakeGradingProvider",
    "FakeBuyerPersonaRepository",
    "FakeBuyerNotifier",
    "FakeSecondChanceShelf",
]


class FakeItemRepository(ItemRepository):
    """In-memory single-table store keyed by ``item_id``.

    Facets (META/GRADE/CARD/DECISION/LISTING) are kept in per-item dataclass
    slots mirroring the DynamoDB single-table model. Stored values are deep
    copied on the way in and out so callers cannot mutate persisted state by
    holding a reference (matching the marshalling boundary of a real gateway).
    """

    def __init__(self) -> None:
        self._meta: dict[str, ItemMeta] = {}
        self._grades: dict[str, GradeRecord] = {}
        self._cards_by_item: dict[str, CardRecord] = {}
        self._cards_by_id: dict[str, CardRecord] = {}
        self._decisions: dict[str, DecisionRecord] = {}
        self._listings: dict[str, ListingRecord] = {}
        # idem_key -> item_id, recording which keys have already produced a grade.
        self._idem_keys: dict[str, str] = {}

    # -- META --------------------------------------------------------------
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

    def update_status(self, item_id: str, status: ItemStatus) -> None:
        meta = self._meta.get(item_id)
        if meta is None:
            raise KeyError(f"unknown item: {item_id}")
        self._meta[item_id] = replace(meta, status=status)

    # -- GRADE -------------------------------------------------------------
    def put_grade(self, item_id: str, grade: GradeRecord) -> None:
        stored = copy.deepcopy(grade)
        self._grades[item_id] = stored
        if stored.idem_key is not None:
            self._idem_keys[stored.idem_key] = item_id

    def get_grade(self, item_id: str) -> GradeRecord | None:
        return copy.deepcopy(self._grades.get(item_id))

    def put_grade_if_absent(
        self,
        item_id: str,
        idem_key: str,
        grade: GradeRecord,
    ) -> bool:
        """Conditional write: first key wins, later duplicates are retained.

        Returns ``True`` when the grade is written, ``False`` when a grade for
        this idempotency key was already present and is therefore retained
        unchanged (Requirement 7.3).
        """
        if idem_key in self._idem_keys:
            return False
        stored = copy.deepcopy(grade)
        stored.idem_key = idem_key
        self._grades[item_id] = stored
        self._idem_keys[idem_key] = item_id
        return True

    # -- CARD --------------------------------------------------------------
    def put_card(self, item_id: str, card: CardRecord) -> None:
        stored = copy.deepcopy(card)
        self._cards_by_item[item_id] = stored
        self._cards_by_id[stored.card_id] = stored

    def get_card(self, card_id: str) -> CardRecord | None:
        return copy.deepcopy(self._cards_by_id.get(card_id))

    # -- DECISION ----------------------------------------------------------
    def put_decision(self, item_id: str, decision: DecisionRecord) -> None:
        self._decisions[item_id] = copy.deepcopy(decision)

    # -- LISTING -----------------------------------------------------------
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
        self,
        category: str,
        geo: str | None = None,
        limit: int = 50,
    ) -> list[ListingRecord]:
        results = [
            copy.deepcopy(listing)
            for listing in self._listings.values()
            if listing.category == category
            and (geo is None or listing.geohash5.startswith(geo))
        ]
        return results[:limit]


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


class FakeObjectStore(ObjectStore):
    """In-memory object store with presigned-URL issuance (Requirement 2)."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.presigned: list[PresignedUrl] = []

    def put_object(self, key: str, data: bytes) -> None:
        """Test helper to seed object bytes (not part of the interface)."""
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
        try:
            return self._objects[key]
        except KeyError as exc:
            raise KeyError(f"no object at key: {key}") from exc


class FakeQueueClient(QueueClient):
    """In-memory grading work queue capturing enqueued messages (Req 7.1)."""

    def __init__(self) -> None:
        self.messages: list[GradingMessage] = []

    def send_grading_message(self, msg: GradingMessage) -> None:
        self.messages.append(copy.deepcopy(msg))


class FakeCardSigner(CardSigner):
    """HMAC-SHA256 signer with an in-memory key (Requirements 11.2, 12.1).

    Uses a real keyed hash so sign/verify round-trips and tamper detection
    behave exactly as the KMS-backed implementation will.
    """

    def __init__(self, key: bytes = b"rebridge-test-hmac-key") -> None:
        self._key = key

    def sign(self, payload: bytes) -> str:
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, signature: str) -> bool:
        expected = self.sign(payload)
        return hmac.compare_digest(expected, signature)


class FakeEventPublisher(EventPublisher):
    """In-memory lifecycle event sink (Requirement 15)."""

    def __init__(self) -> None:
        self.events: list[LifecycleEvent] = []

    def publish(self, event: LifecycleEvent) -> None:
        self.events.append(copy.deepcopy(event))

    def events_of(self, event_type: str) -> list[LifecycleEvent]:
        """Test helper: filter captured events by type."""
        return [e for e in self.events if e.event_type == event_type]


class FakeGradingProvider(GradingProvider):
    """A programmable vision-model fake (the swappable seam, Requirement 8.4).

    Construct it with a ``name`` and a ``script`` of outcomes. Each call to
    :meth:`grade` consumes the next outcome:

    * a :class:`RawModelResponse` is returned as-is;
    * a ``str`` is wrapped in a :class:`RawModelResponse` (handy for scripting
      valid or invalid JSON content);
    * an :class:`Exception` instance (or a callable returning/raising one) is
      raised, letting tests drive timeout / error fallback scenarios.

    When the script is exhausted the final outcome repeats, so a provider can be
    made to "always time out" with a single-element script. Every invocation is
    recorded in :attr:`calls` for ordering assertions (cascade tests).
    """

    def __init__(
        self,
        name: str,
        script: Iterable[RawModelResponse | str | BaseException] | None = None,
    ) -> None:
        self._name = name
        self._script: deque[RawModelResponse | str | BaseException] = deque(
            script or []
        )
        self.calls: list[tuple[int, CatalogContext]] = []

    @property
    def name(self) -> str:
        return self._name

    def grade(
        self, images: list[bytes], catalog: CatalogContext
    ) -> RawModelResponse:
        self.calls.append((len(images), catalog))
        if not self._script:
            raise RuntimeError(
                f"FakeGradingProvider {self._name!r} has no scripted outcome"
            )
        # Peek; keep the last outcome so a single-element script repeats.
        outcome = self._script[0] if len(self._script) == 1 else self._script.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, RawModelResponse):
            return outcome
        # str content
        return RawModelResponse(provider_name=self._name, content=outcome)


class FakeBuyerPersonaRepository(BuyerPersonaRepository):
    """Seeded buyer persona source for demand matching (Req 13.6, 18.2).

    Personas are provided at construction time (the v1 seeded data source).
    :meth:`candidates` filters by exact category interest and a geohash prefix
    match against the requested ``geo``.
    """

    def __init__(self, personas: Iterable[BuyerPersona] | None = None) -> None:
        self._personas: list[BuyerPersona] = list(personas or [])

    def add(self, persona: BuyerPersona) -> None:
        """Test helper to seed an additional persona."""
        self._personas.append(persona)

    def candidates(self, geo: str, category: str) -> list[BuyerPersona]:
        return [
            copy.deepcopy(p)
            for p in self._personas
            if category in p.category_interests
            and (not geo or p.geohash5.startswith(geo) or geo.startswith(p.geohash5))
        ]


class FakeBuyerNotifier(BuyerNotifier):
    """In-memory proactive notification sink (Requirement 13.5).

    Records every ``(buyer_id, item_id)`` push in order so tests can assert
    exactly which buyers were notified for a match.
    """

    def __init__(self) -> None:
        self.notifications: list[tuple[str, str]] = []

    def notify(self, buyer_id: str, item_id: str) -> None:
        self.notifications.append((buyer_id, item_id))

    def buyers_for(self, item_id: str) -> list[str]:
        """Test helper: ordered buyer ids notified about ``item_id``."""
        return [b for b, i in self.notifications if i == item_id]


class FakeSecondChanceShelf(SecondChanceShelf):
    """In-memory Second-Chance PDP shelf with idempotent upsert (Req 13.5).

    Placements are keyed by ``item_id`` and the per-item upsert count is tracked
    so tests can assert an Item appears exactly once on the shelf regardless of
    how many times it is matched.
    """

    def __init__(self) -> None:
        self.upsert_counts: dict[str, int] = {}

    def upsert(self, item_id: str) -> None:
        self.upsert_counts[item_id] = self.upsert_counts.get(item_id, 0) + 1

    @property
    def items(self) -> list[str]:
        """Test helper: the distinct Items currently on the shelf."""
        return list(self.upsert_counts)

    def __contains__(self, item_id: object) -> bool:
        return item_id in self.upsert_counts
