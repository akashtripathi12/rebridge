"""Unit tests for the GradingPipeline run-flow orchestration (task 9.1).

These exercise the pipeline against the in-memory fakes and the programmable
:class:`FakeGradingProvider`, covering every branch of the flow:

* idempotent skip when a grade for the key is already present (Req 7.3);
* quality-precheck failure -> RETAKE_REQUIRED (Req 4.2);
* confidence >= threshold -> persist GRADE, card, GRADED event, router invoke
  (Req 6.1);
* confidence < threshold -> PENDING_REVIEW + enqueue with priority
  ``est_value * (1 - confidence)`` (Req 6.2);
* non-conforming JSON after retries -> review state (Req 5.7);
* total cascade failure -> PENDING_REVIEW (Req 8.3);
* concurrent idempotent loss on persist -> skip;
* end-to-end idempotency across two runs;
* unknown item -> ItemNotFound.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from rebridge_data.models import (
    GradeRecord,
    GradingMessage,
    ItemMeta,
    ItemStatus,
)

from rebridge_service.confidence_gate import ConfidenceGate
from rebridge_service.eventing_service import EventingService
from rebridge_service.grade_schema import serialize_grade_assessment
from rebridge_service.grading_engine import GradingEngine
from rebridge_service.grading_pipeline import (
    CallableRouter,
    GradingPipeline,
    ItemNotFound,
    PipelineOutcome,
)
from rebridge_service.health_card_service import HealthCardService
from rebridge_service.idempotency import derive_idempotency_key
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
# Fixtures / helpers
# ---------------------------------------------------------------------------

ITEM_ID = "item-123"
PHOTO_KEYS = ["items/item-123/photo-0", "items/item-123/photo-1"]
EST_VALUE = Decimal("100")

# A high-contrast checkerboard: high variance-of-Laplacian (sharp) and a mean
# brightness around 127 -> passes both precheck checks.
SHARP_PIXELS = [[255 if (r + c) % 2 == 0 else 0 for c in range(5)] for r in range(5)]
# A flat, dark frame: zero Laplacian variance (blurry) and brightness 10
# (underexposed) -> fails the precheck.
BLURRY_PIXELS = [[10 for _ in range(5)] for _ in range(5)]


def _decoder(raw: bytes):
    """Map seeded object bytes to a grayscale matrix for the precheck."""
    return BLURRY_PIXELS if raw == b"bad" else SHARP_PIXELS


def _assessment(grade: Grade = Grade.GOOD, confidence: float = 0.9) -> GradeAssessment:
    return GradeAssessment(
        grade=grade,
        defects=[Defect(location="corner", severity="minor")],
        completeness=CompletenessResult(is_complete=True, missing_components=[]),
        confidence=confidence,
        summary="Looks good overall.",
    )


def _valid_json(grade: Grade = Grade.GOOD, confidence: float = 0.9) -> str:
    return serialize_grade_assessment(_assessment(grade, confidence))


class FakeRouter:
    """Records route() invocations and returns a decision with a disposition."""

    def __init__(self) -> None:
        self.routed: list[str] = []

    def route(self, item_id: str):
        self.routed.append(item_id)
        return type("Decision", (), {"disposition": "RESELL"})()


def _build(
    *,
    provider_script,
    photo_bytes=b"good",
    threshold: float = 0.80,
    router=None,
    seed_meta: bool = True,
    max_json_retries: int = 2,
):
    item_repo = FakeItemRepository()
    if seed_meta:
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
        store.put_object(key, photo_bytes)
    review_repo = FakeReviewQueueRepository()
    publisher = FakeEventPublisher()
    engine = GradingEngine(
        [FakeGradingProvider("nova", script=provider_script)],
        timeout=None,
        max_json_retries=max_json_retries,
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
        value_estimator=lambda meta, assessment: EST_VALUE,
        catalog_provider=None,
    )
    return pipeline, item_repo, store, review_repo, publisher


def _message(idem_key: str = "idem-key-1") -> GradingMessage:
    return GradingMessage(item_id=ITEM_ID, idem_key=idem_key, photo_keys=list(PHOTO_KEYS))


# ---------------------------------------------------------------------------
# Branch: confidence >= threshold -> GRADED
# ---------------------------------------------------------------------------


def test_high_confidence_grades_cards_emits_and_routes():
    router = FakeRouter()
    pipeline, item_repo, _store, review_repo, publisher = _build(
        provider_script=[_valid_json(Grade.LIKE_NEW, 0.95)], router=router
    )

    result = pipeline.run(_message())

    assert result.outcome is PipelineOutcome.GRADED
    # Grade persisted and confirmed.
    grade = item_repo.get_grade(ITEM_ID)
    assert grade is not None and grade.confirmed is True
    assert grade.grade == Grade.LIKE_NEW.value
    assert grade.idem_key == "idem-key-1"
    # Status advanced to GRADED.
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.GRADED
    # Card rendered, signed, persisted.
    assert result.card is not None
    assert item_repo.get_item(ITEM_ID).card is not None
    # GRADED lifecycle event emitted.
    assert [e.event_type for e in publisher.events] == ["GRADED"]
    # Router invoked exactly once; no review entry.
    assert router.routed == [ITEM_ID]
    assert review_repo.list_pending(10) == []


def test_confidence_exactly_at_threshold_auto_continues():
    pipeline, item_repo, *_ = _build(
        provider_script=[_valid_json(Grade.GOOD, 0.80)], threshold=0.80
    )
    result = pipeline.run(_message())
    assert result.outcome is PipelineOutcome.GRADED
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.GRADED


def test_graded_without_router_skips_routing_cleanly():
    pipeline, item_repo, *_rest = _build(
        provider_script=[_valid_json(Grade.GOOD, 0.9)], router=None
    )
    result = pipeline.run(_message())
    assert result.outcome is PipelineOutcome.GRADED
    assert result.decision is None
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.GRADED


# ---------------------------------------------------------------------------
# Branch: confidence < threshold -> PENDING_REVIEW
# ---------------------------------------------------------------------------


def test_low_confidence_routes_to_review_with_priority():
    router = FakeRouter()
    pipeline, item_repo, _store, review_repo, publisher = _build(
        provider_script=[_valid_json(Grade.ACCEPTABLE, 0.50)], router=router
    )

    result = pipeline.run(_message())

    assert result.outcome is PipelineOutcome.PENDING_REVIEW
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.PENDING_REVIEW
    # Grade persisted but NOT confirmed.
    grade = item_repo.get_grade(ITEM_ID)
    assert grade is not None and grade.confirmed is False
    # Review entry enqueued with priority est_value * (1 - confidence).
    pending = review_repo.list_pending(10)
    assert len(pending) == 1
    assert pending[0].item_id == ITEM_ID
    assert pending[0].priority == pytest.approx(float(EST_VALUE) * (1.0 - 0.50))
    # No GRADED event and no routing for an unconfirmed grade.
    assert publisher.events == []
    assert router.routed == []


# ---------------------------------------------------------------------------
# Branch: quality precheck failure -> RETAKE_REQUIRED
# ---------------------------------------------------------------------------


def test_precheck_failure_sets_retake_required_and_skips_model():
    nova_script = [_valid_json(Grade.GOOD, 0.99)]
    pipeline, item_repo, _store, review_repo, publisher = _build(
        provider_script=nova_script, photo_bytes=b"bad"
    )

    result = pipeline.run(_message())

    assert result.outcome is PipelineOutcome.RETAKE_REQUIRED
    assert result.retake_prompt is not None
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.RETAKE_REQUIRED
    # Model never produced a grade; nothing persisted/enqueued/emitted.
    assert item_repo.get_grade(ITEM_ID) is None
    assert review_repo.list_pending(10) == []
    assert publisher.events == []


# ---------------------------------------------------------------------------
# Branch: non-conforming JSON / total cascade failure -> PENDING_REVIEW
# ---------------------------------------------------------------------------


def test_non_conforming_json_after_retries_routes_to_review():
    # Provider always returns junk; engine retries then raises cascade failure.
    pipeline, item_repo, _store, review_repo, publisher = _build(
        provider_script=["not json at all"], max_json_retries=2
    )

    result = pipeline.run(_message())

    assert result.outcome is PipelineOutcome.PENDING_REVIEW
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.PENDING_REVIEW
    # No grade persisted (nothing conformed).
    assert item_repo.get_grade(ITEM_ID) is None
    # Enqueued for review with confidence 0 -> priority == est_value.
    pending = review_repo.list_pending(10)
    assert len(pending) == 1
    assert pending[0].priority == pytest.approx(float(EST_VALUE))
    assert publisher.events == []


def test_total_cascade_failure_routes_to_review():
    pipeline, item_repo, _store, review_repo, _publisher = _build(
        provider_script=[TimeoutError("nova timed out")]
    )

    result = pipeline.run(_message())

    assert result.outcome is PipelineOutcome.PENDING_REVIEW
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.PENDING_REVIEW
    assert item_repo.get_grade(ITEM_ID) is None
    assert len(review_repo.list_pending(10)) == 1


# ---------------------------------------------------------------------------
# Idempotency (Req 7.3)
# ---------------------------------------------------------------------------


def test_skips_when_grade_already_present_for_key():
    pipeline, item_repo, _store, _review, publisher = _build(
        provider_script=[_valid_json(Grade.GOOD, 0.99)]
    )
    # Pre-persist a grade carrying the same idempotency key.
    item_repo.put_grade(
        ITEM_ID,
        GradeRecord(
            grade=Grade.VERY_GOOD.value,
            confidence=0.91,
            summary="already graded",
            idem_key="idem-key-1",
            confirmed=True,
        ),
    )

    result = pipeline.run(_message("idem-key-1"))

    assert result.outcome is PipelineOutcome.SKIPPED_IDEMPOTENT
    # Existing grade retained unchanged.
    assert item_repo.get_grade(ITEM_ID).grade == Grade.VERY_GOOD.value
    assert publisher.events == []


def test_second_identical_run_is_idempotent_skip():
    pipeline, item_repo, *_rest = _build(
        provider_script=[_valid_json(Grade.GOOD, 0.99), _valid_json(Grade.LIKE_NEW, 0.99)]
    )
    first = pipeline.run(_message("idem-key-1"))
    second = pipeline.run(_message("idem-key-1"))

    assert first.outcome is PipelineOutcome.GRADED
    assert second.outcome is PipelineOutcome.SKIPPED_IDEMPOTENT
    # The grade from the first run is retained.
    assert item_repo.get_grade(ITEM_ID).grade == Grade.GOOD.value


def test_blank_idem_key_is_derived_from_item_and_photos():
    pipeline, item_repo, *_rest = _build(
        provider_script=[_valid_json(Grade.GOOD, 0.99)]
    )
    result = pipeline.run(GradingMessage(item_id=ITEM_ID, idem_key="", photo_keys=list(PHOTO_KEYS)))

    expected = derive_idempotency_key(ITEM_ID, PHOTO_KEYS)
    assert result.idem_key == expected
    assert item_repo.get_grade(ITEM_ID).idem_key == expected


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_unknown_item_raises_item_not_found():
    pipeline, *_rest = _build(
        provider_script=[_valid_json(Grade.GOOD, 0.99)], seed_meta=False
    )
    with pytest.raises(ItemNotFound):
        pipeline.run(_message())


def test_callable_router_adapter_is_invoked():
    calls: list[str] = []

    def route(item_id: str):
        calls.append(item_id)
        return type("D", (), {"disposition": "P2P"})()

    pipeline, *_rest = _build(
        provider_script=[_valid_json(Grade.GOOD, 0.99)],
        router=CallableRouter(route),
    )
    result = pipeline.run(_message())
    assert result.outcome is PipelineOutcome.GRADED
    assert calls == [ITEM_ID]
