"""Routing adapter that emits ROUTED after persisting the decision.

The :class:`~rebridge_service.grading_pipeline.GradingPipeline` invokes an
injected router (its ``RoutingPort`` seam) on the auto-route step and expects
that router to BOTH persist the DECISION facet AND emit the ``ROUTED`` lifecycle
event (Requirement 15.2). :meth:`rebridge_service.routing_agent.RoutingAgent.decide`
only persists the decision — it does not emit — so wiring the pipeline's router
directly to ``RoutingAgent.decide`` (as the worker previously did via
``CallableRouter``) meant the asynchronous grade->auto-route path never emitted
``ROUTED``. Only the explicit ``POST /items/{id}/route`` endpoint did.

:class:`EventEmittingRouter` closes that gap: it satisfies the pipeline's
``RoutingPort`` protocol (``route(item_id) -> decision``) by delegating to the
``RoutingAgent`` and then emitting ``ROUTED`` through the ``EventingService``,
so the async path matches the explicit-route path. It lives in the API layer
because it is composition glue (api -> service), constructed by the composition
root in :mod:`rebridge_api.wiring`.
"""

from __future__ import annotations

from rebridge_service.eventing_service import EventingService
from rebridge_service.models import RoutingDecision
from rebridge_service.routing_agent import RoutingAgent

__all__ = ["EventEmittingRouter"]


class EventEmittingRouter:
    """A pipeline router that persists the decision and emits ROUTED.

    Implements the pipeline's ``RoutingPort`` structural contract: ``route``
    returns an object exposing ``.disposition``. Here it returns the
    :class:`RoutingDecision` produced by :meth:`RoutingAgent.decide` after
    emitting the corresponding ``ROUTED`` lifecycle event.
    """

    def __init__(self, routing: RoutingAgent, eventing: EventingService) -> None:
        self._routing = routing
        self._eventing = eventing

    def route(self, item_id: str) -> RoutingDecision:
        decision = self._routing.decide(item_id)
        try:
            self._eventing.emit_routed(item_id, decision.disposition)
        except Exception:
            # Fallback: the decision is persisted, so we return it even if
            # the downstream event emission fails.
            pass
        return decision
