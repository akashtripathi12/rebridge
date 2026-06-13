"""Unit tests for :class:`rebridge_service.eventing_service.EventingService`.

Covers task 14.1: each lifecycle helper emits the correct lifecycle event
through the injected :class:`EventPublisher`, identifying the Item; the ROUTED
event additionally carries the selected disposition (Requirements 15.1–15.5).

The service is exercised against the in-memory :class:`FakeEventPublisher`
(the data-layer gateway seam) so there are no AWS calls.
"""

from __future__ import annotations

import pytest

from rebridge_data.models import LifecycleEvent

from rebridge_service.eventing_service import EventingService
from rebridge_service.models import Disposition

from tests.fakes import FakeEventPublisher


def _service() -> tuple[EventingService, FakeEventPublisher]:
    publisher = FakeEventPublisher()
    return EventingService(publisher=publisher), publisher


# -- GRADED (15.1) --------------------------------------------------------
def test_emit_graded_publishes_graded_event_identifying_item():
    svc, pub = _service()

    returned = svc.emit_graded("item-1")

    assert pub.events == [LifecycleEvent(event_type="GRADED", item_id="item-1")]
    assert returned.event_type == "GRADED"
    assert returned.item_id == "item-1"
    assert returned.payload == {}


# -- ROUTED (15.2) --------------------------------------------------------
def test_emit_routed_carries_disposition_in_payload():
    svc, pub = _service()

    svc.emit_routed("item-2", Disposition.RESELL)

    assert pub.events == [
        LifecycleEvent(
            event_type="ROUTED",
            item_id="item-2",
            payload={"disposition": "RESELL"},
        )
    ]


@pytest.mark.parametrize(
    "disposition",
    list(Disposition),
)
def test_emit_routed_accepts_every_disposition(disposition: Disposition):
    svc, pub = _service()

    svc.emit_routed("item-3", disposition)

    (event,) = pub.events_of("ROUTED")
    assert event.item_id == "item-3"
    assert event.payload["disposition"] == disposition.value


def test_emit_routed_accepts_plain_string_disposition():
    svc, pub = _service()

    svc.emit_routed("item-4", "DONATE")

    (event,) = pub.events_of("ROUTED")
    assert event.payload == {"disposition": "DONATE"}


# -- LISTED (15.3) --------------------------------------------------------
def test_emit_listed_publishes_listed_event_identifying_item():
    svc, pub = _service()

    svc.emit_listed("item-5")

    assert pub.events == [LifecycleEvent(event_type="LISTED", item_id="item-5")]


# -- MATCHED (15.4) -------------------------------------------------------
def test_emit_matched_publishes_matched_event_identifying_item():
    svc, pub = _service()

    svc.emit_matched("item-6")

    assert pub.events == [LifecycleEvent(event_type="MATCHED", item_id="item-6")]


# -- SOLD (15.5) ----------------------------------------------------------
def test_emit_sold_publishes_sold_event_identifying_item():
    svc, pub = _service()

    svc.emit_sold("item-7")

    assert pub.events == [LifecycleEvent(event_type="SOLD", item_id="item-7")]


# -- non-routed events carry no disposition payload -----------------------
def test_non_routed_events_have_empty_payload():
    svc, pub = _service()

    svc.emit_graded("i")
    svc.emit_listed("i")
    svc.emit_matched("i")
    svc.emit_sold("i")

    assert all(event.payload == {} for event in pub.events)


# -- ordering / multiple transitions --------------------------------------
def test_events_are_published_in_call_order():
    svc, pub = _service()

    svc.emit_graded("item-8")
    svc.emit_routed("item-8", Disposition.P2P)
    svc.emit_listed("item-8")
    svc.emit_matched("item-8")
    svc.emit_sold("item-8")

    assert [e.event_type for e in pub.events] == [
        "GRADED",
        "ROUTED",
        "LISTED",
        "MATCHED",
        "SOLD",
    ]
    assert all(e.item_id == "item-8" for e in pub.events)
