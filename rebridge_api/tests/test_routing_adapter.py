"""Unit test for the EventEmittingRouter (Fix 2: ROUTED on the async path).

The grading pipeline's auto-route step drives an injected router and expects it
to persist the decision AND emit ROUTED. EventEmittingRouter wraps the routing
agent with the eventing service to do exactly that, so the async grade->route
path emits ROUTED just like the explicit POST /items/{id}/route endpoint.
"""

from __future__ import annotations

from decimal import Decimal

from rebridge_api.routing_adapter import EventEmittingRouter
from rebridge_service.eventing_service import EventingService
from rebridge_service.models import Disposition, RoutingDecision

from tests.fakes import FakeEventPublisher


class _StubRoutingAgent:
    """Records decide() calls and returns a fixed decision."""

    def __init__(self, decision: RoutingDecision) -> None:
        self._decision = decision
        self.decided: list[str] = []

    def decide(self, item_id: str, *, geohash5: str | None = None) -> RoutingDecision:
        self.decided.append(item_id)
        return self._decision


def _decision() -> RoutingDecision:
    return RoutingDecision(
        disposition=Disposition.P2P,
        price=Decimal("36.00"),
        value=Decimal("36.00"),
        cost=Decimal("5.50"),
        margin=Decimal("30.50"),
        rationale="P2P selected: highest-margin viable path.",
    )


def test_route_persists_decision_and_emits_routed():
    publisher = FakeEventPublisher()
    eventing = EventingService(publisher)
    agent = _StubRoutingAgent(_decision())
    router = EventEmittingRouter(agent, eventing)

    result = router.route("itm_1")

    # The agent was asked to decide and the decision is returned unchanged.
    assert agent.decided == ["itm_1"]
    assert result.disposition is Disposition.P2P

    # Exactly one ROUTED event, identifying the item and carrying the disposition.
    routed = publisher.events_of("ROUTED")
    assert len(routed) == 1
    assert routed[0].item_id == "itm_1"
    assert routed[0].payload.get("disposition") == "P2P"
