"""End-to-end integration test for the async grading trigger (Requirement 7.1).

Requirement 7.1 says: *WHEN a photo set upload completes in S3, THE
Grading_Pipeline SHALL begin processing through an S3 event to SQS to Lambda
worker path.* This test exercises that path -- the **SQS -> Lambda worker** legs
end to end against a real (moto-mocked) SQS queue, plus the real
:class:`SqsQueueClient` producer and the real :class:`GradingWorker` consumer --
with only the terminal :class:`GradingPipeline` replaced by an injected fake so
we can observe exactly what the worker drives.

### What is real vs. simulated

``S3 upload completes --> S3 event --> SQS --> Lambda (worker) --> pipeline``

* **S3 event -> SQS enqueue (simulated):** In production an S3
  ``ObjectCreated``/upload-completion notification fans into a small handler
  that constructs a :class:`GradingMessage` (``item_id`` + ``idem_key`` +
  ``photo_keys``) and enqueues it via :class:`SqsQueueClient`. We represent that
  step directly by building the same :class:`GradingMessage` the completion
  handler would and enqueuing it through the **real** ``SqsQueueClient`` onto a
  moto SQS queue. This keeps the producer side faithful (real serialization,
  real ``send_message``) while not depending on the not-yet-wired S3
  notification glue.
* **SQS -> worker (real):** We ``receive_message`` from the moto queue and
  reshape the raw SQS message into the **SQS Lambda event envelope** the worker
  expects (``{"Records": [{"messageId", "body"}, ...]}``) -- exactly the
  transformation the Lambda event source mapping performs. This is the real wire
  contract: ``MessageId`` -> ``messageId`` and ``Body`` -> ``body``.
* **worker -> pipeline (real worker, fake pipeline):** We invoke the real
  :meth:`GradingWorker.handle` with a fake pipeline injected through the
  ``pipeline_provider`` seam and assert the worker parsed the SQS body back into
  a :class:`GradingMessage` and called ``pipeline.run`` with the right
  ``item_id`` / ``idem_key`` / ``photo_keys`` -- proving upload-completion
  triggers grading through the S3 -> SQS -> worker path.
"""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from rebridge_api.worker import GradingWorker
from rebridge_data.models import GradingMessage
from rebridge_data.sqs_queue_client import SqsQueueClient

REGION = "us-east-1"


# ---------------------------------------------------------------------------
# test doubles
# ---------------------------------------------------------------------------


class FakePipeline:
    """Stands in for the real ``GradingPipeline``; records every ``run`` call.

    The worker drives anything exposing ``run(message)``; in production this is
    the real pipeline. Capturing the messages lets us assert the worker handed
    the pipeline exactly the work the producer enqueued.
    """

    def __init__(self) -> None:
        self.calls: list[GradingMessage] = []

    def run(self, message: GradingMessage) -> None:
        self.calls.append(message)


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqs_queue():
    """Stand up a fresh moto SQS grading queue; yield (client, queue_url)."""
    with mock_aws():
        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName="rebridge-grading")["QueueUrl"]
        yield sqs, queue_url


def _drain_into_lambda_event(sqs, queue_url) -> dict:
    """Receive all queued messages and shape them as the SQS Lambda envelope.

    This mirrors what the AWS Lambda event source mapping does: each SQS message
    becomes a record with ``messageId`` (from ``MessageId``) and ``body`` (from
    ``Body``). Returns ``{"Records": [...]}`` as the worker's ``handle`` expects.
    """
    resp = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
    records = [
        {"messageId": m["MessageId"], "body": m["Body"]}
        for m in resp.get("Messages", [])
    ]
    return {"Records": records}


# ---------------------------------------------------------------------------
# end-to-end async trigger
# ---------------------------------------------------------------------------


def test_upload_completion_triggers_grading_through_s3_sqs_worker_path(sqs_queue):
    """Req 7.1: an enqueued upload-completion drives the pipeline via SQS->worker.

    Producer (real ``SqsQueueClient``) -> moto SQS -> Lambda event envelope ->
    real ``GradingWorker`` -> fake pipeline. The worker must run the pipeline
    once with a ``GradingMessage`` carrying the item id, idem key, and photo keys
    that the S3-completion handler enqueued.
    """
    sqs, queue_url = sqs_queue

    # --- S3 upload-completion -> SQS enqueue (the completion handler's job) ---
    # Represented directly: build the message the S3-completion handler would
    # send for the finished photo set and enqueue it through the real client.
    producer = SqsQueueClient(queue_url, sqs_client=sqs)
    uploaded = GradingMessage(
        item_id="item-async-1",
        idem_key="idem-async-1",
        photo_keys=["uploads/item-async-1/front.jpg", "uploads/item-async-1/back.jpg"],
    )
    producer.send_grading_message(uploaded)

    # --- SQS -> Lambda worker (event source mapping reshapes the message) ----
    event = _drain_into_lambda_event(sqs, queue_url)
    assert len(event["Records"]) == 1  # exactly the one upload-completion

    # --- worker -> pipeline (real worker, injected fake pipeline) ------------
    pipeline = FakePipeline()
    worker = GradingWorker(pipeline_provider=lambda: pipeline)
    resp = worker.handle(event)

    # Nothing redriven: the upload-completion was processed successfully.
    assert resp == {"batchItemFailures": []}

    # The worker ran grading exactly once with the enqueued work item.
    assert len(pipeline.calls) == 1
    graded = pipeline.calls[0]
    assert isinstance(graded, GradingMessage)
    assert graded.item_id == "item-async-1"
    assert graded.idem_key == "idem-async-1"
    assert graded.photo_keys == [
        "uploads/item-async-1/front.jpg",
        "uploads/item-async-1/back.jpg",
    ]


def test_round_trip_preserves_message_through_real_serialization(sqs_queue):
    """The SQS JSON round-trip preserves the grading payload byte-for-byte.

    Proves the producer's serialization and the worker's ``_parse_record`` are
    wire-compatible: what ``SqsQueueClient`` puts on the queue is exactly what the
    worker reconstructs, with no field drift across the S3->SQS->worker hop.
    """
    sqs, queue_url = sqs_queue

    producer = SqsQueueClient(queue_url, sqs_client=sqs)
    producer.send_grading_message(
        GradingMessage(item_id="i-2", idem_key="k-2", photo_keys=["p/only.jpg"])
    )

    # The raw body on the wire is the producer's JSON; confirm its shape before
    # the worker consumes it (the contract the Lambda mapping forwards verbatim).
    event = _drain_into_lambda_event(sqs, queue_url)
    body = json.loads(event["Records"][0]["body"])
    assert body == {
        "item_id": "i-2",
        "idem_key": "k-2",
        "photo_keys": ["p/only.jpg"],
    }

    pipeline = FakePipeline()
    GradingWorker(pipeline_provider=lambda: pipeline).handle(event)

    graded = pipeline.calls[0]
    assert (graded.item_id, graded.idem_key, graded.photo_keys) == (
        "i-2",
        "k-2",
        ["p/only.jpg"],
    )


def test_multiple_upload_completions_each_trigger_grading(sqs_queue):
    """Several upload-completions enqueued in turn are each graded once.

    Models a small burst of finished photo sets: every enqueued completion flows
    through SQS into one worker batch and drives the pipeline exactly once, with
    no message lost or duplicated across the S3->SQS->worker path.
    """
    sqs, queue_url = sqs_queue
    producer = SqsQueueClient(queue_url, sqs_client=sqs)

    for n in range(3):
        producer.send_grading_message(
            GradingMessage(
                item_id=f"item-{n}",
                idem_key=f"idem-{n}",
                photo_keys=[f"uploads/item-{n}/p0.jpg"],
            )
        )

    event = _drain_into_lambda_event(sqs, queue_url)
    assert len(event["Records"]) == 3

    pipeline = FakePipeline()
    resp = GradingWorker(pipeline_provider=lambda: pipeline).handle(event)

    assert resp == {"batchItemFailures": []}
    graded_ids = sorted(call.item_id for call in pipeline.calls)
    assert graded_ids == ["item-0", "item-1", "item-2"]
