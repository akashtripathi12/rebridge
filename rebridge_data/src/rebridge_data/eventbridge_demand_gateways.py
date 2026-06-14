"""EventBridge-backed demand-matching side-effect gateways.

Concrete implementations of the two Demand_Matching_Engine side-effect seams,
:class:`~rebridge_data.interfaces.BuyerNotifier` and
:class:`~rebridge_data.interfaces.SecondChanceShelf` (Requirement 13.5). v1 ships
no dedicated buyer-notification channel and no separate PDP-shelf datastore, so
both effects are realized as lifecycle events on the **same** Amazon EventBridge
bus the rest of the system already publishes to.

This is what connects Engine B end to end with **no new external
infrastructure**: when the engine pushes a match, a ``BUYER_NOTIFIED`` event is
emitted per notified buyer and a ``SHELF_UPSERTED`` event is emitted for the
placed Item, alongside the engine's own ``MATCHED`` event. Downstream consumers
(a notification fan-out Lambda, the Second-Chance PDP rebuild) subscribe to
these detail-types as the production roadmap step; the events are real and
observable on the bus today.

Both gateways compose an existing :class:`~rebridge_data.interfaces.EventPublisher`
(the EventBridge publisher built by the composition root), so they reuse the one
configured bus and its error handling rather than constructing their own client.
``boto3`` is therefore not imported here, but these still belong to the data
layer because they are infrastructure gateways injected into the service engine.
"""

from __future__ import annotations

from rebridge_data.interfaces import BuyerNotifier, EventPublisher, SecondChanceShelf
from rebridge_data.models import LifecycleEvent

__all__ = [
    "BUYER_NOTIFIED_EVENT",
    "SHELF_UPSERTED_EVENT",
    "EventBridgeBuyerNotifier",
    "EventBridgeSecondChanceShelf",
]

# Detail-types for the two demand-matching side-effect events. They are distinct
# from the five core lifecycle EventTypes (GRADED/ROUTED/LISTED/MATCHED/SOLD);
# the data-layer LifecycleEvent.event_type is a free string, so no enum changes.
BUYER_NOTIFIED_EVENT = "BUYER_NOTIFIED"
SHELF_UPSERTED_EVENT = "SHELF_UPSERTED"


class EventBridgeBuyerNotifier(BuyerNotifier):
    """Notify a buyer by emitting a ``BUYER_NOTIFIED`` event on the bus.

    Composes the configured :class:`EventPublisher`; each :meth:`notify` publishes
    one lifecycle event identifying the Item and the notified buyer, so a
    downstream consumer can fan out to the buyer's channel (push / email / inbox).
    """

    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    def notify(self, buyer_id: str, item_id: str) -> None:
        self._publisher.publish(
            LifecycleEvent(
                event_type=BUYER_NOTIFIED_EVENT,
                item_id=item_id,
                payload={"buyer_id": buyer_id},
            )
        )


class EventBridgeSecondChanceShelf(SecondChanceShelf):
    """Place an Item on the Second-Chance shelf via a ``SHELF_UPSERTED`` event.

    Composes the configured :class:`EventPublisher`; :meth:`upsert` publishes one
    idempotent placement event for the Item so the Second-Chance PDP shelf
    rebuild consumer can feature it. Re-emitting for the same Item is harmless
    (the consumer upserts by Item id).
    """

    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    def upsert(self, item_id: str) -> None:
        self._publisher.publish(
            LifecycleEvent(
                event_type=SHELF_UPSERTED_EVENT,
                item_id=item_id,
                payload={},
            )
        )
