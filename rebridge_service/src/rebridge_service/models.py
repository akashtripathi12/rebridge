"""Framework-free service-layer domain models for ReBridge_Backend.

These dataclasses and enums are the canonical in-memory representation of the
business domain. They use only the Python standard library (``dataclasses``,
``enum``, ``decimal``) so the service layer stays free of any web framework,
ORM, or AWS dependency. The data layer maps these to/from persistence and the
API layer maps them to/from transport models.

Design references:
- ``ItemStatus`` mirrors the lifecycle in the DynamoDB META facet (Req 1.6).
- ``Grade`` holds exactly the five allowed condition values (Req 5.1).
- ``GradeAssessment.confidence`` is constrained to the closed interval
  ``[0.0, 1.0]`` (Req 5.4).
- ``Disposition`` enumerates the four routing paths (Req 10.4).
- ``RoutingDecision`` carries the unit-economics rationale (Req 10.7).
- ``HealthCard`` is the signed, QR-verifiable record (Req 11.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

__all__ = [
    "ItemStatus",
    "Grade",
    "Disposition",
    "EventType",
    "Defect",
    "CompletenessResult",
    "GradeAssessment",
    "RoutingDecision",
    "HealthCard",
    "ListingRecord",
    "ReviewQueueEntry",
    "BuyerPersona",
    "LifecycleEvent",
    "KNOWN_CATEGORIES",
]

KNOWN_CATEGORIES: tuple[str, ...] = (
    "shoes",
    "baby",
    "tech",
    "books",
    "electronics",
    "apparel",
    "home",
    "toys",
)


class ItemStatus(Enum):
    """Lifecycle status of an Item (Requirement 1, design META facet)."""

    CREATED = "CREATED"
    RETAKE_REQUIRED = "RETAKE_REQUIRED"
    GRADING = "GRADING"
    PENDING_REVIEW = "PENDING_REVIEW"
    GRADED = "GRADED"
    LISTED = "LISTED"
    SOLD = "SOLD"


class Grade(Enum):
    """Condition classification with exactly the five allowed values.

    Validates Requirement 5.1: a Grade SHALL be one of Like New, Very Good,
    Good, Acceptable, or Unsellable. The enum values carry the human-readable
    labels; the members are the canonical machine identifiers.
    """

    LIKE_NEW = "Like New"
    VERY_GOOD = "Very Good"
    GOOD = "Good"
    ACCEPTABLE = "Acceptable"
    UNSELLABLE = "Unsellable"


class Disposition(Enum):
    """Routing disposition paths (Requirement 10.4)."""

    RESELL = "RESELL"
    REFURB = "REFURB"
    P2P = "P2P"
    DONATE = "DONATE"


class EventType(Enum):
    """Lifecycle event types emitted by the Event_Publisher (Requirement 15)."""

    GRADED = "GRADED"
    ROUTED = "ROUTED"
    LISTED = "LISTED"
    MATCHED = "MATCHED"
    SOLD = "SOLD"
    SELLER_NOTIFIED = "SELLER_NOTIFIED"


@dataclass
class Defect:
    """A single observed defect with a location and a severity (Req 5.2)."""

    location: str
    severity: str


@dataclass
class CompletenessResult:
    """Result of comparing the observed item against the catalog (Req 5.3).

    ``is_complete`` is True when no expected components are missing.
    ``missing_components`` enumerates any catalog-expected parts not observed.
    """

    is_complete: bool
    missing_components: list[str] = field(default_factory=list)


@dataclass
class GradeAssessment:
    """A grade assessment produced by the Grading_Engine (Requirement 5).

    Includes a ``Grade`` (one of the five allowed values), a defect list, a
    completeness result, a confidence score in the closed interval
    ``[0.0, 1.0]`` (Req 5.4), and a plain-language summary (Req 5.5).
    """

    grade: Grade
    defects: list[Defect]
    completeness: CompletenessResult
    confidence: float
    summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.grade, Grade):
            raise ValueError(
                f"grade must be a Grade enum member, got {self.grade!r}"
            )
        # Confidence_Score must be a real number in the closed interval [0, 1].
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ):
            raise ValueError(
                f"confidence must be a float, got {type(self.confidence).__name__}"
            )
        self.confidence = float(self.confidence)
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in the closed interval [0, 1], got {self.confidence}"
            )


@dataclass
class RoutingDecision:
    """A disposition decision with its unit-economics rationale (Req 10.7).

    Carries the selected ``Disposition``, the recoverable ``price``, and the
    ``value``/``cost``/``margin`` that drove the choice, plus a one-line
    ``rationale`` string stating that math.
    """

    disposition: Disposition
    price: Decimal
    value: Decimal
    cost: Decimal
    margin: Decimal
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, Disposition):
            raise ValueError(
                f"disposition must be a Disposition enum member, got {self.disposition!r}"
            )


@dataclass
class HealthCard:
    """A tamper-evident Product Health Card (Requirements 11, 12).

    Contains the grade, annotated photo references, a plain-language defect
    summary, a verification date, and a warranty stance, plus the HMAC
    signature and QR target used for public verification.
    """

    card_id: str
    item_id: str
    grade: Grade
    graded_at: str
    defect_summary: str
    warranty_stance: str
    annotated_photo_keys: list[str] = field(default_factory=list)
    signature: str = ""
    qr_target: str = ""


@dataclass
class ListingRecord:
    """A LISTING facet for a graded Item (Requirement 3).

    ``geohash5`` keeps location at no finer precision than Geohash5 (Req 17).
    """

    item_id: str
    status: str
    category: str
    price: Decimal
    geohash5: str
    listed_at: str


@dataclass
class ReviewQueueEntry:
    """An entry in the prioritized human Review_Queue (Requirement 14).

    ``priority`` is value multiplied by uncertainty, i.e.
    ``value * (1 - confidence)``; the queue is ordered by this descending.
    """

    item_id: str
    grade: Grade
    value: Decimal
    confidence: float
    priority: float = 0.0

    def __post_init__(self) -> None:
        # Derive priority = value * (1 - confidence) when not explicitly set.
        if self.priority == 0.0:
            self.priority = float(self.value) * (1.0 - float(self.confidence))


@dataclass
class BuyerPersona:
    """A seeded candidate buyer used by the Demand_Matching_Engine (Req 13).

    ``persona_type`` distinguishes deal-seeker / price-balker personas that
    receive anti-cannibalization weighting (Req 13.4). Signal scores feed the
    weighted ranking function (Req 13.2).
    """

    buyer_id: str
    geohash5: str
    category: str
    persona_type: str
    intent: float
    lifecycle: float
    geo: float
    price_sensitivity: float
    wishlist_categories: list[str] = field(default_factory=list)
    cart_categories: list[str] = field(default_factory=list)


@dataclass
class LifecycleEvent:
    """A lifecycle event emitted through the Event_Publisher (Requirement 15).

    ``disposition`` is populated only for ROUTED events (Req 15.2).
    """

    event_type: EventType
    item_id: str
    disposition: Disposition | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            raise ValueError(
                f"event_type must be an EventType enum member, got {self.event_type!r}"
            )
