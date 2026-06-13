"""Property-based test for the confidence-gate decision boundary.

# Feature: rebridge-backend, Property 9: Confidence gate decision boundary

Property 9 (design.md): *For any* grade assessment, when its confidence is
greater than or equal to the configured threshold the Grading_Pipeline SHALL
persist the grade and continue to event emission, and when its confidence is
below the threshold the Grading_Pipeline SHALL set status PENDING_REVIEW and add
an entry to the Review_Queue.

**Validates: Requirements 6.1, 6.2**

The strategy varies the model's reported confidence across the whole [0, 1]
interval, the configured Confidence_Threshold across [0, 1], the assessed grade,
and the estimated value. For each draw the pipeline is run once against the
in-memory fakes (no AWS calls) with a programmed :class:`FakeGradingProvider`
that returns a single schema-conforming response carrying the chosen
confidence. The test then asserts the two-sided boundary:

* ``confidence >= threshold`` -> outcome GRADED, status GRADED, the persisted
  grade is *confirmed*, and **no** review entry is enqueued (Requirement 6.1);
* ``confidence <  threshold`` -> outcome PENDING_REVIEW, status PENDING_REVIEW,
  the persisted grade is *unconfirmed*, and **exactly one** review entry is
  enqueued (Requirement 6.2).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from rebridge_data.models import GradingMessage, ItemMeta, ItemStatus

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

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

_ITEM_ID = "item-prop-9"
_PHOTO_KEYS = ["items/item-prop-9/photo-0", "items/item-prop-9/photo-1"]

# A high-contrast checkerboard: high variance-of-Laplacian (sharp) and a mean
# brightness near 127 -> always passes the quality precheck so every run
# reaches the confidence gate.
_SHARP_PIXELS = [[255 if (r + c) % 2 == 0 else 0 for c in range(5)] for r in range(5)]


def _decoder(_raw: bytes):
    return _SHARP_PIXELS


class _FakeRouter:
    """Records route() calls; returns a decision with a disposition."""

    def __init__(self) -> None:
        self.routed: list[str] = []

    def route(self, item_id: str):
        self.routed.append(item_id)
        return type("Decision", (), {"disposition": "RESELL"})()


def _valid_json(grade: Grade, confidence: float) -> str:
    assessment = GradeAssessment(
        grade=grade,
        defects=[Defect(location="corner", severity="minor")],
        completeness=CompletenessResult(is_complete=True, missing_components=[]),
        confidence=confidence,
        summary="Property-9 boundary check.",
    )
    return serialize_grade_assessment(assessment)


def _build(*, grade: Grade, confidence: float, threshold: float, est_value: Decimal):
    """Construct a pipeline over fresh in-memory fakes for one run."""

    item_repo = FakeItemRepository()
    item_repo.put_item_meta(
        ItemMeta(
            item_id=_ITEM_ID,
            status=ItemStatus.CREATED,
            category="electronics",
            age_months=10,
            context_source="manual",
            created_at="2024-01-01T00:00:00+00:00",
        )
    )
    store = FakeObjectStore()
    for key in _PHOTO_KEYS:
        store.put_object(key, b"good")
    review_repo = FakeReviewQueueRepository()
    publisher = FakeEventPublisher()
    router = _FakeRouter()
    engine = GradingEngine(
        [FakeGradingProvider("nova", script=[_valid_json(grade, confidence)])],
        timeout=None,
        max_json_retries=2,
    )
    pipeline = GradingPipeline(
        item_repo=item_repo,
        object_store=store,
        review_repo=review_repo,
        precheck=QualityPrecheck(),
        grading_engine=engine,
        confidence_gate=ConfidenceGate(threshold=threshold),
        card_service=HealthCardService(FakeCardSigner(), item_repo),
        eventing=EventingService(publisher),
        router=router,
        pixel_decoder=_decoder,
        value_estimator=lambda meta, assessment: est_value,
        catalog_provider=None,
    )
    return pipeline, item_repo, review_repo, publisher, router


def _message() -> GradingMessage:
    return GradingMessage(item_id=_ITEM_ID, idem_key="idem-prop-9", photo_keys=list(_PHOTO_KEYS))


# Confidence and threshold span the full [0, 1] interval. width=32 keeps the
# JSON serialize/parse round-trip exact so the gate sees the generated value.
_unit = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False, width=32)
_grade = st.sampled_from(list(Grade))
_value = st.decimals(min_value=Decimal("1"), max_value=Decimal("5000"), places=2)


@settings(max_examples=_ITERATIONS)
@given(grade=_grade, confidence=_unit, threshold=_unit, est_value=_value)
# Exercise the exact boundary (confidence == threshold) explicitly: it must
# auto-continue per Requirement 6.1's ">=".
@example(grade=Grade.GOOD, confidence=0.80, threshold=0.80, est_value=Decimal("100.00"))
@example(grade=Grade.GOOD, confidence=0.0, threshold=0.0, est_value=Decimal("100.00"))
@example(grade=Grade.GOOD, confidence=1.0, threshold=1.0, est_value=Decimal("100.00"))
def test_confidence_gate_decision_boundary(
    grade: Grade, confidence: float, threshold: float, est_value: Decimal
) -> None:
    pipeline, item_repo, review_repo, publisher, router = _build(
        grade=grade, confidence=confidence, threshold=threshold, est_value=est_value
    )

    result = pipeline.run(_message())

    pending = review_repo.list_pending(10)
    grade_record = item_repo.get_grade(_ITEM_ID)
    status = item_repo.get_item(_ITEM_ID).meta.status

    if confidence >= threshold:
        # Requirement 6.1: persist + continue to event emission automatically.
        assert result.outcome is PipelineOutcome.GRADED
        assert status is ItemStatus.GRADED
        assert grade_record is not None and grade_record.confirmed is True
        assert grade_record.grade == grade.value
        # Auto-continued: GRADED event emitted, item routed, nothing in review.
        assert [e.event_type for e in publisher.events] == ["GRADED"]
        assert router.routed == [_ITEM_ID]
        assert pending == []
    else:
        # Requirement 6.2: PENDING_REVIEW + a single review-queue entry.
        assert result.outcome is PipelineOutcome.PENDING_REVIEW
        assert status is ItemStatus.PENDING_REVIEW
        assert grade_record is not None and grade_record.confirmed is False
        assert grade_record.grade == grade.value
        assert len(pending) == 1
        assert pending[0].item_id == _ITEM_ID
        # Priority is value * uncertainty; no auto-continue side effects.
        assert pending[0].priority == pytest.approx(float(est_value) * (1.0 - confidence))
        assert publisher.events == []
        assert router.routed == []
