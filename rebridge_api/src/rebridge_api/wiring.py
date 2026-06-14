"""Composition root for the ReBridge API (task 17.8).

This module is the **single place** in the system where concrete, boto3-backed
data-layer implementations are constructed and injected into the pure
service-layer classes (design.md -> "Composition root (`wiring.py`)"). Every
other module is programmed against interfaces; only here are the real
``Dynamo*``/``S3*``/``Sqs*``/``Kms*``/``EventBridge*``/``Bedrock*`` gateways
built and wired together. Configuration -- the confidence threshold (default
0.80, Req 6.3), model timeout, top-N, table name, KMS key id, queue url,
bucket, event bus, region, Cognito parameters, and Bedrock model ids -- is read
once into a :class:`Settings` dataclass and threaded through the three build
entrypoints:

* :func:`build_services` constructs the data concretes once and injects them
  into the service classes, returning the :class:`~rebridge_api.dependencies.Services`
  container the FastAPI routers depend on. The grading cascade is wired in
  order ``[Nova Lite, Claude vision]`` (Req 8.4) and the
  :class:`~rebridge_service.confidence_gate.ConfidenceGate` is built from the
  configured threshold (Req 6.3).
* :func:`build_app` creates the FastAPI app from those services, attaches a
  Cognito JWT verifier built from configuration, installs the app on the Lambda
  HTTP adapter, and returns it.
* :func:`build_worker` constructs the boto3-backed :class:`GradingPipeline` and
  the :class:`~rebridge_api.worker.GradingWorker` that drives it, and registers
  the worker on the module-level SQS entrypoint seam.

### boto3-tolerant, lazy construction

Importing this module performs **no** AWS calls. The boto3 clients/resources are
created (which only requires a region, never network or credentials) but never
invoked until a request or SQS record is actually processed. A single shared
``dynamodb`` resource is created and injected into both Dynamo repositories so
the concretes are constructed once, as the design requires. ``boto3`` is
imported here because the composition root is the API layer's infrastructure
glue; the *service* layer remains free of any AWS dependency.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

import boto3
from fastapi import FastAPI

from rebridge_data.bedrock_grading_providers import (
    DEFAULT_CLAUDE_VISION_MODEL_ID,
    DEFAULT_NOVA_LITE_MODEL_ID,
    BedrockNovaLiteProvider,
    ClaudeVisionProvider,
)
from rebridge_data.dynamo_item_repository import DynamoItemRepository
from rebridge_data.dynamo_review_queue_repository import DynamoReviewQueueRepository
from rebridge_data.eventbridge_demand_gateways import (
    EventBridgeBuyerNotifier,
    EventBridgeSecondChanceShelf,
)
from rebridge_data.eventbridge_publisher import EventBridgePublisher
from rebridge_data.kms_card_signer import KmsCardSigner
from rebridge_data.s3_object_store import S3ObjectStore
from rebridge_data.seeded_buyer_persona_repository import SeededBuyerPersonaRepository
from rebridge_data.sqs_queue_client import SqsQueueClient

from rebridge_service.confidence_gate import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
)
from rebridge_service.demand_matching_engine import DemandMatchingEngine
from rebridge_service.eventing_service import EventingService
from rebridge_service.grading_engine import GradingEngine
from rebridge_service.grading_pipeline import GradingPipeline
from rebridge_service.health_card_service import HealthCardService
from rebridge_service.item_service import ItemService
from rebridge_service.quality_precheck import QualityPrecheck
from rebridge_service.review_console_service import ReviewConsoleService
from rebridge_service.routing_agent import RoutingAgent
from rebridge_service.routing_tools import CostModel, DemandProbe, PriceEstimator

from rebridge_api import http_adapter
from rebridge_api.app import create_app
from rebridge_api.auth import CognitoJwtVerifier
from rebridge_api.dependencies import Services, set_verifier
from rebridge_api.routing_adapter import EventEmittingRouter
from rebridge_api.worker import GradingWorker, set_worker

__all__ = [
    "Settings",
    "BuiltServices",
    "build_services",
    "build_app",
    "build_worker",
]


# Default per-call model timeout (seconds) for the grading cascade when config
# does not supply one. Generous enough for a vision model call yet bounded so a
# hung provider falls through to the next in the cascade.
DEFAULT_MODEL_TIMEOUT_SECONDS: float = 3.0

# Default number of buyers the Demand_Matching_Engine notifies per match
# (Requirement 13.5).
DEFAULT_TOP_N: int = 5

# Default AWS region. Supplying a region keeps boto3 client/resource
# construction offline-tolerant (no NoRegionError) without requiring ambient
# AWS configuration.
DEFAULT_REGION: str = "us-east-1"


@dataclass(frozen=True)
class Settings:
    """Typed configuration for the composition root, loaded from the environment.

    All fields carry sensible defaults so the app is constructible without any
    ambient configuration (the boto3 gateways are still built lazily and make no
    AWS calls at construction). The infrastructure identifiers (table name,
    bucket, queue url, KMS key id, event bus) default to obvious placeholders;
    the deployed environment overrides them via the ``REBRIDGE_*`` environment
    variables read by :meth:`from_env`.

    Attributes
    ----------
    confidence_threshold:
        Confidence_Threshold for the :class:`ConfidenceGate`; defaults to 0.80
        (Requirement 6.3).
    model_timeout:
        Per-call timeout (seconds) enforced on each grading provider invocation.
    top_n:
        Default number of buyers notified per demand match (Requirement 13.5).
    table_name:
        DynamoDB single-table name backing the item and review-queue repos.
    photo_bucket:
        S3 bucket holding uploaded photos.
    grading_queue_url:
        SQS grading queue URL.
    kms_key_id:
        KMS HMAC key id used to sign Product Health Cards.
    event_bus:
        EventBridge event bus name for lifecycle events.
    region:
        AWS region for all constructed clients/resources.
    cognito_region / cognito_user_pool_id / cognito_app_client_id:
        Cognito user-pool parameters for the JWT verifier. ``cognito_region``
        defaults to :attr:`region` when not separately configured.
    nova_lite_model_id / claude_vision_model_id:
        Bedrock model ids for the cascade providers (Nova Lite first, Claude
        vision second, Requirement 8.4).
    """

    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    model_timeout: float = DEFAULT_MODEL_TIMEOUT_SECONDS
    top_n: int = DEFAULT_TOP_N
    table_name: str = "rebridge"
    photo_bucket: str = "rebridge-photos"
    grading_queue_url: str = "https://sqs.local/rebridge-grading"
    kms_key_id: str = "alias/rebridge-card-signing"
    event_bus: str = "rebridge-lifecycle"
    region: str = DEFAULT_REGION
    cognito_region: str = DEFAULT_REGION
    cognito_user_pool_id: str = "us-east-1_placeholder"
    cognito_app_client_id: str = "placeholder-app-client-id"
    nova_lite_model_id: str = DEFAULT_NOVA_LITE_MODEL_ID
    claude_vision_model_id: str = DEFAULT_CLAUDE_VISION_MODEL_ID

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Build :class:`Settings` from a ``REBRIDGE_*`` environment mapping.

        Reads from ``os.environ`` by default; tests pass an explicit ``dict``.
        Unset keys fall back to the dataclass defaults, so a fully empty mapping
        yields a usable (placeholder) configuration. Numeric fields are parsed
        with the field's default substituted on a missing/blank value.
        """

        src = os.environ if env is None else env

        def _get(key: str, default: str) -> str:
            value = src.get(key)
            return value if value is not None and value != "" else default

        def _get_float(key: str, default: float) -> float:
            value = _get(key, "")
            if not value:
                return default
            try:
                return float(value)
            except ValueError as e:
                raise ValueError(f"Invalid numeric value for {key}: {value}") from e

        def _get_int(key: str, default: int) -> int:
            value = _get(key, "")
            if not value:
                return default
            try:
                return int(value)
            except ValueError as e:
                raise ValueError(f"Invalid integer value for {key}: {value}") from e

        region = _get("REBRIDGE_REGION", _get("AWS_REGION", DEFAULT_REGION))

        return cls(
            confidence_threshold=_get_float("REBRIDGE_CONFIDENCE_THRESHOLD", DEFAULT_CONFIDENCE_THRESHOLD),
            model_timeout=_get_float("REBRIDGE_MODEL_TIMEOUT", DEFAULT_MODEL_TIMEOUT_SECONDS),
            top_n=_get_int("REBRIDGE_TOP_N", DEFAULT_TOP_N),
            table_name=_get("REBRIDGE_TABLE_NAME", cls.table_name),
            photo_bucket=_get("REBRIDGE_PHOTO_BUCKET", cls.photo_bucket),
            grading_queue_url=_get("REBRIDGE_GRADING_QUEUE_URL", cls.grading_queue_url),
            kms_key_id=_get("REBRIDGE_KMS_KEY_ID", cls.kms_key_id),
            event_bus=_get("REBRIDGE_EVENT_BUS", cls.event_bus),
            region=region,
            cognito_region=_get("REBRIDGE_COGNITO_REGION", region),
            cognito_user_pool_id=_get(
                "REBRIDGE_COGNITO_USER_POOL_ID", cls.cognito_user_pool_id
            ),
            cognito_app_client_id=_get(
                "REBRIDGE_COGNITO_APP_CLIENT_ID", cls.cognito_app_client_id
            ),
            nova_lite_model_id=_get(
                "REBRIDGE_NOVA_LITE_MODEL_ID", DEFAULT_NOVA_LITE_MODEL_ID
            ),
            claude_vision_model_id=_get(
                "REBRIDGE_CLAUDE_VISION_MODEL_ID", DEFAULT_CLAUDE_VISION_MODEL_ID
            ),
        )


@dataclass
class BuiltServices:
    """Everything the composition root constructs from one :class:`Settings`.

    :func:`build_services` returns this so callers (the app and worker builders,
    and tests) can reach both the router-facing :class:`Services` container and
    the additional collaborators -- the boto3-backed repositories, the grading
    engine, confidence gate, and the review/demand services -- that the worker
    pipeline and other entrypoints need. Constructing them together guarantees
    the concretes are built exactly once and shared.
    """

    settings: Settings
    services: Services

    # Data-layer concretes (constructed once, shared across services).
    item_repo: DynamoItemRepository
    review_repo: DynamoReviewQueueRepository
    object_store: S3ObjectStore

    # Service-layer collaborators not exposed through the router container.
    grading_engine: GradingEngine
    confidence_gate: ConfidenceGate
    card_service: HealthCardService
    eventing: EventingService
    routing: RoutingAgent
    precheck: QualityPrecheck
    review_console: ReviewConsoleService
    demand_engine: DemandMatchingEngine
    price_estimator: PriceEstimator


def build_services(settings: Settings) -> BuiltServices:
    """Construct the data concretes once and inject them into the services.

    This is the heart of the composition root. It builds a single shared
    ``dynamodb`` resource (so both Dynamo repositories reuse one connection),
    the S3/SQS/KMS/EventBridge gateways, the seeded buyer-persona repository, and
    the ordered Bedrock provider cascade, then injects them into the pure
    service-layer classes. No AWS calls are made here -- the clients are created
    but not invoked.

    The grading cascade is wired as ``[Nova Lite, Claude vision]`` (Requirement
    8.4) and the :class:`ConfidenceGate` is built from
    ``settings.confidence_threshold`` (default 0.80, Requirement 6.3).
    """

    region = settings.region

    # --- Data-layer concretes (built once) --------------------------------
    # One shared DynamoDB resource injected into both repositories so the
    # concrete data layer is constructed exactly once (design requirement).
    dynamodb_resource = boto3.resource("dynamodb", region_name=region)
    item_repo = DynamoItemRepository(
        settings.table_name, dynamodb_resource=dynamodb_resource
    )
    review_repo = DynamoReviewQueueRepository(
        settings.table_name, dynamodb_resource=dynamodb_resource
    )
    object_store = S3ObjectStore(
        settings.photo_bucket, client=boto3.client("s3", region_name=region)
    )
    queue = SqsQueueClient(settings.grading_queue_url, region_name=region)
    signer = KmsCardSigner(settings.kms_key_id, region_name=region)
    publisher = EventBridgePublisher(settings.event_bus, region_name=region)
    buyers = SeededBuyerPersonaRepository()
    # Demand-matching side-effect gateways, realized as events on the same bus
    # (no new external infra) so Engine B's push/shelf are connected end to end.
    buyer_notifier = EventBridgeBuyerNotifier(publisher)
    second_chance_shelf = EventBridgeSecondChanceShelf(publisher)

    # Ordered grading cascade: Nova Lite first, Claude vision fallback (Req 8.4).
    providers = [
        BedrockNovaLiteProvider(settings.nova_lite_model_id, region_name=region),
        ClaudeVisionProvider(settings.claude_vision_model_id, region_name=region),
    ]

    # --- Service-layer wiring ---------------------------------------------
    eventing = EventingService(publisher)
    grading_engine = GradingEngine(
        providers, timeout=settings.model_timeout, max_json_retries=2
    )
    # ConfidenceGate from configured threshold (default 0.80, Requirement 6.3).
    confidence_gate = ConfidenceGate(threshold=settings.confidence_threshold)
    card_service = HealthCardService(signer, item_repo)
    item_service = ItemService(item_repo, object_store, eventing=eventing)
    precheck = QualityPrecheck()
    price_estimator = PriceEstimator()

    routing = RoutingAgent(
        price=price_estimator,
        cost=CostModel(),
        item_repo=item_repo,
        demand=DemandProbe.from_buyer_repository(buyers),
    )

    review_console = ReviewConsoleService(item_repo, review_repo)
    # Engine B fully connected: notifier + shelf + eventing injected so match()
    # notifies top-N buyers, upserts the Second-Chance shelf, and emits MATCHED.
    demand_engine = DemandMatchingEngine(
        buyers,
        notifier=buyer_notifier,
        shelf=second_chance_shelf,
        eventing=eventing,
        top_n=settings.top_n,
    )

    services = Services(
        item_service=item_service,
        routing=routing,
        eventing=eventing,
        queue=queue,
        item_repo=item_repo,
        card_service=card_service,
        matching=demand_engine,
        review=review_console,
    )

    return BuiltServices(
        settings=settings,
        services=services,
        item_repo=item_repo,
        review_repo=review_repo,
        object_store=object_store,
        grading_engine=grading_engine,
        confidence_gate=confidence_gate,
        card_service=card_service,
        eventing=eventing,
        routing=routing,
        precheck=precheck,
        review_console=review_console,
        demand_engine=demand_engine,
        price_estimator=price_estimator,
    )


def build_app(settings: Settings, built: BuiltServices | None = None) -> FastAPI:
    """Build the configured FastAPI app and install it on the Lambda adapter.

    Creates the app from the wired :class:`Services` container, attaches a
    Cognito JWT verifier built from configuration (no network until the first
    token is validated), installs the app on the HTTP adapter via
    :func:`rebridge_api.http_adapter.set_app`, and returns it. ``built`` may be
    supplied to reuse an already-constructed :class:`BuiltServices`; otherwise
    one is built from ``settings``.
    """

    built = built or build_services(settings)
    app = create_app(services=built.services)

    verifier = CognitoJwtVerifier.from_cognito(
        region=settings.cognito_region,
        user_pool_id=settings.cognito_user_pool_id,
        app_client_id=settings.cognito_app_client_id,
    )
    set_verifier(app, verifier)

    # Install the configured app on the Lambda HTTP adapter so the module-level
    # handler serves this wired app rather than a default one.
    http_adapter.set_app(app)
    return app


def build_worker(settings: Settings, built: BuiltServices | None = None) -> GradingWorker:
    """Construct the boto3-backed grading worker and register it (Req 7.1).

    Builds a :class:`GradingPipeline` wired to the shared boto3-backed
    repositories, object store, review queue, grading engine, confidence gate,
    health card service, eventing, and routing (the routing agent is adapted to
    the pipeline's ``route(item_id)`` seam via :class:`CallableRouter`). The
    pipeline is constructed once and handed to the :class:`GradingWorker` through
    a zero-arg ``pipeline_provider`` so the worker reuses it across the batch,
    then registered on the SQS entrypoint seam via
    :func:`rebridge_api.worker.set_worker`.
    """

    built = built or build_services(settings)

    def dummy_pixel_decoder(raw: bytes) -> list[list[float]]:
        # Dummy decoder that returns a sharp 3x3 matrix so precheck passes
        return [[10.0, 200.0, 10.0], [200.0, 10.0, 200.0], [10.0, 200.0, 10.0]]

    def value_estimator(meta, assessment):
        from rebridge_service.models import Grade
        grade = assessment.grade if assessment else Grade.ACCEPTABLE
        band = built.price_estimator.estimate(meta.category, grade, meta.age_months)
        return band.point

    pipeline = GradingPipeline(
        item_repo=built.item_repo,
        object_store=built.object_store,
        review_repo=built.review_repo,
        precheck=built.precheck,
        grading_engine=built.grading_engine,
        confidence_gate=built.confidence_gate,
        card_service=built.card_service,
        eventing=built.eventing,
        router=EventEmittingRouter(built.routing, built.eventing),
        pixel_decoder=dummy_pixel_decoder,
        value_estimator=value_estimator,
    )

    worker = GradingWorker(pipeline_provider=lambda: pipeline)
    set_worker(worker)
    return worker
