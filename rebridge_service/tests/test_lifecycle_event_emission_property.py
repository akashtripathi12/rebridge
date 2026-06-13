"""Property-based test for lifecycle event emission.

# Feature: rebridge-backend, Property 27: Lifecycle transitions emit their events

Property 27 (design.md): *For any* lifecycle transition (grade confirmed,
decision persisted, listing created, ranked-buyer push, sale), the
Event_Publisher SHALL emit the corresponding event (GRADED, ROUTED, LISTED,
MATCHED, SOLD) identifying the Item.

**Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5**

This test drives an arbitrary sequence of lifecycle emissions through the
:class:`EventingService` over arbitrary item ids (and arbitrary dispositions
for ROUTED), exercised against the in-memory :class:`FakeEventPublisher` (the
data-layer gateway seam, no AWS calls). It asserts the universal properties:

* every emission produces exactly one published event (no loss, no extras);
* each published event carries the correct canonical ``event_type`` for its
  transition and the ``item_id`` that was emitted;
* a ROUTED event carries its selected disposition under
  ``payload["disposition"]`` while every other event type carries an empty
  payload;
* events are published in the exact order the transitions occurred (call order).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.eventing_service import EventingService
from rebridge_service.models import Disposition, EventType

from .fakes import FakeEventPublisher


# A single lifecycle transition to emit. ``kind`` selects the helper to call;
# ``item_id`` is the arbitrary Item identifier; ``disposition`` is only consumed
# by the ROUTED transition (ignored otherwise).
_item_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=16,
)

_transition = st.fixed_dictionaries(
    {
        "kind": st.sampled_from(["graded", "routed", "listed", "matched", "sold"]),
        "item_id": _item_ids,
        "disposition": st.sampled_from(list(Disposition)),
    }
)

# Expected canonical event type emitted by each helper.
_EXPECTED_TYPE = {
    "graded": EventType.GRADED.value,
    "routed": EventType.ROUTED.value,
    "listed": EventType.LISTED.value,
    "matched": EventType.MATCHED.value,
    "sold": EventType.SOLD.value,
}


def _emit(service: EventingService, transition: dict) -> None:
    """Invoke the EventingService helper matching ``transition['kind']``."""
    kind = transition["kind"]
    item_id = transition["item_id"]
    if kind == "graded":
        service.emit_graded(item_id)
    elif kind == "routed":
        service.emit_routed(item_id, transition["disposition"])
    elif kind == "listed":
        service.emit_listed(item_id)
    elif kind == "matched":
        service.emit_matched(item_id)
    elif kind == "sold":
        service.emit_sold(item_id)
    else:  # pragma: no cover - defensive; strategy never yields other kinds
        raise AssertionError(f"unexpected transition kind: {kind}")


@settings(max_examples=200)
@given(transitions=st.lists(_transition, max_size=40))
def test_lifecycle_transitions_emit_their_events(transitions):
    publisher = FakeEventPublisher()
    service = EventingService(publisher=publisher)

    for transition in transitions:
        _emit(service, transition)

    # 1) Exactly one published event per transition (no loss, no extras).
    assert len(publisher.events) == len(transitions)

    # 2) Each event matches its transition in type, item id, and payload, and
    #    3) appears in the same order the transition was emitted (call order).
    for transition, event in zip(transitions, publisher.events):
        assert event.event_type == _EXPECTED_TYPE[transition["kind"]]
        assert event.item_id == transition["item_id"]
        if transition["kind"] == "routed":
            # ROUTED carries its selected disposition (Requirement 15.2).
            assert event.payload == {
                "disposition": transition["disposition"].value
            }
        else:
            # Every other lifecycle event identifies the Item with no payload.
            assert event.payload == {}
