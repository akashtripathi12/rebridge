"""Tests for the EventBridge-backed demand-matching gateways.

EventBridgeBuyerNotifier and EventBridgeSecondChanceShelf realize the two
Demand_Matching_Engine side-effect seams as lifecycle events on the shared bus.
These assert each publishes the right detail-type and payload through the
injected EventPublisher.
"""

from __future__ import annotations

from rebridge_data.eventbridge_demand_gateways import (
    BUYER_NOTIFIED_EVENT,
    SHELF_UPSERTED_EVENT,
    EventBridgeBuyerNotifier,
    EventBridgeSecondChanceShelf,
)
from rebridge_data.interfaces import BuyerNotifier, EventPublisher, SecondChanceShelf
from rebridge_data.models import LifecycleEvent


class _RecordingPublisher(EventPublisher):
    """Captures published LifecycleEvents instead of calling AWS."""

    def __init__(self) -> None:
        self.events: list[LifecycleEvent] = []

    def publish(self, event: LifecycleEvent) -> None:
        self.events.append(event)


def test_buyer_notifier_is_a_buyer_notifier():
    assert isinstance(EventBridgeBuyerNotifier(_RecordingPublisher()), BuyerNotifier)


def test_shelf_is_a_second_chance_shelf():
    assert isinstance(EventBridgeSecondChanceShelf(_RecordingPublisher()), SecondChanceShelf)


def test_notify_publishes_buyer_notified_event_with_buyer_and_item():
    pub = _RecordingPublisher()
    EventBridgeBuyerNotifier(pub).notify("buy_001", "itm_1")

    assert len(pub.events) == 1
    event = pub.events[0]
    assert event.event_type == BUYER_NOTIFIED_EVENT
    assert event.item_id == "itm_1"
    assert event.payload == {"buyer_id": "buy_001"}


def test_upsert_publishes_shelf_upserted_event_for_item():
    pub = _RecordingPublisher()
    EventBridgeSecondChanceShelf(pub).upsert("itm_1")

    assert len(pub.events) == 1
    event = pub.events[0]
    assert event.event_type == SHELF_UPSERTED_EVENT
    assert event.item_id == "itm_1"


def test_repeated_upsert_emits_one_event_each_idempotent_by_item():
    pub = _RecordingPublisher()
    shelf = EventBridgeSecondChanceShelf(pub)
    shelf.upsert("itm_1")
    shelf.upsert("itm_1")
    # Each call emits a placement event; the consumer upserts by item id, so
    # re-placement is harmless.
    assert all(e.event_type == SHELF_UPSERTED_EVENT for e in pub.events)
    assert {e.item_id for e in pub.events} == {"itm_1"}
