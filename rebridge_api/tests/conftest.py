"""Shared fixtures: a Services container wired to in-memory fakes + TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rebridge_api import Services, create_app
from rebridge_api.dependencies import CurrentUser, get_current_user
from rebridge_data.models import BuyerPersona
from rebridge_data.seeded_buyer_persona_repository import SeededBuyerPersonaRepository
from rebridge_service.demand_matching_engine import DemandMatchingEngine
from rebridge_service.eventing_service import EventingService
from rebridge_service.health_card_service import HealthCardService
from rebridge_service.item_service import ItemService
from rebridge_service.review_console_service import ReviewConsoleService
from rebridge_service.routing_agent import RoutingAgent
from rebridge_service.routing_tools import CostModel, PriceEstimator

from tests.fakes import (
    FakeBuyerNotifier,
    FakeCardSigner,
    FakeEventPublisher,
    FakeItemRepository,
    FakeObjectStore,
    FakeQueueClient,
    FakeReviewQueueRepository,
    FakeSecondChanceShelf,
)


# A small spread of seeded personas across categories and neighborhoods so the
# matches route returns ranked buyers with varied persona types in tests.
SEED_PERSONAS = [
    BuyerPersona(
        buyer_id="buy_001",
        geohash5="9q8yy",
        persona_type="deal_seeker",
        category_interests=["electronics", "home"],
        intent=0.90,
        lifecycle=0.60,
        price_sensitivity=0.90,
    ),
    BuyerPersona(
        buyer_id="buy_002",
        geohash5="9q8yy",
        persona_type="price_balker",
        category_interests=["electronics"],
        intent=0.70,
        lifecycle=0.55,
        price_sensitivity=0.95,
    ),
    BuyerPersona(
        buyer_id="buy_003",
        geohash5="9q8yz",
        persona_type="browser",
        category_interests=["electronics", "books"],
        intent=0.40,
        lifecycle=0.30,
        price_sensitivity=0.50,
    ),
    BuyerPersona(
        buyer_id="buy_004",
        geohash5="9q5ct",
        persona_type="collector",
        category_interests=["books"],
        intent=0.72,
        lifecycle=0.52,
        price_sensitivity=0.30,
    ),
    BuyerPersona(
        buyer_id="buy_005",
        geohash5="dr5ru",
        persona_type="gifter",
        category_interests=["toys", "apparel"],
        intent=0.55,
        lifecycle=0.50,
        price_sensitivity=0.60,
    ),
]


class Harness:
    """Bundles the fakes and the wired app so tests can assert on both."""

    def __init__(self) -> None:
        self.item_repo = FakeItemRepository()
        self.object_store = FakeObjectStore()
        self.queue = FakeQueueClient()
        self.publisher = FakeEventPublisher()
        self.signer = FakeCardSigner()
        self.review_repo = FakeReviewQueueRepository()
        self.buyers = SeededBuyerPersonaRepository(SEED_PERSONAS)

        self.eventing = EventingService(self.publisher)
        self.item_service = ItemService(self.item_repo, self.object_store, eventing=self.eventing)
        self.routing = RoutingAgent(
            price=PriceEstimator(),
            cost=CostModel(),
            item_repo=self.item_repo,
        )
        self.card_service = HealthCardService(self.signer, self.item_repo)
        self.review_console = ReviewConsoleService(self.item_repo, self.review_repo)
        # Engine B fully wired (notifier + shelf + shared eventing) so that
        # creating a listing triggers match() -> notify + shelf + MATCHED, the
        # same as production wiring.
        self.notifier = FakeBuyerNotifier()
        self.shelf = FakeSecondChanceShelf()
        self.matching = DemandMatchingEngine(
            self.buyers,
            notifier=self.notifier,
            shelf=self.shelf,
            eventing=self.eventing,
            top_n=5,
        )

        self.services = Services(
            item_service=self.item_service,
            routing=self.routing,
            eventing=self.eventing,
            queue=self.queue,
            item_repo=self.item_repo,
            card_service=self.card_service,
            matching=self.matching,
            review=self.review_console,
        )
        self.app = create_app(services=self.services)
        # These route tests exercise the service wiring, not authentication, so
        # override the auth dependency with a stub principal. The stub carries the
        # operator role so the back-office routes (create/grade/route/listing
        # CRUD/review) admit it; the dedicated auth tests (test_auth.py) build an
        # app with a real verifier, and the RBAC tests (test_rbac.py) override
        # this with customer/operator principals to assert the 403 boundary.
        self.app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            subject="test-user", claims={"sub": "test-user"}, role="operator"
        )
        self.client = TestClient(self.app)


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(harness: Harness) -> TestClient:
    return harness.client
