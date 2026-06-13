"""Grading-latency p99 measurement test (task 18.3, Requirement 9.1).

Requirement 9.1 states: *WHEN a photo set that passed the Quality_Precheck is
graded, THE Grading_Pipeline SHALL produce a persisted grade within 4 seconds
at the 99th percentile of grading submissions.*

This is an **orchestration latency smoke test**, not a property test (see the
tasks.md note: data/infrastructure concerns such as p99 latency are validated
with integration/smoke tests rather than Hypothesis properties). It drives the
real :class:`GradingPipeline.run` end to end over the in-memory fakes with a
passing photo set and conforming model JSON, records per-run wall-clock
latency for a modest sample of ``N`` submissions, computes the 99th percentile,
and asserts it stays under the 4-second budget.

### What this guards (and what it does not)

The :class:`FakeGradingProvider` returns its scripted JSON immediately, so the
*model inference* latency is mocked out -- in deployment that cost dominates and
is exercised against the real provider cascade. What this test guards is the
**pure pipeline / orchestration path**: idempotency lookup, image fetch,
quality precheck (variance-of-Laplacian + brightness over every pixel),
catalog assembly, strict-JSON parse, confidence gate, grade persistence, card
render + HMAC sign + persist, event emit, and routing. A regression that made
any of these steps pathologically slow (e.g. accidental quadratic work in the
precheck or card rendering) would blow the budget here even though the model is
mocked. The real end-to-end p99 (including model latency) is measured in the
deployed environment.
"""

from __future__ import annotations

import time
from decimal import Decimal

from rebridge_data.models import (
    GradingMessage,
    ItemMeta,
    ItemStatus,
)

from rebridge_service.confidence_gate import ConfidenceGate
from rebridge_service.eventing_service import EventingService
from rebridge_service.grade_schema import serialize_grade_assessment
from rebridge_service.grading_engine import GradingEngine
from rebridge_service.grading_pipeline import GradingPipeline, PipelineOutcome
from rebridge_service.health_card_service import HealthCardService
from rebridge_service.models import (
    CompletenessResult,
    Defect,
    Grade,
    GradeAssessment,
)
from rebridge_service.quality_precheck import QualityPrecheck

from tests.fakes import (
    FakeCardSigner,
    FakeEventPublisher,
    FakeGradingProvider,
    FakeItemRepository,
    FakeObjectStore,
    FakeReviewQueueRepository,
)

# ---------------------------------------------------------------------------
# Test parameters
# ---------------------------------------------------------------------------

# Modest sample so the suite stays fast while still giving a meaningful p99.
SAMPLE_SIZE = 150
# Requirement 9.1: 4-second budget at the 99th percentile.
P99_BUDGET_SECONDS = 4.0

ITEM_ID = "item-latency"
PHOTO_KEYS = ["items/item-latency/photo-0", "items/item-latency/photo-1"]
EST_VALUE = Decimal("100")

# Sharp, well-lit checkerboard: passes the blur + lighting precheck.
SHARP_PIXELS = [[255 if (r + c) % 2 == 0 else 0 for c in range(5)] for r in range(5)]


def _decoder(_raw: bytes):
    return SHARP_PIXELS


def _valid_json() -> str:
    assessment = GradeAssessment(
        grade=Grade.GOOD,
        defects=[Defect(location="corner", severity="minor")],
        completeness=CompletenessResult(is_complete=True, missing_components=[]),
        confidence=0.95,
        summary="Looks good overall.",
    )
    return serialize_grade_assessment(assessment)


def _build_pipeline() -> GradingPipeline:
    """Construct a fresh pipeline + fakes wired for the happy (GRADED) path.

    A fresh instance per run keeps every submission a *first* grade (the
    idempotency check would otherwise short-circuit a repeat), so each timed
    run exercises the full precheck -> grade -> gate -> persist -> card -> event
    -> route path.
    """
    item_repo = FakeItemRepository()
    item_repo.put_item_meta(
        ItemMeta(
            item_id=ITEM_ID,
            status=ItemStatus.CREATED,
            category="electronics",
            age_months=10,
            context_source="manual",
            created_at="2024-01-01T00:00:00+00:00",
        )
    )
    store = FakeObjectStore()
    for key in PHOTO_KEYS:
        store.put_object(key, b"good")
    engine = GradingEngine(
        [FakeGradingProvider("nova", script=[_valid_json()])],
        timeout=None,
        max_json_retries=2,
    )
    return GradingPipeline(
        item_repo=item_repo,
        object_store=store,
        review_repo=FakeReviewQueueRepository(),
        precheck=QualityPrecheck(),
        grading_engine=engine,
        confidence_gate=ConfidenceGate(threshold=0.80),
        card_service=HealthCardService(FakeCardSigner(), item_repo),
        eventing=EventingService(FakeEventPublisher()),
        router=None,
        pixel_decoder=_decoder,
        value_estimator=lambda meta, assessment: EST_VALUE,
        catalog_provider=None,
    )


def _percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile of ``samples`` (0 < pct <= 100)."""
    ordered = sorted(samples)
    # Nearest-rank: rank = ceil(pct/100 * N), 1-indexed.
    import math

    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[rank - 1]


def test_grading_pipeline_p99_latency_within_budget():
    """p99 of end-to-end persisted-grade latency stays under 4s (Req 9.1)."""
    message = GradingMessage(
        item_id=ITEM_ID, idem_key="", photo_keys=list(PHOTO_KEYS)
    )

    latencies: list[float] = []
    for _ in range(SAMPLE_SIZE):
        # Build outside the timed region so only the pipeline path is measured.
        pipeline = _build_pipeline()
        start = time.perf_counter()
        result = pipeline.run(message)
        elapsed = time.perf_counter() - start

        # Every sampled run must actually traverse the full grade-and-persist
        # path; a skipped/retake/review run would not be a valid latency sample.
        assert result.outcome is PipelineOutcome.GRADED
        assert result.grade is not None and result.grade.confirmed is True
        latencies.append(elapsed)

    p99 = _percentile(latencies, 99.0)
    print(
        f"\ngrading p99 latency over {SAMPLE_SIZE} runs: {p99 * 1000:.2f} ms "
        f"(budget {P99_BUDGET_SECONDS}s)"
    )

    assert p99 < P99_BUDGET_SECONDS, (
        f"grading p99 latency {p99:.4f}s exceeded the {P99_BUDGET_SECONDS}s "
        f"budget over {SAMPLE_SIZE} runs (Requirement 9.1)"
    )
