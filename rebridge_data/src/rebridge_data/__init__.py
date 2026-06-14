"""ReBridge data layer.

Holds the abstract repository/gateway interfaces and the boto3-backed
concrete implementations. This is the only layer permitted to import boto3.

The abstract interfaces (and the persistence-shaped record types they
reference) are re-exported here for convenient import by the service layer and
the composition root.
"""

from rebridge_data.dynamo_item_repository import DynamoItemRepository
from rebridge_data.interfaces import (
    BuyerPersonaRepository,
    CardSigner,
    EventPublisher,
    GradingProvider,
    ItemRepository,
    ObjectStore,
    QueueClient,
    ReviewQueueRepository,
    ConditionCheckFailed,
)
from rebridge_data.kms_card_signer import KmsCardSigner
from rebridge_data.models import (
    BuyerPersona,
    CardRecord,
    CatalogContext,
    CompletenessResult,
    DecisionRecord,
    Defect,
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
from rebridge_data.s3_object_store import S3ObjectStore

__all__ = [
    # interfaces
    "ItemRepository",
    "ConditionCheckFailed",
    # concrete implementations
    "DynamoItemRepository",
    "ReviewQueueRepository",
    "ObjectStore",
    "QueueClient",
    "CardSigner",
    "EventPublisher",
    "GradingProvider",
    "BuyerPersonaRepository",
    # concrete implementations
    "KmsCardSigner",
    # records / value types
    "ItemStatus",
    "ItemMeta",
    "ItemAggregate",
    "GradeRecord",
    "Defect",
    "CompletenessResult",
    "CardRecord",
    "DecisionRecord",
    "ListingRecord",
    "ListingPatch",
    "ReviewQueueEntry",
    "PresignedUrl",
    "GradingMessage",
    "LifecycleEvent",
    "CatalogContext",
    "RawModelResponse",
    "BuyerPersona",
    # concrete implementations (boto3-backed)
    "S3ObjectStore",
]
__version__ = "0.1.0"

# Concrete boto3-backed implementations (appended to avoid clobbering parallel
# edits to the interface/record re-exports above).
from rebridge_data.sqs_queue_client import SqsQueueClient  # noqa: E402

__all__.append("SqsQueueClient")

from rebridge_data.dynamo_review_queue_repository import (  # noqa: E402
    DynamoReviewQueueRepository,
)

__all__.append("DynamoReviewQueueRepository")

from rebridge_data.geohash import (  # noqa: E402
    decode_geohash,
    encode_geohash5,
    geohash_distance_km,
    seeded_distance_km,
)

__all__.append("encode_geohash5")
__all__.append("decode_geohash")
__all__.append("geohash_distance_km")
__all__.append("seeded_distance_km")

from rebridge_data.eventbridge_publisher import EventBridgePublisher  # noqa: E402

__all__.append("EventBridgePublisher")

from rebridge_data.bedrock_grading_providers import (  # noqa: E402
    BedrockNovaLiteProvider,
    ClaudeVisionProvider,
)

__all__.append("BedrockNovaLiteProvider")
__all__.append("ClaudeVisionProvider")

from rebridge_data.seeded_buyer_persona_repository import (  # noqa: E402
    SeededBuyerPersonaRepository,
)

__all__.append("SeededBuyerPersonaRepository")

from rebridge_data.eventbridge_demand_gateways import (  # noqa: E402
    EventBridgeBuyerNotifier,
    EventBridgeSecondChanceShelf,
)

__all__.append("EventBridgeBuyerNotifier")
__all__.append("EventBridgeSecondChanceShelf")
