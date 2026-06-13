"""Property-based test for the worker retry-then-DLQ bound.

# Feature: rebridge-backend, Property 12: Retry-then-DLQ bound

Property 12 (design.md): *For any* sequence of transient worker failures, the
Grading_Pipeline SHALL retry at most 2 times with jittered backoff and SHALL
route the message to the dead-letter queue only on the failure following the
final retry.

**Validates: Requirements 7.4**

The test drives the real :class:`~rebridge_api.worker.GradingWorker` over
arbitrary SQS batches built from arbitrary *failure profiles* (no AWS, no
mocks). Each record is assigned one of:

* ``always`` -- the pipeline raises a transient error on every attempt, so the
  record must exhaust the retry budget and end up in ``batchItemFailures`` (the
  DLQ path);
* ``recovers`` after ``j`` transient failures where ``0 <= j <= max_retries`` --
  the record fails ``j`` times then succeeds, so it must NOT appear in
  ``batchItemFailures``.

``max_retries`` is itself varied. For every generated batch the test asserts:

* an always-failing record invokes the pipeline exactly ``1 + max_retries``
  times and its message id is reported for the DLQ;
* a record that recovers after ``j`` failures invokes the pipeline exactly
  ``j + 1`` times (= ``min(k, 1 + max_retries)`` with ``k = j + 1``) and is NOT
  reported for the DLQ;
* the number of backoff sleeps equals the total number of retries actually
  performed across the whole batch;
* the reported failures are exactly the set of always-failing record ids -- a
  true partial batch response (only failed ids are returned).

``sleep`` and ``jitter`` are injected so no real time ever passes; an identity
jitter makes the per-retry delay deterministic and observable.
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_api.worker import GradingWorker
from rebridge_data.models import GradingMessage

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200


class _RecordingSleep:
    """A no-op sleep that records the delays it was asked to sleep for."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class _ProfilePipeline:
    """Drives configured per-item failure profiles.

    ``fail_counts`` maps an item id to the number of consecutive transient
    failures it should raise before succeeding. ``float("inf")`` models an
    always-failing record (the DLQ path); a finite ``j`` models recovery after
    ``j`` failures.
    """

    def __init__(self, fail_counts: dict[str, float]) -> None:
        self._remaining = dict(fail_counts)
        self.calls: list[GradingMessage] = []

    def run(self, message: GradingMessage) -> None:
        self.calls.append(message)
        remaining = self._remaining.get(message.item_id, 0)
        if remaining > 0:
            if remaining != float("inf"):
                self._remaining[message.item_id] = remaining - 1
            raise RuntimeError(f"transient failure for {message.item_id}")

    def calls_for(self, item_id: str) -> int:
        return sum(1 for c in self.calls if c.item_id == item_id)


def _record(message_id: str, item_id: str):
    body = json.dumps(
        {"item_id": item_id, "idem_key": "idem", "photo_keys": ["k1", "k2"]}
    )
    return {"messageId": message_id, "body": body}


# A single batch: a list of (always_fail?, recover_after_j) per record. We build
# distinct message/item ids from the index so ids never collide within a batch.
_failure_profile = st.lists(
    st.fixed_dictionaries(
        {
            "always": st.booleans(),
            # recovery point in 0..3; clamped to <= max_retries below.
            "recover_after": st.integers(min_value=0, max_value=3),
        }
    ),
    min_size=0,
    max_size=8,
)


@settings(max_examples=_ITERATIONS)
@given(profiles=_failure_profile, max_retries=st.integers(min_value=0, max_value=3))
def test_retry_then_dlq_bound(profiles, max_retries: int) -> None:
    """Transient failures retry at most ``max_retries`` times before the DLQ.

    Validates Requirement 7.4 / Property 12.
    """

    fail_counts: dict[str, float] = {}
    records = []
    always_ids: set[str] = set()
    # Expected pipeline attempts per item id.
    expected_calls: dict[str, int] = {}
    # Total retries performed across the batch (== expected backoff sleeps).
    expected_sleeps = 0

    for i, profile in enumerate(profiles):
        message_id = f"m{i}"
        item_id = f"item-{i}"
        records.append(_record(message_id, item_id))

        if profile["always"]:
            fail_counts[item_id] = float("inf")
            always_ids.add(message_id)
            # initial attempt + max_retries retries
            expected_calls[item_id] = 1 + max_retries
            expected_sleeps += max_retries
        else:
            # recover after j transient failures, j clamped into the budget.
            j = min(profile["recover_after"], max_retries)
            fail_counts[item_id] = j
            expected_calls[item_id] = j + 1  # = min(j+1, 1+max_retries)
            expected_sleeps += j

    pipeline = _ProfilePipeline(fail_counts)
    sleep = _RecordingSleep()
    worker = GradingWorker(
        pipeline_provider=lambda: pipeline,
        max_retries=max_retries,
        base_delay=0.5,
        sleep=sleep,
        jitter=lambda d: d,  # identity jitter -> deterministic delays
    )

    resp = worker.handle({"Records": records})

    # -- only failed (always-failing) record ids are returned: partial batch --
    reported = {f["itemIdentifier"] for f in resp["batchItemFailures"]}
    assert reported == always_ids
    # No duplicates in the response.
    assert len(resp["batchItemFailures"]) == len(always_ids)

    # -- each record was attempted exactly min(k, 1+max_retries) times --------
    for item_id, expected in expected_calls.items():
        assert pipeline.calls_for(item_id) == expected

    # -- number of backoff sleeps equals retries actually performed -----------
    assert len(sleep.delays) == expected_sleeps

    # -- the jittered exponential backoff schedule is honored -----------------
    # Each retry sleeps base_delay * 2**attempt (identity jitter). We rebuild the
    # expected multiset of delays from the per-item retry counts.
    expected_delays: list[float] = []
    for item_id, expected in expected_calls.items():
        retries = expected - 1  # attempts beyond the first are retries
        for attempt in range(retries):
            expected_delays.append(0.5 * (2 ** attempt))
    assert sorted(sleep.delays) == sorted(expected_delays)
