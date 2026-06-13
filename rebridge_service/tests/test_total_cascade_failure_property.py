"""Property-based test for total-cascade-failure routing in the GradingPipeline.

# Feature: rebridge-backend, Property 14: Total cascade failure routes to review

Property 14 (design.md): *For any* photo set where every provider in the
cascade fails or times out, the Grading_Pipeline SHALL set the Item status to
PENDING_REVIEW.

**Validates: Requirements 8.3**

The strategy generates cascades of varied length (1-5 providers) where *every*
provider yields a non-conforming outcome - a scripted ``TimeoutError``, an
arbitrary provider ``RuntimeError``, or perpetually non-conforming JSON (which
the engine retries and then exhausts). Because no provider ever returns a
schema-conforming assessment, the ``GradingEngine`` raises ``TotalCascadeFailure``
and the pipeline must route the item to human review.

For every generated cascade the test asserts the pipeline:

1. reports the ``PENDING_REVIEW`` outcome and sets the item status to
   ``PENDING_REVIEW``;
2. persists *no* grade (nothing conformed, so there is nothing to store);
3. enqueues *exactly one* review entry for the item.

All scenarios run against the in-memory fakes and the programmable
``FakeGradingProvider`` - no AWS calls and no real wall-clock sleeps (timeouts
are scripted as ``TimeoutError`` while the engine runs calls inline with
``timeout=None``). Photos are seeded sharp/well-exposed so the quality precheck
passes and the flow always reaches the model cascade.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import GradingMessage, ItemMeta, ItemStatus

from rebridge_service.confidence_gate import ConfidenceGate
from rebridge_service.eventing_service import EventingService
from rebridge_service.grading_engine import GradingEngine
from rebridge_service.grading_pipeline import GradingPipeline, PipelineOutcome
from rebridge_service.health_card_service import HealthCardService
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

ITEM_ID = "item-cascade"
PHOTO_KEYS = ["items/item-cascade/photo-0", "items/item-cascade/photo-1"]
EST_VALUE = Decimal("100")

# A high-contrast checkerboard => high variance-of-Laplacian (sharp) and a mean
# brightness near 127, so the quality precheck passes and the flow reaches the
# model cascade.
_SHARP_PIXELS = [[255 if (r + c) % 2 == 0 else 0 for c in range(5)] for r in range(5)]


def _decoder(_raw: bytes):
    return _SHARP_PIXELS


# Every outcome is non-conforming, so the whole cascade always fails.
_FAILURE_OUTCOMES = ["timeout", "error", "bad_json"]


@st.composite
def total_failure_cascades(draw: st.DrawFn):
    """Generate a cascade (1-5 providers) where every provider fails."""
    n = draw(st.integers(min_value=1, max_value=5))
    return draw(st.lists(st.sampled_from(_FAILURE_OUTCOMES), min_size=n, max_size=n))


def _script_for(outcome: str, index: int):
    if outcome == "timeout":
        return [TimeoutError(f"provider-{index} timed out")]
    if outcome == "error":
        return [RuntimeError(f"provider-{index} boom")]
    # bad_json - single element repeats, exhausting the engine's JSON retries.
    return ["this is not valid json"]


def _build_pipeline(outcomes):
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
    review_repo = FakeReviewQueueRepository()
    publisher = FakeEventPublisher()
    providers = [
        FakeGradingProvider(f"p{i}", script=_script_for(o, i))
        for i, o in enumerate(outcomes)
    ]
    engine = GradingEngine(providers, timeout=None, max_json_retries=2)
    pipeline = GradingPipeline(
        item_repo=item_repo,
        object_store=store,
        review_repo=review_repo,
        precheck=QualityPrecheck(),
        grading_engine=engine,
        confidence_gate=ConfidenceGate(threshold=0.80),
        card_service=HealthCardService(FakeCardSigner(), item_repo),
        eventing=EventingService(publisher),
        router=None,
        pixel_decoder=_decoder,
        value_estimator=lambda meta, assessment: EST_VALUE,
        catalog_provider=None,
    )
    return pipeline, item_repo, review_repo


@settings(max_examples=_ITERATIONS)
@given(total_failure_cascades())
def test_total_cascade_failure_routes_to_review(outcomes):
    pipeline, item_repo, review_repo = _build_pipeline(outcomes)

    result = pipeline.run(
        GradingMessage(item_id=ITEM_ID, idem_key="", photo_keys=list(PHOTO_KEYS))
    )

    # 1. Pipeline routes the item to human review.
    assert result.outcome is PipelineOutcome.PENDING_REVIEW
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.PENDING_REVIEW

    # 2. No grade is persisted (nothing conformed).
    assert item_repo.get_grade(ITEM_ID) is None

    # 3. Exactly one review entry is enqueued for the item.
    pending = review_repo.list_pending(10)
    assert len(pending) == 1
    assert pending[0].item_id == ITEM_ID
