"""ReBridge service / business-logic layer.

The defensible core: grading pipeline, routing policy, health cards, demand
matching, review console, and eventing. Programmed entirely against the
abstract interfaces declared in ``rebridge_data``; never imports boto3.
"""

from rebridge_service.confidence_gate import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
    GateDecision,
    GateOutcome,
)
from rebridge_service.idempotency import (
    derive_idempotency_key,
    derive_idempotency_key_from_photo_set_hash,
    photo_set_hash,
)
from rebridge_service.grading_engine import (
    GradingEngine,
    GradingEngineError,
    TotalCascadeFailure,
)
from rebridge_service.demand_matching_engine import (
    FAVORED_PERSONA_TYPES,
    DemandMatchingEngine,
    MatchWeights,
    ScoredCandidate,
)
from rebridge_service.eventing_service import EventingService
from rebridge_service.health_card_service import (
    CANONICAL_SEPARATOR,
    CardNotFound,
    GradeRequired,
    HealthCardError,
    HealthCardService,
    VerificationResult,
    canonical_card_payload,
)
from rebridge_service.item_service import (

    InvalidField,
    ItemNotFound,
    ItemService,
    ItemServiceError,
    MissingField,
)
from rebridge_service.notification_service import NotificationService
from rebridge_service.notification_worker import NotificationWorker
from rebridge_service.review_console_service import ReviewConsoleService
from rebridge_service.routing_tools import (
    AGE_BUCKETS,
    DEFAULT_CATEGORY,
    DEFAULT_DEMAND_INDEX,
    DEFAULT_ROUTE_COSTS,
    CostBreakdown,
    CostModel,
    DemandLevel,
    DemandProbe,
    DemandSignal,
    PriceBand,
    PriceEstimator,
    age_bucket_for_months,
)
from rebridge_service.models import (
    BuyerPersona,
    CompletenessResult,
    Defect,
    Disposition,
    EventType,
    Grade,
    GradeAssessment,
    HealthCard,
    ItemStatus,
    LifecycleEvent,
    ListingRecord,
    ReviewQueueEntry,
    RoutingDecision,
)

__all__: list[str] = [
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
    "ConfidenceGate",
    "GateDecision",
    "GateOutcome",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "derive_idempotency_key",
    "derive_idempotency_key_from_photo_set_hash",
    "photo_set_hash",
    "GradingEngine",
    "GradingEngineError",
    "TotalCascadeFailure",
    "HealthCardService",
    "HealthCardError",
    "GradeRequired",
    "CardNotFound",
    "VerificationResult",
    "canonical_card_payload",
    "CANONICAL_SEPARATOR",
    "ItemService",
    "ItemServiceError",
    "MissingField",
    "InvalidField",
    "ItemNotFound",
    "PriceBand",
    "PriceEstimator",
    "CostBreakdown",
    "CostModel",
    "DEFAULT_ROUTE_COSTS",
    "DemandLevel",
    "DemandSignal",
    "DemandProbe",
    "DEFAULT_DEMAND_INDEX",
    "AGE_BUCKETS",
    "DEFAULT_CATEGORY",
    "DemandMatchingEngine",
    "NotificationService",
    "NotificationWorker",
    "MatchWeights",
    "ScoredCandidate",
    "FAVORED_PERSONA_TYPES",
    "age_bucket_for_months",
]
__version__ = "0.1.0"
