"""Tests for the EventBridge-backed EventPublisher (Requirement 15.1-15.5).

These use ``moto`` to stand up an in-memory EventBridge bus so the publishing of
a :class:`LifecycleEvent` through ``publish`` can be exercised without touching
real AWS. moto's EventBridge support validates and accepts ``PutEvents`` calls
(returning ``Entries`` with event ids and a zero ``FailedEntryCount``) but does
not retain delivered entries for later inspection, so to assert the exact
request shape (Source / DetailType / Detail JSON / EventBusName) we also drive
the publisher against a recording stub. The moto tests prove the publisher
issues a real, well-formed ``PutEvents`` call; the stub tests prove the envelope
contents map correctly from the domain event.
"""

import json

import boto3
import pytest
from moto import mock_aws

from rebridge_data.eventbridge_publisher import EventBridgePublisher
from rebridge_data.interfaces import EventPublisher
from rebridge_data.models import LifecycleEvent

REGION = "us-east-1"
BUS_NAME = "rebridge-lifecycle-bus"


@pytest.fixture()
def event_bus():
    """Create a fresh mocked EventBridge bus and yield (client, bus_name)."""
    with mock_aws():
        events = boto3.client("events", region_name=REGION)
        events.create_event_bus(Name=BUS_NAME)
        yield events, BUS_NAME


class _RecordingEventsClient:
    """Minimal stub recording the kwargs passed to ``put_events``.

    Mimics a successful EventBridge response (one accepted entry, no failures).
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_events(self, **kwargs):
        self.calls.append(kwargs)
        entries = kwargs.get("Entries", [])
        return {
            "FailedEntryCount": 0,
            "Entries": [{"EventId": f"evt-{i}"} for i in range(len(entries))],
        }


class _FailingEventsClient:
    """Stub that reports a failed entry, to exercise the error path."""

    def put_events(self, **kwargs):
        return {
            "FailedEntryCount": 1,
            "Entries": [
                {
                    "ErrorCode": "InternalException",
                    "ErrorMessage": "bus unavailable",
                }
            ],
        }


# --- moto-backed tests: real, well-formed PutEvents round-trip ---------------


def test_implements_event_publisher_interface(event_bus):
    events, bus_name = event_bus
    publisher = EventBridgePublisher(bus_name, client=events)
    assert isinstance(publisher, EventPublisher)


def test_publish_succeeds_against_moto_bus(event_bus):
    events, bus_name = event_bus
    publisher = EventBridgePublisher(bus_name, client=events)

    # Should not raise: moto accepts the PutEvents call with no failed entries.
    publisher.publish(
        LifecycleEvent(
            event_type="GRADED",
            item_id="item-123",
            payload={"grade": "Very Good"},
        )
    )


@pytest.mark.parametrize(
    "event_type",
    ["GRADED", "ROUTED", "LISTED", "MATCHED", "SOLD"],
)
def test_publish_all_lifecycle_event_types_against_moto(event_bus, event_type):
    events, bus_name = event_bus
    publisher = EventBridgePublisher(bus_name, client=events)
    # Each of the five lifecycle events publishes cleanly (Req 15.1-15.5).
    publisher.publish(LifecycleEvent(event_type=event_type, item_id="item-x"))


# --- stub-backed tests: exact request/envelope shape -------------------------


def test_publish_sends_single_entry_with_expected_envelope():
    stub = _RecordingEventsClient()
    publisher = EventBridgePublisher(BUS_NAME, client=stub)

    publisher.publish(
        LifecycleEvent(
            event_type="ROUTED",
            item_id="item-77",
            payload={"disposition": "RESELL"},
        )
    )

    assert len(stub.calls) == 1
    entries = stub.calls[0]["Entries"]
    assert len(entries) == 1
    entry = entries[0]

    assert entry["Source"] == "rebridge.lifecycle"
    assert entry["DetailType"] == "ROUTED"
    assert entry["EventBusName"] == BUS_NAME

    detail = json.loads(entry["Detail"])
    assert detail == {
        "event_type": "ROUTED",
        "item_id": "item-77",
        "payload": {"disposition": "RESELL"},
    }


def test_detail_json_identifies_item_with_empty_payload():
    stub = _RecordingEventsClient()
    publisher = EventBridgePublisher(BUS_NAME, client=stub)

    publisher.publish(LifecycleEvent(event_type="SOLD", item_id="item-9"))

    detail = json.loads(stub.calls[0]["Entries"][0]["Detail"])
    assert detail["event_type"] == "SOLD"
    assert detail["item_id"] == "item-9"
    assert detail["payload"] == {}


def test_custom_source_is_applied_to_entry():
    stub = _RecordingEventsClient()
    publisher = EventBridgePublisher(
        BUS_NAME, source="my.custom.source", client=stub
    )

    publisher.publish(LifecycleEvent(event_type="LISTED", item_id="item-1"))

    assert stub.calls[0]["Entries"][0]["Source"] == "my.custom.source"


def test_failed_entry_raises_runtime_error():
    publisher = EventBridgePublisher(BUS_NAME, client=_FailingEventsClient())

    with pytest.raises(RuntimeError) as excinfo:
        publisher.publish(LifecycleEvent(event_type="GRADED", item_id="item-err"))

    message = str(excinfo.value)
    assert "GRADED" in message
    assert "item-err" in message
    assert "bus unavailable" in message
