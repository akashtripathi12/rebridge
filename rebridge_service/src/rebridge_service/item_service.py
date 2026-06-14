"""ItemService: item creation, retrieval, and aggregate facet assembly.

This is the first slice of the ``Item_API`` business logic (design.md →
"Components and Interfaces → Service Layer → ItemService"). It is programmed
entirely against the abstract :mod:`rebridge_data.interfaces` and never imports
boto3 or any web framework.

Responsibilities implemented here (task 4.1):

* Create an Item from an **order-scan** or **manual** context, assigning a
  unique item identifier and an initial status of ``CREATED``
  (Requirements 1.1, 1.2).
* Reject a creation request that omits a required field with a validation error
  that names the missing field (Requirement 1.3).
* Aggregate-retrieve an Item, returning its status together with exactly the
  GRADE / CARD / DECISION / LISTING facets that have been persisted for it
  (Requirement 1.4), and raise a not-found error for an unknown item identifier
  (Requirement 1.5).

Presigned-upload validation (task 4.5) issues one presigned S3 PUT URL per
requested photo slot (2-4 inclusive) with a 5-minute TTL, never proxying photo
bytes through the API (Requirements 2.1, 2.2, 2.3, 2.4). Listing CRUD (task 4.7)
is a separate task; this class is structured so it can be added as further
methods without reworking creation/retrieval.

### Presigned photo-upload contract

``request_photo_upload_urls(item_id, count)`` returns exactly ``count``
:class:`~rebridge_data.models.PresignedUrl` values, one per photo slot, where
``2 <= count <= 4``. Each URL targets a stable object key
``items/{item_id}/photo-{i}`` and expires 300 seconds after issuance. A count
outside the 2-4 range raises :class:`InvalidPhotoCount`; an unconfigured object
store raises :class:`ObjectStoreNotConfigured`. The method neither accepts nor
returns image bytes - only upload targets (Requirement 2.3).

### Creation request contract

``create_item`` accepts a plain mapping (the API layer maps a validated Pydantic
body to it). The two context shapes are:

* **order-scan** (``context_source == "order_scan"``): requires ``category``,
  ``age_months``, and ``order_id`` (the scanned order reference, persisted as
  ``ItemMeta.context_ref``).
* **manual** (``context_source == "manual"``): requires ``category`` and
  ``age_months``.

``context_source`` itself is always required. A required field that is absent or
``None`` raises :class:`MissingField` naming that field; a ``context_source``
value outside the two allowed shapes raises :class:`InvalidField`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from decimal import Decimal

from rebridge_service.eventing_service import EventingService
from rebridge_data.interfaces import ItemRepository, ObjectStore
from rebridge_data.models import (
    ItemAggregate,
    ItemMeta,
    ItemStatus,
    ListingPatch,
    ListingRecord,
    PresignedUrl,
)

__all__ = [
    "ItemServiceError",
    "MissingField",
    "InvalidField",
    "ItemNotFound",
    "InvalidPhotoCount",
    "ObjectStoreNotConfigured",
    "GradeRequired",
    "ListingNotFound",
    "ORDER_SCAN",
    "MANUAL",
    "MIN_PHOTOS",
    "MAX_PHOTOS",
    "PHOTO_UPLOAD_TTL_SECONDS",
    "DEFAULT_LISTING_STATUS",
    "ItemService",
]

# Recognized creation context sources.
ORDER_SCAN = "order_scan"
MANUAL = "manual"

# Allowed photo-slot count for a single grading submission (Requirement 2.4).
MIN_PHOTOS = 2
MAX_PHOTOS = 4

# Presigned upload URL lifetime in seconds (Requirement 2.2).
PHOTO_UPLOAD_TTL_SECONDS = 300

# Status assigned to a newly created LISTING facet (Requirement 3.1).
DEFAULT_LISTING_STATUS = "ACTIVE"

# Fields required for every creation request, regardless of context shape.
_COMMON_REQUIRED_FIELDS = ("context_source", "category", "age_months")

# Additional fields required per context shape.
_CONTEXT_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    ORDER_SCAN: ("order_id",),
    MANUAL: (),
}


class ItemServiceError(Exception):
    """Base class for all service-level errors raised by :class:`ItemService`."""


class MissingField(ItemServiceError):
    """A required creation field was absent or ``None``.

    The offending field name is available as :attr:`field` and is named in the
    error message so the API layer can surface a 422 identifying it
    (Requirement 1.3).
    """

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"missing required field: {field}")


class InvalidField(ItemServiceError):
    """A provided field carried a value outside its allowed domain."""

    def __init__(self, field: str, value: Any, message: str | None = None) -> None:
        self.field = field
        self.value = value
        detail = message or f"invalid value for field {field!r}: {value!r}"
        super().__init__(detail)


class ItemNotFound(ItemServiceError):
    """No Item exists for the requested item identifier (Requirement 1.5)."""

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"item not found: {item_id}")


class InvalidPhotoCount(ItemServiceError):
    """A presigned-upload request asked for a count outside the 2-4 range.

    Raised when a client requests fewer than :data:`MIN_PHOTOS` or more than
    :data:`MAX_PHOTOS` photo upload URLs for a single grading submission. The
    requested ``count`` and the allowed bounds are exposed for the API layer to
    surface a 422 stating the allowed range (Requirement 2.4).
    """

    def __init__(self, count: int) -> None:
        self.count = count
        self.minimum = MIN_PHOTOS
        self.maximum = MAX_PHOTOS
        super().__init__(
            f"photo count {count} is outside the allowed range of "
            f"{MIN_PHOTOS} to {MAX_PHOTOS} photos"
        )


class ObjectStoreNotConfigured(ItemServiceError):
    """A presigned-upload request was made but no ObjectStore was injected.

    The presigned-URL feature requires an :class:`~rebridge_data.interfaces.ObjectStore`
    collaborator; this signals a composition-root misconfiguration rather than a
    client error.
    """

    def __init__(self) -> None:
        super().__init__(
            "no ObjectStore configured: ItemService.object_store is required "
            "to issue presigned photo-upload URLs"
        )


class GradeRequired(ItemServiceError):
    """A listing creation was attempted for an Item that has no persisted grade.

    Listing recoverable inventory requires a graded Item: a buyer-facing listing
    must reflect an assessed condition. The offending ``item_id`` is exposed so
    the API layer can surface a 409 stating that a grade is required before
    listing (Requirement 3.5).
    """

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(
            f"item {item_id} has no grade: a grade is required before listing"
        )


class ListingNotFound(ItemServiceError):
    """No LISTING facet exists for the requested (existing) Item.

    Raised by update operations that require a listing to already exist
    (Requirement 3.2 applies to an existing listing). The ``item_id`` is exposed
    so the API layer can surface a 404.
    """

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"no listing for item: {item_id}")


@dataclass
class ItemService:
    """Business logic for Item creation, retrieval, and facet aggregation.

    Collaborators are injected as abstract interfaces (design's one-way
    dependency ``service -> data``). ``object_store`` is accepted now so the
    presigned-upload slice (task 4.5) can extend this class without changing its
    construction sites. ``id_factory`` and ``clock`` are injectable to keep
    creation deterministic under test.
    """

    item_repo: ItemRepository
    object_store: ObjectStore | None = None
    eventing: EventingService | None = None
    id_factory: Callable[[], str] = lambda: uuid.uuid4().hex
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    # -- creation ----------------------------------------------------------
    def create_item(self, request: Mapping[str, Any]) -> ItemMeta:
        """Create an Item from an order-scan or manual context.

        Returns the persisted :class:`ItemMeta` with a freshly generated unique
        ``item_id`` and status ``CREATED`` (Requirements 1.1, 1.2). Raises
        :class:`MissingField` for any absent required field (Requirement 1.3)
        and :class:`InvalidField` for an unrecognized ``context_source``.
        """
        # context_source is required before we can know which shape applies.
        self._require(request, "context_source")
        context_source = request["context_source"]
        if context_source not in _CONTEXT_REQUIRED_FIELDS:
            raise InvalidField(
                "context_source",
                context_source,
                message=(
                    "context_source must be one of "
                    f"{ORDER_SCAN!r} or {MANUAL!r}, got {context_source!r}"
                ),
            )

        # Validate the remaining common and context-specific required fields.
        for field in _COMMON_REQUIRED_FIELDS:
            if field == "context_source":
                continue
            self._require(request, field)
        for field in _CONTEXT_REQUIRED_FIELDS[context_source]:
            self._require(request, field)

        item_id = self.id_factory()
        meta = ItemMeta(
            item_id=item_id,
            status=ItemStatus.CREATED,
            category=request["category"],
            age_months=request["age_months"],
            context_source=context_source,
            created_at=self.clock().isoformat(),
            context_ref=request.get("order_id") if context_source == ORDER_SCAN else None,
        )
        self.item_repo.put_item_meta(meta)
        return meta

    # -- retrieval ---------------------------------------------------------
    def get_item(self, item_id: str) -> ItemAggregate:
        """Return an Item's status plus exactly its persisted facets.

        The repository's :meth:`ItemRepository.get_item` already returns the META
        facet together with whichever of GRADE / CARD / DECISION / LISTING exist
        (absent facets are ``None``), satisfying Requirement 1.4. An unknown
        identifier raises :class:`ItemNotFound` (Requirement 1.5).
        """
        aggregate = self.item_repo.get_item(item_id)
        if aggregate is None:
            raise ItemNotFound(item_id)
        return aggregate

    # -- presigned photo upload -------------------------------------------
    def request_photo_upload_urls(
        self, item_id: str, count: int
    ) -> list[PresignedUrl]:
        """Issue one presigned S3 PUT URL per requested photo slot.

        Validates that ``count`` is within the inclusive 2-4 range and that the
        Item exists, then returns exactly ``count`` presigned upload targets -
        one per slot - each addressing a stable object key
        ``items/{item_id}/photo-{i}`` and expiring 300 seconds after issuance
        (Requirements 2.1, 2.2). The image bytes never pass through this method;
        it only mints upload URLs (Requirement 2.3).

        Raises
        ------
        InvalidPhotoCount
            When ``count`` is below :data:`MIN_PHOTOS` or above
            :data:`MAX_PHOTOS` (Requirement 2.4).
        ItemNotFound
            When ``item_id`` does not identify an existing Item (Requirement
            2.1 applies to an existing Item).
        ObjectStoreNotConfigured
            When no :class:`ObjectStore` collaborator was injected.
        """
        if count < MIN_PHOTOS or count > MAX_PHOTOS:
            raise InvalidPhotoCount(count)

        if self.object_store is None:
            raise ObjectStoreNotConfigured()

        # Requirement 2.1 issues URLs for an existing Item; reject unknown ids.
        if self.item_repo.get_item(item_id) is None:
            raise ItemNotFound(item_id)

        return [
            self.object_store.presign_put(
                self._photo_key(item_id, slot),
                ttl_seconds=PHOTO_UPLOAD_TTL_SECONDS,
            )
            for slot in range(1, count + 1)
        ]

    @staticmethod
    def _photo_key(item_id: str, slot: int) -> str:
        """Return the stable S3 object key for a given photo slot."""
        return f"items/{item_id}/photo-{slot}"

    # -- listing CRUD ------------------------------------------------------
    def create_listing(
        self,
        item_id: str,
        *,
        category: str,
        price: Decimal,
        geohash5: str,
        status: str = DEFAULT_LISTING_STATUS,
        listed_at: str | None = None,
    ) -> ListingRecord:
        """Create the LISTING facet for a graded Item.

        Requires that the Item exists and carries a persisted GRADE facet: a
        buyer-facing listing must reflect an assessed condition. On success the
        new :class:`~rebridge_data.models.ListingRecord` is persisted and
        returned (Requirement 3.1).

        Raises
        ------
        ItemNotFound
            When ``item_id`` does not identify an existing Item.
        GradeRequired
            When the Item exists but has no persisted GRADE facet
            (Requirement 3.5).
        """
        aggregate = self.item_repo.get_item(item_id)
        if aggregate is None:
            raise ItemNotFound(item_id)
        if aggregate.grade is None:
            raise GradeRequired(item_id)

        listing = ListingRecord(
            item_id=item_id,
            status=status,
            category=category,
            price=price,
            geohash5=geohash5,
            listed_at=listed_at if listed_at is not None else self.clock().isoformat(),
        )
        self.item_repo.put_listing(item_id, listing)
        self.item_repo.update_status(item_id, ItemStatus.LISTED)
        if self.eventing:
            self.eventing.emit_listed(item_id)
        return listing

    def get_listing(self, item_id: str) -> ListingRecord | None:
        """Return the current LISTING facet for an Item (Requirement 3.3).

        Returns ``None`` when the Item exists but has no listing (for example
        after a deletion). Raises :class:`ItemNotFound` for an unknown Item.
        """
        if self.item_repo.get_item(item_id) is None:
            raise ItemNotFound(item_id)
        return self.item_repo.get_listing(item_id)

    def update_listing(self, item_id: str, patch: ListingPatch) -> ListingRecord:
        """Apply a partial update to an existing LISTING facet (Requirement 3.2).

        Returns the updated :class:`~rebridge_data.models.ListingRecord`. Fields
        left ``None`` on the ``patch`` are unchanged.

        Raises
        ------
        ItemNotFound
            When ``item_id`` does not identify an existing Item.
        ListingNotFound
            When the Item exists but has no LISTING facet to update.
        """
        if self.item_repo.get_item(item_id) is None:
            raise ItemNotFound(item_id)
        if self.item_repo.get_listing(item_id) is None:
            raise ListingNotFound(item_id)
        return self.item_repo.update_listing(item_id, patch)

    def delete_listing(self, item_id: str) -> None:
        """Remove the LISTING facet for an Item (Requirement 3.4).

        Raises :class:`ItemNotFound` for an unknown Item. Deletion is idempotent
        for an existing Item: removing an absent listing is a no-op.
        """
        aggregate = self.item_repo.get_item(item_id)
        if aggregate is None:
            raise ItemNotFound(item_id)
            
        self.item_repo.delete_listing(item_id)
        
        # Revert the status to GRADED if it was LISTED
        if aggregate.meta.status == ItemStatus.LISTED:
            from rebridge_data.interfaces import ConditionCheckFailed
            try:
                self.item_repo.update_status(item_id, ItemStatus.GRADED, expected_status=ItemStatus.LISTED)
            except ConditionCheckFailed:
                pass

    def buy_listing(self, item_id: str) -> None:
        """Transition an Item to SOLD and emit the SOLD lifecycle event.
        
        Requires that the Item exists and has a LISTING facet. Prevents
        double-sells by checking if the Item is already SOLD.
        
        Raises
        ------
        ItemNotFound
            When ``item_id`` does not identify an existing Item.
        ListingNotFound
            When the Item exists but has no LISTING facet.
        ValueError
            When the Item is already SOLD or not in LISTED status.
        """
        aggregate = self.item_repo.get_item(item_id)
        if aggregate is None:
            raise ItemNotFound(item_id)
        if aggregate.listing is None:
            raise ListingNotFound(item_id)
            
        from rebridge_data.interfaces import ConditionCheckFailed
        try:
            self.item_repo.update_status(item_id, ItemStatus.SOLD, expected_status=ItemStatus.LISTED)
        except ConditionCheckFailed:
            raise ValueError(f"Item {item_id} cannot be sold because its status is {aggregate.meta.status}")
            
        if self.eventing:
            self.eventing.emit_sold(item_id)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _require(request: Mapping[str, Any], field: str) -> None:
        """Raise :class:`MissingField` when ``field`` is absent or ``None``."""
        if field not in request or request[field] is None:
            raise MissingField(field)
