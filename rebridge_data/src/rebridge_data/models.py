"""Data-layer record and value types referenced by the abstract interfaces.

These are persistence-shaped, framework-free data holders (no boto3, no HTTP,
no business logic). They live in ``rebridge_data`` because the abstract
interfaces in :mod:`rebridge_data.interfaces` reference them, and the one-way
dependency direction ``api -> service -> data`` forbids the data layer from
importing the service layer. The service layer may import these records.

They are intentionally distinct from the richer service-layer domain models
(e.g. ``GradeAssessment``, ``RoutingDecision``, ``HealthCard``): these mirror
the DynamoDB single-table facets and gateway payloads (see design.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class ItemStatus(str, Enum):
    """Lifecycle status persisted on the META facet (Requirement 1.6)."""

    CREATED = "CREATED"
    RETAKE_REQUIRED = "RETAKE_REQUIRED"
    GRADING = "GRADING"
    PENDING_REVIEW = "PENDING_REVIEW"
    GRADED = "GRADED"
    LISTED = "LISTED"
    SOLD = "SOLD"


@dataclass
class ItemMeta:
    """META facet: ``ITEM#<id>`` / ``META``."""

    item_id: str
    status: ItemStatus
    category: str
    age_months: int
    context_source: str  # "order_scan" | "manual"
    created_at: str
    # Optional reference to the originating context. For an order-scan context
    # this carries the scanned order identifier; for a manual context it is None.
    context_ref: str | None = None
    expected_price: Decimal | None = None


@dataclass
class Defect:
    """A single observed defect with a location and severity."""

    location: str
    severity: str


@dataclass
class CompletenessResult:
    """Observed-vs-catalog completeness check result."""

    complete: bool
    missing_components: list[str] = field(default_factory=list)


@dataclass
class GradeRecord:
    """GRADE facet: ``ITEM#<id>`` / ``GRADE``."""

    grade: str
    confidence: float
    summary: str
    defects: list[Defect] = field(default_factory=list)
    completeness: CompletenessResult | None = None
    idem_key: str | None = None
    confirmed: bool = False


@dataclass
class CardRecord:
    """CARD facet: ``ITEM#<id>`` / ``CARD``."""

    card_id: str
    item_id: str
    signature: str
    qr_target: str
    graded_at: str
    warranty_stance: str
    annotated_photo_keys: list[str] = field(default_factory=list)


@dataclass
class DecisionRecord:
    """DECISION facet: ``ITEM#<id>`` / ``DECISION``."""

    disposition: str
    price: Decimal
    value: Decimal
    cost: Decimal
    margin: Decimal
    rationale: str


@dataclass
class ListingRecord:
    """LISTING facet: ``ITEM#<id>`` / ``LISTING``."""

    item_id: str
    status: str
    category: str
    price: Decimal
    geohash5: str
    listed_at: str


@dataclass
class ListingPatch:
    """Partial update applied to an existing LISTING facet.

    ``None`` fields are left unchanged.
    """

    status: str | None = None
    category: str | None = None
    price: Decimal | None = None
    geohash5: str | None = None


@dataclass
class ItemAggregate:
    """An Item's META facet plus whichever facets exist for it (Requirement 1.4)."""

    meta: ItemMeta
    grade: GradeRecord | None = None
    card: CardRecord | None = None
    decision: DecisionRecord | None = None
    listing: ListingRecord | None = None


@dataclass
class ReviewQueueEntry:
    """A pending low-confidence grade awaiting human action.

    ``priority`` encodes value x uncertainty = ``value * (1 - confidence)``
    and orders the queue descending (Requirement 14.1).
    """

    item_id: str
    value: Decimal
    confidence: float
    priority: float
    grade: GradeRecord | None = None


@dataclass
class PresignedUrl:
    """A presigned S3 upload target (Requirement 2.1, 2.2)."""

    url: str
    method: str = "PUT"
    headers: dict[str, str] = field(default_factory=dict)
    expires_in: int = 300


@dataclass
class GradingMessage:
    """A grading work item enqueued for the asynchronous worker (Requirement 7.1)."""

    item_id: str
    idem_key: str
    photo_keys: list[str] = field(default_factory=list)


@dataclass
class LifecycleEvent:
    """A lifecycle event emitted through the publisher (Requirement 15)."""

    event_type: str  # GRADED | ROUTED | LISTED | MATCHED | SOLD
    item_id: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass
class CatalogContext:
    """Catalog reference data supplied to a grading provider."""

    category: str
    title: str | None = None
    expected_components: list[str] = field(default_factory=list)


@dataclass
class RawModelResponse:
    """The raw, unparsed response returned by a grading provider (Requirement 8.4)."""

    provider_name: str
    content: str


@dataclass
class BuyerPersona:
    """A seeded buyer persona used by demand matching (Requirement 13.6, 18.2)."""

    buyer_id: str
    geohash5: str
    persona_type: str  # e.g. "deal_seeker", "price_balker"
    category_interests: list[str] = field(default_factory=list)
    intent: float = 0.0
    lifecycle: float = 0.0
    price_sensitivity: float = 0.0
