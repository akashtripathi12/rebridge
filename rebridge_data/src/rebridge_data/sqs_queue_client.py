"""Concrete SQS-backed :class:`QueueClient` implementation (Requirement 7.1).

This is one of the boto3-backed gateways that live exclusively in
``rebridge_data``. It serializes a :class:`GradingMessage` to JSON and enqueues
it on the configured SQS grading queue so the asynchronous worker Lambda can
later consume it and run the grading pipeline.

The queue URL is injected through the constructor; the concrete client is only
ever constructed by the composition root in ``rebridge_api``.
"""

from __future__ import annotations

import json
from typing import Any

import boto3

from rebridge_data.interfaces import QueueClient
from rebridge_data.models import GradingMessage


class SqsQueueClient(QueueClient):
    """Send grading messages to an SQS queue.

    Args:
        queue_url: The URL of the target SQS grading queue.
        sqs_client: An optional pre-built boto3 SQS client. When omitted, a
            default client is created via ``boto3.client("sqs")`` (optionally
            pinned to ``region_name``).
        region_name: Region used only when constructing the default client.
    """

    def __init__(
        self,
        queue_url: str,
        sqs_client: Any | None = None,
        region_name: str | None = None,
    ) -> None:
        self._queue_url = queue_url
        if sqs_client is not None:
            self._sqs = sqs_client
        elif region_name is not None:
            self._sqs = boto3.client("sqs", region_name=region_name)
        else:
            self._sqs = boto3.client("sqs")

    def send_grading_message(self, msg: GradingMessage) -> None:
        """Serialize ``msg`` to JSON and enqueue it on the grading queue."""
        body = json.dumps(
            {
                "item_id": msg.item_id,
                "idem_key": msg.idem_key,
                "photo_keys": list(msg.photo_keys),
            }
        )
        self._sqs.send_message(QueueUrl=self._queue_url, MessageBody=body)
