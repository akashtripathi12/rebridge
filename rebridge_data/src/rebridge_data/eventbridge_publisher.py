"""EventBridge-backed lifecycle :class:`EventPublisher` implementation.

Concrete :class:`~rebridge_data.interfaces.EventPublisher` that emits the
ReBridge lifecycle events (GRADED, ROUTED, LISTED, MATCHED, SOLD) onto a
configured Amazon EventBridge event bus (Requirement 15.1-15.5). Downstream
consumers (analytics via Firehose, the demand-matching consumer) subscribe to
this bus and react to item progress.

Each :class:`~rebridge_data.models.LifecycleEvent` is mapped to a single
EventBridge ``PutEvents`` entry with the following envelope:

* ``Source``     — a configurable namespace identifying ReBridge as the emitter
  (default ``"rebridge.lifecycle"``).
* ``DetailType`` — the lifecycle ``event_type`` (e.g. ``"GRADED"``), so rule
  patterns can route on detail-type.
* ``Detail``     — a JSON document carrying ``event_type``, ``item_id`` and the
  event ``payload``, so every consumer can identify the Item (Requirement 15).
* ``EventBusName`` — the injected target bus name.

``boto3`` is imported here because the data layer is the only layer permitted to
depend on it. The EventBridge client is injectable so the publisher can be
exercised against moto / a stub in tests without real AWS calls. The bus name
and source are injected through the constructor; the concrete publisher is only
ever constructed by the composition root in ``rebridge_api``.
"""

from __future__ import annotations

import json
from typing import Any

import boto3

from rebridge_data.interfaces import EventPublisher
from rebridge_data.models import LifecycleEvent

__all__ = ["EventBridgePublisher"]

# Default emitter namespace used as the EventBridge entry ``Source`` when the
# caller does not override it.
_DEFAULT_SOURCE = "rebridge.lifecycle"


class EventBridgePublisher(EventPublisher):
    """Publish lifecycle events to a configured EventBridge bus.

    Args:
        event_bus_name: The name of the target EventBridge event bus.
        source: The ``Source`` namespace stamped on every emitted entry.
            Defaults to ``"rebridge.lifecycle"``.
        client: Optional pre-built EventBridge (``events``) client (or any
            object exposing a ``put_events`` method). When omitted, a boto3
            ``events`` client is constructed. Injecting a client keeps unit
            tests free of real AWS calls.
        region_name: Optional region used only when constructing the default
            boto3 client.
    """

    def __init__(
        self,
        event_bus_name: str,
        *,
        source: str = _DEFAULT_SOURCE,
        client: Any | None = None,
        region_name: str | None = None,
    ) -> None:
        self._event_bus_name = event_bus_name
        self._source = source
        self._client = (
            client
            if client is not None
            else boto3.client("events", region_name=region_name)
        )

    def publish(self, event: LifecycleEvent) -> None:
        """Emit ``event`` as a single ``PutEvents`` entry on the configured bus.

        Raises:
            RuntimeError: If EventBridge reports a failed entry
                (``FailedEntryCount`` greater than zero), so callers do not
                silently drop a lifecycle transition.
        """
        detail = json.dumps(
            {
                "event_type": event.event_type,
                "item_id": event.item_id,
                "payload": event.payload,
            }
        )
        response = self._client.put_events(
            Entries=[
                {
                    "Source": self._source,
                    "DetailType": event.event_type,
                    "Detail": detail,
                    "EventBusName": self._event_bus_name,
                }
            ]
        )
        failed = response.get("FailedEntryCount", 0)
        if failed:
            entries = response.get("Entries", [])
            reason = entries[0].get("ErrorMessage") if entries else "unknown error"
            raise RuntimeError(
                f"EventBridge rejected lifecycle event "
                f"{event.event_type} for item {event.item_id}: {reason}"
            )
