"""Shared fixtures: a Services container wired to in-memory fakes + TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rebridge_api import Services, create_app
from rebridge_api.dependencies import CurrentUser, get_current_user
from rebridge_service.eventing_service import EventingService
from rebridge_service.health_card_service import HealthCardService
from rebridge_service.item_service import ItemService
from rebridge_service.routing_agent import RoutingAgent
from rebridge_service.routing_tools import CostModel, PriceEstimator

from tests.fakes import (
    FakeCardSigner,
    FakeEventPublisher,
    FakeItemRepository,
    FakeObjectStore,
    FakeQueueClient,
)


class Harness:
    """Bundles the fakes and the wired app so tests can assert on both."""

    def __init__(self) -> None:
        self.item_repo = FakeItemRepository()
        self.object_store = FakeObjectStore()
        self.queue = FakeQueueClient()
        self.publisher = FakeEventPublisher()
        self.signer = FakeCardSigner()

        self.eventing = EventingService(self.publisher)
        self.item_service = ItemService(self.item_repo, self.object_store)
        self.routing = RoutingAgent(
            price=PriceEstimator(),
            cost=CostModel(),
            item_repo=self.item_repo,
        )
        self.card_service = HealthCardService(self.signer, self.item_repo)

        self.services = Services(
            item_service=self.item_service,
            routing=self.routing,
            eventing=self.eventing,
            queue=self.queue,
            item_repo=self.item_repo,
            card_service=self.card_service,
        )
        self.app = create_app(services=self.services)
        # These route tests exercise the service wiring, not authentication, so
        # override the auth dependency with a stub principal. The dedicated auth
        # tests (test_auth.py) build an app with a real verifier instead.
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            subject="test-user", claims={"sub": "test-user"}
        )
        self.client = TestClient(self.app)


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(harness: Harness) -> TestClient:
    return harness.client
