"""Tests for the SQS-backed QueueClient (Requirement 7.1).

These use ``moto`` to stand up an in-memory SQS queue so the round-trip of a
:class:`GradingMessage` through ``send_grading_message`` can be asserted without
touching real AWS.
"""

import json

import boto3
import pytest
from moto import mock_aws

from rebridge_data.interfaces import QueueClient
from rebridge_data.models import GradingMessage
from rebridge_data.sqs_queue_client import SqsQueueClient

REGION = "us-east-1"


@pytest.fixture()
def sqs_queue():
    """Create a fresh mocked SQS queue and yield (client, queue_url)."""
    with mock_aws():
        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="rebridge-grading")["QueueUrl"]
        yield sqs, queue_url


def _receive_one(sqs, queue_url):
    resp = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)
    messages = resp.get("Messages", [])
    assert len(messages) == 1
    return messages[0]


def test_implements_queue_client_interface(sqs_queue):
    sqs, queue_url = sqs_queue
    client = SqsQueueClient(queue_url, sqs_client=sqs)
    assert isinstance(client, QueueClient)


def test_send_grading_message_round_trips_payload(sqs_queue):
    sqs, queue_url = sqs_queue
    client = SqsQueueClient(queue_url, sqs_client=sqs)

    msg = GradingMessage(
        item_id="item-123",
        idem_key="idem-abc",
        photo_keys=["photos/a.jpg", "photos/b.jpg"],
    )
    client.send_grading_message(msg)

    received = _receive_one(sqs, queue_url)
    payload = json.loads(received["Body"])

    assert payload["item_id"] == "item-123"
    assert payload["idem_key"] == "idem-abc"
    assert payload["photo_keys"] == ["photos/a.jpg", "photos/b.jpg"]


def test_send_grading_message_with_empty_photo_keys(sqs_queue):
    sqs, queue_url = sqs_queue
    client = SqsQueueClient(queue_url, sqs_client=sqs)

    msg = GradingMessage(item_id="item-0", idem_key="k0", photo_keys=[])
    client.send_grading_message(msg)

    received = _receive_one(sqs, queue_url)
    payload = json.loads(received["Body"])

    assert payload["item_id"] == "item-0"
    assert payload["idem_key"] == "k0"
    assert payload["photo_keys"] == []


def test_each_send_enqueues_a_distinct_message(sqs_queue):
    sqs, queue_url = sqs_queue
    client = SqsQueueClient(queue_url, sqs_client=sqs)

    client.send_grading_message(GradingMessage("i1", "k1", ["p1.jpg"]))
    client.send_grading_message(GradingMessage("i2", "k2", ["p2.jpg"]))

    resp = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
    bodies = [json.loads(m["Body"])["item_id"] for m in resp.get("Messages", [])]
    assert sorted(bodies) == ["i1", "i2"]
