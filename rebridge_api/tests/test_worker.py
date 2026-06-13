"""Unit tests for the SQS grading worker entrypoint (task 17.6).

Exercises the retry/DLQ contract (Requirements 7.1, 7.4) with a fake
``GradingPipeline`` injected through the worker's ``pipeline_provider`` seam and
an injected recording ``sleep`` so the backoff schedule is observable without
any real time passing:

* a record that succeeds is processed exactly once with no failures reported;
* a transient-failing record is retried up to 2x and then reported as a batch
  item failure (the DLQ path);
* a transient failure that recovers within the retry budget succeeds;
* a mixed batch reports only the failed record ids;
* the injected backoff/jitter drives the sleep schedule (no real sleep);
* a malformed record body routes to the DLQ without retrying;
* the module-level ``lambda_handler`` uses the worker registered via
  ``set_worker``.
"""

from __future__ import annotations

import json

import pytest

from rebridge_api.worker import (
    GradingWorker,
    get_worker,
    lambda_handler,
    set_worker,
)
from rebridge_data.models import GradingMessage


# ---------------------------------------------------------------------------
# test doubles
# ---------------------------------------------------------------------------


class FakePipeline:
    """Records ``run`` calls; fails for configured items.

    ``always_fail`` item ids raise on every attempt (the DLQ path). Items in
    ``transient_fail_counts`` raise that many times and then succeed, modelling
    a transient failure that recovers within the retry budget.
    """

    def __init__(
        self,
        always_fail: set[str] | None = None,
        transient_fail_counts: dict[str, int] | None = None,
    ) -> None:
        self.calls: list[GradingMessage] = []
        self.always_fail = set(always_fail or ())
        self._remaining = dict(transient_fail_counts or {})

    def run(self, message: GradingMessage) -> None:
        self.calls.append(message)
        if message.item_id in self.always_fail:
            raise RuntimeError(f"permanent-style boom for {message.item_id}")
        remaining = self._remaining.get(message.item_id, 0)
        if remaining > 0:
            self._remaining[message.item_id] = remaining - 1
            raise RuntimeError(f"transient failure for {message.item_id}")

    def calls_for(self, item_id: str) -> int:
        return sum(1 for c in self.calls if c.item_id == item_id)


class RecordingSleep:
    """A no-op sleep that records the delays it was asked to sleep for."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _record(message_id: str, item_id: str, *, idem_key="idem", photo_keys=("k1", "k2")):
    body = json.dumps(
        {"item_id": item_id, "idem_key": idem_key, "photo_keys": list(photo_keys)}
    )
    return {"messageId": message_id, "body": body}


def _event(*records):
    return {"Records": list(records)}


def _worker(pipeline, sleep, **kwargs):
    """Build a worker with an identity jitter so delays are deterministic."""

    return GradingWorker(
        pipeline_provider=lambda: pipeline,
        sleep=sleep,
        jitter=lambda d: d,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# success path
# ---------------------------------------------------------------------------


def test_successful_record_processed_once_with_no_failures():
    """Req 7.1: a record that succeeds is run exactly once; nothing redriven."""
    pipeline = FakePipeline()
    sleep = RecordingSleep()
    worker = _worker(pipeline, sleep)

    resp = worker.handle(_event(_record("m1", "item-1")))

    assert resp == {"batchItemFailures": []}
    assert pipeline.calls_for("item-1") == 1
    assert sleep.delays == []  # no retry => no backoff


def test_record_body_parsed_into_grading_message():
    """The SQS body is parsed into a GradingMessage with the right fields."""
    pipeline = FakePipeline()
    worker = _worker(pipeline, RecordingSleep())

    worker.handle(
        _event(_record("m1", "item-1", idem_key="abc", photo_keys=("a", "b", "c")))
    )

    (msg,) = pipeline.calls
    assert msg.item_id == "item-1"
    assert msg.idem_key == "abc"
    assert msg.photo_keys == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# retry-then-DLQ
# ---------------------------------------------------------------------------


def test_transient_failure_retried_twice_then_reported_for_dlq():
    """Req 7.4: retry up to 2x with backoff, then route to the DLQ."""
    pipeline = FakePipeline(always_fail={"item-1"})
    sleep = RecordingSleep()
    worker = _worker(pipeline, sleep, base_delay=0.5, max_retries=2)

    resp = worker.handle(_event(_record("m1", "item-1")))

    # The failing message id is reported so SQS redrives it to the DLQ.
    assert resp == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
    # Initial attempt + 2 retries == 3 total attempts.
    assert pipeline.calls_for("item-1") == 3
    # Backoff slept exactly twice with jittered exponential delays.
    assert sleep.delays == [0.5, 1.0]


def test_transient_failure_recovers_within_retry_budget():
    """A transient failure that clears within 2 retries completes successfully."""
    pipeline = FakePipeline(transient_fail_counts={"item-1": 2})
    sleep = RecordingSleep()
    worker = _worker(pipeline, sleep, base_delay=0.5, max_retries=2)

    resp = worker.handle(_event(_record("m1", "item-1")))

    assert resp == {"batchItemFailures": []}
    assert pipeline.calls_for("item-1") == 3  # fail, fail, succeed
    assert sleep.delays == [0.5, 1.0]


# ---------------------------------------------------------------------------
# partial batch response
# ---------------------------------------------------------------------------


def test_mixed_batch_reports_only_failed_record_ids():
    """Partial batch response: only the failing record id is redriven."""
    pipeline = FakePipeline(always_fail={"bad"})
    sleep = RecordingSleep()
    worker = _worker(pipeline, sleep, max_retries=2)

    resp = worker.handle(
        _event(
            _record("ok-1", "good-1"),
            _record("bad-1", "bad"),
            _record("ok-2", "good-2"),
        )
    )

    assert resp == {"batchItemFailures": [{"itemIdentifier": "bad-1"}]}
    # The successful records ran once each; the failing record exhausted retries.
    assert pipeline.calls_for("good-1") == 1
    assert pipeline.calls_for("good-2") == 1
    assert pipeline.calls_for("bad") == 3


# ---------------------------------------------------------------------------
# injected backoff / jitter
# ---------------------------------------------------------------------------


def test_injected_jitter_shapes_backoff_schedule_without_real_sleep():
    """The sleep/backoff and jitter are injectable so tests never sleep."""
    pipeline = FakePipeline(always_fail={"x"})
    sleep = RecordingSleep()
    worker = GradingWorker(
        pipeline_provider=lambda: pipeline,
        base_delay=1.0,
        max_retries=2,
        sleep=sleep,
        jitter=lambda d: d * 0.1,  # deterministic, observable jitter
    )

    worker.handle(_event(_record("m", "x")))

    # (1.0 * 2**0) * 0.1, (1.0 * 2**1) * 0.1
    assert sleep.delays == [pytest.approx(0.1), pytest.approx(0.2)]


# ---------------------------------------------------------------------------
# permanent / malformed records
# ---------------------------------------------------------------------------


def test_malformed_body_reported_for_dlq_without_retry():
    """A body that does not parse is permanent: report for DLQ, never retried."""
    pipeline = FakePipeline()
    sleep = RecordingSleep()
    worker = _worker(pipeline, sleep)

    resp = worker.handle(_event({"messageId": "m1", "body": "not-json"}))

    assert resp == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
    assert pipeline.calls == []  # never reached the pipeline
    assert sleep.delays == []


def test_permanent_error_fails_fast_to_dlq_when_not_transient():
    """A non-transient error skips retries and routes straight to the DLQ."""
    pipeline = FakePipeline(always_fail={"item-1"})
    sleep = RecordingSleep()
    worker = GradingWorker(
        pipeline_provider=lambda: pipeline,
        sleep=sleep,
        jitter=lambda d: d,
        is_transient=lambda exc: False,  # classify everything as permanent
    )

    resp = worker.handle(_event(_record("m1", "item-1")))

    assert resp == {"batchItemFailures": [{"itemIdentifier": "m1"}]}
    assert pipeline.calls_for("item-1") == 1  # no retries
    assert sleep.delays == []


def test_empty_event_returns_no_failures():
    pipeline = FakePipeline()
    worker = _worker(pipeline, RecordingSleep())
    assert worker.handle({"Records": []}) == {"batchItemFailures": []}
    assert worker.handle({}) == {"batchItemFailures": []}


# ---------------------------------------------------------------------------
# module-level lambda_handler seam
# ---------------------------------------------------------------------------


def test_lambda_handler_uses_registered_worker():
    """lambda_handler delegates to the worker registered via set_worker."""
    pipeline = FakePipeline()
    worker = GradingWorker(pipeline_provider=lambda: pipeline, sleep=lambda d: None)
    set_worker(worker)
    try:
        resp = lambda_handler(_event(_record("m1", "item-1")))
        assert resp == {"batchItemFailures": []}
        assert pipeline.calls_for("item-1") == 1
    finally:
        set_worker(None)


def test_get_worker_raises_when_unregistered():
    set_worker(None)
    with pytest.raises(RuntimeError):
        get_worker()
