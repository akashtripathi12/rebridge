"""EventingService: lifecycle event emission through the EventPublisher seam.

This is the business-logic component that satisfies Requirement 15 (design.md →
"Components and Interfaces → Service Layer → EventingService"). It is programmed
entirely against the abstract :class:`rebridge_data.interfaces.EventPublisher`
gateway and constructs the persistence-shaped
:class:`rebridge_data.models.LifecycleEvent` records that flow through it. It
never imports boto3 or any web framework — the concrete EventBridge-backed
publisher is built and injected by the API composition root.

Responsibilities implemented here (task 14.1):

* Provide one helper per lifecycle transition that builds the correct event and
  publishes it:

  * :meth:`emit_graded` — a confirmed grade was persisted (Requirement 15.1).
  * :meth:`emit_routed` — the Routing_Agent persisted a decision; the event
    carries the selected disposition (Requirement 15.2).
  * :meth:`emit_listed` — a listing was created for an Item (Requirement 15.3).
  * :meth:`emit_matched` — the Demand_Matching_Engine pushed to ranked buyers
    (Requirement 15.4).
  * :meth:`emit_sold` — an Item was sold (Requirement 15.5).

Each event identifies the Item by ``item_id``; the ROUTED event additionally
carries the disposition under ``payload["disposition"]``.

### Integration (wiring) note

This task implements the service itself. The actual emission **call sites** are
wired in when the corresponding orchestrations are assembled:

* ``emit_graded`` — from the review confirm/override path and the grading
  pipeline's grade-confirmation step (`ReviewConsoleService` / `GradingPipeline`).
* ``emit_routed`` — from the `RoutingAgent` immediately after the DECISION facet
  is persisted.
* ``emit_listed`` — from `ItemService.create_listing` after the LISTING facet is
  persisted.
* ``emit_matched`` — from `DemandMatchingEngine` after the top-N push / PDP shelf
  upsert.
* ``emit_sold`` — from the sale-completion path that transitions an Item to SOLD.

Those collaborators receive an ``EventingService`` instance via their
constructors and call the matching helper at the point of the transition.
"""

from __future__ import annotations

from dataclasses import dataclass

from rebridge_data.interfaces import EventPublisher
from rebridge_data.models import LifecycleEvent

from rebridge_service.models import Disposition, EventType

__all__ = ["EventingService"]


@dataclass
class EventingService:
    """Emits GRADED, ROUTED, LISTED, MATCHED, SOLD lifecycle events (Req 15).

    The :class:`EventPublisher` collaborator is injected as an abstract
    interface, honoring the design's one-way ``service -> data`` dependency
    direction. Every helper builds a data-layer :class:`LifecycleEvent` whose
    ``event_type`` is the canonical string for the transition and whose
    ``item_id`` identifies the affected Item, then publishes it.
    """

    publisher: EventPublisher

    # -- lifecycle helpers -------------------------------------------------
    def emit_graded(self, item_id: str) -> LifecycleEvent:
        """Emit a GRADED event for ``item_id`` (Requirement 15.1)."""
        return self._publish(EventType.GRADED, item_id)

    def emit_routed(
        self,
        item_id: str,
        disposition: Disposition | str,
    ) -> LifecycleEvent:
        """Emit a ROUTED event identifying the Item and its disposition (15.2).

        ``disposition`` accepts either a :class:`Disposition` enum member or its
        string value; it is carried under ``payload["disposition"]`` as the
        canonical string so downstream consumers need not import the enum.
        """
        return self._publish(
            EventType.ROUTED,
            item_id,
            payload={"disposition": self._disposition_value(disposition)},
        )

    def emit_listed(self, item_id: str) -> LifecycleEvent:
        """Emit a LISTED event for ``item_id`` (Requirement 15.3)."""
        return self._publish(EventType.LISTED, item_id)

    def emit_matched(self, item_id: str) -> LifecycleEvent:
        """Emit a MATCHED event for ``item_id`` (Requirement 15.4)."""
        return self._publish(EventType.MATCHED, item_id)

    def emit_sold(self, item_id: str) -> LifecycleEvent:
        """Emit a SOLD event for ``item_id`` (Requirement 15.5)."""
        return self._publish(EventType.SOLD, item_id)

    # -- helpers -----------------------------------------------------------
    def _publish(
        self,
        event_type: EventType,
        item_id: str,
        payload: dict[str, object] | None = None,
    ) -> LifecycleEvent:
        """Build a data-layer :class:`LifecycleEvent` and publish it.

        Returns the event that was published so callers (and tests) can inspect
        exactly what was emitted.
        """
        event = LifecycleEvent(
            event_type=event_type.value,
            item_id=item_id,
            payload=payload or {},
        )
        self.publisher.publish(event)
        return event

    @staticmethod
    def _disposition_value(disposition: Disposition | str) -> str:
        """Normalize a disposition to its canonical string value."""
        return disposition.value if isinstance(disposition, Disposition) else disposition
