"""Unit tests for the composition root (task 17.8, ``rebridge_api.wiring``).

These tests build :class:`Settings` from an explicit mapping, then call
:func:`build_services`, :func:`build_app`, and :func:`build_worker` with that
config and assert the wiring is correct. boto3 client/resource construction is
offline -- the gateways are created but never invoked, and ``moto``'s
``mock_aws`` is wrapped around construction so no real AWS endpoint is touched.

Coverage:
* Settings load from a dict/env, including the 0.80 confidence-threshold default
  (Req 6.3) and its override.
* ``build_services`` populates the ``Services`` container with the right service
  types and constructs the data concretes once (shared item repo).
* The grading engine has the two providers in cascade order (Req 8.4).
* ``build_app`` returns a FastAPI app with a verifier attached.
* ``build_worker`` registers a worker driving a boto3-backed pipeline.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from moto import mock_aws

from rebridge_api import (
    Settings,
    build_app,
    build_services,
    build_worker,
)
from rebridge_api import http_adapter, worker as worker_module
from rebridge_api.auth import CognitoJwtVerifier
from rebridge_api.dependencies import Services
from rebridge_data.bedrock_grading_providers import (
    BedrockNovaLiteProvider,
    ClaudeVisionProvider,
)
from rebridge_data.dynamo_item_repository import DynamoItemRepository
from rebridge_data.s3_object_store import S3ObjectStore
from rebridge_data.sqs_queue_client import SqsQueueClient
from rebridge_service.confidence_gate import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
)
from rebridge_service.eventing_service import EventingService
from rebridge_service.item_service import ItemService
from rebridge_service.routing_agent import RoutingAgent


# A representative deployment-style configuration mapping.
ENV = {
    "REBRIDGE_TABLE_NAME": "rebridge-prod",
    "REBRIDGE_PHOTO_BUCKET": "rebridge-prod-photos",
    "REBRIDGE_GRADING_QUEUE_URL": "https://sqs.us-west-2.amazonaws.com/123/grading",
    "REBRIDGE_KMS_KEY_ID": "alias/rebridge-prod-cards",
    "REBRIDGE_EVENT_BUS": "rebridge-prod-bus",
    "REBRIDGE_REGION": "us-west-2",
    "REBRIDGE_TOP_N": "7",
    "REBRIDGE_MODEL_TIMEOUT": "2.5",
    "REBRIDGE_COGNITO_USER_POOL_ID": "us-west-2_pool",
    "REBRIDGE_COGNITO_APP_CLIENT_ID": "client-123",
}


@pytest.fixture(autouse=True)
def _reset_module_seams():
    """Keep the module-level app/worker seams clean between tests."""
    http_adapter.reset_app()
    worker_module.set_worker(None)
    yield
    http_adapter.reset_app()
    worker_module.set_worker(None)


# -- Settings ---------------------------------------------------------------


def test_settings_from_env_reads_keys_and_defaults():
    settings = Settings.from_env(ENV)

    assert settings.table_name == "rebridge-prod"
    assert settings.photo_bucket == "rebridge-prod-photos"
    assert settings.grading_queue_url.endswith("/grading")
    assert settings.kms_key_id == "alias/rebridge-prod-cards"
    assert settings.event_bus == "rebridge-prod-bus"
    assert settings.region == "us-west-2"
    assert settings.top_n == 7
    assert settings.model_timeout == 2.5
    # cognito_region defaults to the main region when not separately set.
    assert settings.cognito_region == "us-west-2"
    assert settings.cognito_user_pool_id == "us-west-2_pool"
    assert settings.cognito_app_client_id == "client-123"


def test_settings_confidence_threshold_defaults_to_080():
    # Req 6.3: default Confidence_Threshold is 0.80 when config omits it.
    settings = Settings.from_env({})
    assert settings.confidence_threshold == pytest.approx(0.80)
    assert settings.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_settings_confidence_threshold_overridable():
    settings = Settings.from_env({"REBRIDGE_CONFIDENCE_THRESHOLD": "0.65"})
    assert settings.confidence_threshold == pytest.approx(0.65)


def test_settings_empty_env_is_constructible_with_defaults():
    settings = Settings.from_env({})
    assert settings.confidence_threshold == pytest.approx(0.80)
    assert settings.top_n == 5
    assert settings.region == "us-east-1"


# -- build_services ---------------------------------------------------------


def test_build_services_populates_container_with_right_types():
    with mock_aws():
        built = build_services(Settings.from_env(ENV))

    services = built.services
    assert isinstance(services, Services)
    assert isinstance(services.item_service, ItemService)
    assert isinstance(services.routing, RoutingAgent)
    assert isinstance(services.eventing, EventingService)
    assert isinstance(services.queue, SqsQueueClient)
    assert isinstance(services.item_repo, DynamoItemRepository)
    # card_service is present so the public verify route can resolve cards.
    assert services.card_service is not None


def test_build_services_constructs_data_concretes_once():
    # The same item repository instance is shared by the ItemService, the
    # routing agent, and the router container (built exactly once).
    with mock_aws():
        built = build_services(Settings.from_env(ENV))

    assert built.services.item_repo is built.item_repo
    assert built.services.item_service.item_repo is built.item_repo
    assert built.routing.item_repo is built.item_repo
    assert isinstance(built.object_store, S3ObjectStore)


def test_confidence_gate_defaults_to_080():
    # Req 6.3: with no override the gate threshold is 0.80.
    with mock_aws():
        built = build_services(Settings.from_env({}))
    assert isinstance(built.confidence_gate, ConfidenceGate)
    assert built.confidence_gate.threshold == pytest.approx(0.80)


def test_confidence_gate_threshold_overridable_via_config():
    with mock_aws():
        built = build_services(
            Settings.from_env({"REBRIDGE_CONFIDENCE_THRESHOLD": "0.5"})
        )
    assert built.confidence_gate.threshold == pytest.approx(0.5)


def test_grading_engine_cascade_is_nova_then_claude():
    # Req 8.4: the cascade is [Nova Lite, Claude vision] in that order.
    with mock_aws():
        built = build_services(Settings.from_env(ENV))

    providers = built.grading_engine.providers
    assert len(providers) == 2
    assert isinstance(providers[0], BedrockNovaLiteProvider)
    assert isinstance(providers[1], ClaudeVisionProvider)
    assert providers[0].name == "nova-lite"
    assert providers[1].name == "claude-vision"


def test_grading_engine_uses_configured_timeout():
    with mock_aws():
        built = build_services(Settings.from_env(ENV))
    # The configured per-call timeout is threaded into the engine.
    assert built.grading_engine._timeout == pytest.approx(2.5)


# -- build_app --------------------------------------------------------------


def test_build_app_returns_fastapi_with_verifier_attached():
    with mock_aws():
        app = build_app(Settings.from_env(ENV))

    assert isinstance(app, FastAPI)
    # A Services container is attached to app state.
    assert isinstance(app.state.services, Services)
    # A Cognito JWT verifier is attached for private-route auth.
    verifier = app.state.jwt_verifier
    assert isinstance(verifier, CognitoJwtVerifier)
    assert verifier.app_client_id == "client-123"
    assert verifier.user_pool_id == "us-west-2_pool"


def test_build_app_installs_app_on_http_adapter():
    with mock_aws():
        app = build_app(Settings.from_env(ENV))
    # The configured app is installed on the Lambda HTTP adapter seam.
    assert http_adapter.get_app() is app


def test_build_app_reuses_supplied_built_services():
    with mock_aws():
        built = build_services(Settings.from_env(ENV))
        app = build_app(built.settings, built=built)
    assert app.state.services is built.services


# -- build_worker -----------------------------------------------------------


def test_build_worker_registers_worker_with_pipeline_provider():
    with mock_aws():
        built = build_services(Settings.from_env(ENV))
        returned = build_worker(built.settings, built=built)

    # The worker is registered on the module-level SQS entrypoint seam.
    assert worker_module.get_worker() is returned

    # The provider yields a pipeline wired to the shared boto3-backed repos.
    pipeline = returned.pipeline_provider()
    assert pipeline.item_repo is built.item_repo
    assert pipeline.review_repo is built.review_repo
    assert pipeline.object_store is built.object_store
    assert pipeline.grading_engine is built.grading_engine
    assert pipeline.confidence_gate is built.confidence_gate
    # The routing agent is adapted to the pipeline's route() seam.
    assert pipeline.router is not None


def test_build_worker_builds_services_when_not_supplied():
    with mock_aws():
        returned = build_worker(Settings.from_env(ENV))
    assert worker_module.get_worker() is returned
    assert returned.pipeline_provider() is not None


# -- import safety ----------------------------------------------------------


def test_importing_wiring_makes_no_aws_calls():
    # Constructing Settings and importing the module must not touch AWS. This
    # runs outside any moto mock; if construction called AWS it would fail.
    settings = Settings.from_env(ENV)
    built = build_services(settings)
    assert isinstance(built.services, Services)
