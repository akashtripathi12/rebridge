"""SQS grading worker entrypoint with retry/DLQ handling (task 17.6).

This is the Lambda handler that backs the asynchronous grading path
(design.md -> "Dual Entry Adapters"). API Gateway/FastAPI enqueues a grading
submission; SQS triggers this worker; the worker parses each SQS record into a
:class:`~rebridge_data.models.GradingMessage` and drives the **same**
:class:`~rebridge_service.grading_pipeline.GradingPipeline` the synchronous path
uses. Flipping sync->async requires no business-logic change because both
adapters call the identical pipeline interface (Requirement 7.1).

### Retry-then-DLQ contract (Requirements 7.4, 7.5)

Grading is idempotent (the pipeline persists with ``put_grade_if_absent``), so a
re-run is safe. On a *transient* failure the worker retries the pipeline **up to
2 times** with **jittered exponential backoff** before giving up on that record.
A record that still fails after the final retry is reported as a *batch item
failure*: SQS keeps the message visible and, once it exceeds the queue's
``maxReceiveCount``, routes it to the dead-letter queue (which in turn raises the
operational alarm, Requirement 7.5). The worker never talks to the DLQ
directly -- it simply declines to delete the message by returning it in
``batchItemFailures``.

### Partial batch responses

The worker returns the AWS SQS partial-batch-response shape
``{"batchItemFailures": [{"itemIdentifier": <messageId>}, ...]}`` so that only
the records that failed are redriven; successfully-processed records in the same
batch are deleted by SQS and never reprocessed. (The Lambda event source mapping
must have ``ReportBatchItemFailures`` enabled for this to take effect.)

### Injection seams (no boto3 here)

This module imports **no** boto3 and constructs **no** AWS client. Mirroring the
:mod:`rebridge_api.dependencies` ``set_services``/``get_services`` seam:

* :class:`GradingWorker` takes a ``pipeline_provider`` -- a zero-arg callable
  returning anything with ``run(message)`` (the real ``GradingPipeline`` in
  production; a fake in tests). The provider is invoked once per Lambda
  invocation so the composition root can build the boto3-backed pipeline lazily.
* ``sleep`` and ``jitter`` are injectable so tests exercise the backoff schedule
  without ever sleeping for real.
* ``is_transient`` classifies an exception as transient (retryable) or permanent
  (fail fast straight to the DLQ); it defaults to treating every exception as
  transient, which is safe given the pipeline's idempotency.

The composition root (task 17.8) builds a :class:`GradingWorker` and registers
it with :func:`set_worker`; the module-level :func:`lambda_handler` resolves it
via :func:`get_worker`, keeping all concrete wiring out of this file.
"""

from __future__ import annotations

import json
import random
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from rebridge_data.models import GradingMessage

__all__ = [
    "GradingRunner",
    "PipelineProvider",
    "GradingWorker",
    "set_worker",
    "get_worker",
    "lambda_handler",
]


@runtime_checkable
class GradingRunner(Protocol):
    """Structural type of the object the worker drives per record.

    The real :class:`~rebridge_service.grading_pipeline.GradingPipeline`
    satisfies this; tests inject a fake exposing the same ``run`` method.
    """

    def run(self, message: GradingMessage) -> Any: ...


# A zero-arg factory yielding the grading runner for an invocation. Invoked once
# per Lambda invocation so the composition root can build (and reuse) the
# boto3-backed pipeline lazily without this module importing boto3.
PipelineProvider = Callable[[], GradingRunner]


def _full_jitter(delay: float) -> float:
    """Default jitter: a uniform sample in ``[0, delay]`` ("full jitter").

    Spreading retries across the whole interval avoids synchronized retry
    storms. Tests inject a deterministic replacement so the schedule is
    observable.
    """

    return random.uniform(0.0, delay)


@dataclass
class GradingWorker:
    """Drives :class:`GradingRunner` over an SQS batch with retry/DLQ semantics.

    Parameters
    ----------
    pipeline_provider:
        Zero-arg callable returning the grading runner. Called once per
        :meth:`handle` invocation.
    max_retries:
        Maximum number of *retries* after the initial attempt for a transient
        failure (so a record is attempted at most ``1 + max_retries`` times).
        Defaults to 2 per Requirement 7.4.
    base_delay:
        Base backoff delay in seconds; the pre-jitter delay before retry
        ``attempt`` (0-indexed) is ``base_delay * 2 ** attempt``.
    sleep:
        Injectable sleep function (defaults to :func:`time.sleep`); tests pass a
        recording no-op so no real time passes.
    jitter:
        Injectable function mapping a computed delay to the actual delay slept;
        defaults to full jitter.
    is_transient:
        Predicate deciding whether an exception is transient (retryable). A
        permanent error skips retries and is reported for the DLQ immediately.
        Defaults to treating every exception as transient (safe because grading
        is idempotent).
    """

    pipeline_provider: PipelineProvider
    max_retries: int = 2
    base_delay: float = 0.1
    sleep: Callable[[float], None] = time.sleep
    jitter: Callable[[float], float] = _full_jitter
    is_transient: Callable[[BaseException], bool] = field(
        default=lambda exc: True
    )

    # -- public entrypoint -------------------------------------------------
    def handle(self, event: dict[str, Any], context: Any = None) -> dict[str, Any]:
        """Process one SQS batch and return a partial-batch-failure response.

        Iterates ``event["Records"]``; each record is parsed and run through the
        pipeline with retry. Records that ultimately fail (or that carry a
        malformed body) are reported in ``batchItemFailures`` by their
        ``messageId`` so SQS redrives only those to the DLQ.
        """

        records = event.get("Records") or []
        if not records:
            return {"batchItemFailures": []}

        # Build the runner once per invocation (the provider may construct
        # boto3-backed collaborators); reuse it across the batch and retries.
        pipeline = self.pipeline_provider()

        failures: list[dict[str, str]] = []
        for record in records:
            if not self._process_record(pipeline, record):
                message_id = record.get("messageId")
                if message_id is not None:
                    failures.append({"itemIdentifier": message_id})
        return {"batchItemFailures": failures}

    # -- per-record processing --------------------------------------------
    def _process_record(self, pipeline: GradingRunner, record: dict[str, Any]) -> bool:
        """Parse and run a single record. Return ``True`` on success.

        A ``False`` return means the record should route to the DLQ (either a
        malformed body, which is permanent, or a failure that survived all
        retries).
        """

        try:
            message = self._parse_record(record)
        except Exception:
            # A body that does not parse into a GradingMessage is a permanent
            # error -- retrying cannot fix it, so send it straight to the DLQ.
            return False
        return self._run_with_retry(pipeline, message)

    def _run_with_retry(self, pipeline: GradingRunner, message: GradingMessage) -> bool:
        """Run the pipeline, retrying transient failures with jittered backoff.

        Returns ``True`` once the pipeline completes, or ``False`` after the
        failure following the final retry (or immediately for a permanent
        error). Sleeps ``jitter(base_delay * 2 ** attempt)`` before each retry.
        """

        attempt = 0
        while True:
            try:
                print(f"[Worker] Starting pipeline.run for attempt {attempt}")
                pipeline.run(message)
                print(f"[Worker] Finished pipeline.run for attempt {attempt}")
                return True
            except Exception as exc:  # noqa: BLE001 - classified by is_transient
                print(f"[Worker] Pipeline error on attempt {attempt}: {exc}")
                traceback.print_exc()
                exhausted = attempt >= self.max_retries
                if not self.is_transient(exc) or exhausted:
                    # Permanent error, or transient but out of retries -> DLQ.
                    return False
                delay = self.jitter(self.base_delay * (2 ** attempt))
                self.sleep(delay)
                attempt += 1

    @staticmethod
    def _parse_record(record: dict[str, Any]) -> GradingMessage:
        """Parse one SQS record body into a :class:`GradingMessage`.

        The body is a JSON object with ``item_id``, ``idem_key``, and
        ``photo_keys``. ``item_id`` is required; ``idem_key`` defaults to empty
        (the pipeline derives it from the item id + photo-set hash when blank)
        and ``photo_keys`` defaults to an empty list.
        """

        data = json.loads(record["body"])
        return GradingMessage(
            item_id=data["item_id"],
            idem_key=data.get("idem_key", "") or "",
            photo_keys=list(data.get("photo_keys", [])),
        )


# ---------------------------------------------------------------------------
# Module-level handler seam (mirrors set_services/get_services)
# ---------------------------------------------------------------------------

import threading

_WORKER: GradingWorker | None = None
_WORKER_LOCK = threading.Lock()


def set_worker(worker: GradingWorker | None) -> None:
    """Register the :class:`GradingWorker` the Lambda entrypoint will use.

    The composition root (task 17.8) builds a worker wired to the boto3-backed
    pipeline and calls this; tests call it with a fake-backed worker (and reset
    it to ``None`` afterward).
    """

    global _WORKER
    with _WORKER_LOCK:
        _WORKER = worker


def get_worker() -> GradingWorker:
    """Return the registered worker, or raise if the wiring step was skipped."""

    with _WORKER_LOCK:
        if _WORKER is None:
            raise RuntimeError(
                "no GradingWorker registered; the composition root (or a test) must "
                "call set_worker(worker) before the Lambda entrypoint is invoked"
            )
        return _WORKER


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entrypoint for SQS-triggered grading.

    Resolves the configured :class:`GradingWorker` and delegates to
    :meth:`GradingWorker.handle`, returning the partial-batch-failure response.
    """

    return get_worker().handle(event, context)
