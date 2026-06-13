"""Property-based test for non-conforming model response routing.

# Feature: rebridge-backend, Property 8: Non-conforming model response routes to review

Property 8 (design.md): *For any* model response that does not parse as
schema-conforming JSON (after the allowed retries), the Grading_Pipeline SHALL
set the Item to a review state.

**Validates: Requirements 5.7**

Requirement 5.7: *IF the Grading_Engine returns a response that does not parse
as schema-conforming JSON, THEN THE Grading_Pipeline SHALL set the Item to a
review state.*

The strategy below generates *non-conforming* model output spanning three
meaningful families of junk:

* **arbitrary junk text** -- free-form strings that are not JSON at all;
* **malformed JSON fragments** -- truncated/garbled structures that fail to
  decode;
* **structurally-invalid JSON objects** -- decodable JSON that violates the
  grade-assessment schema (missing required fields, wrong types, unknown grade
  label, out-of-range confidence, empty summary, unknown extra fields, ...).

Every generated value is screened through the real strict parser
(:func:`parse_grade_assessment`) with :func:`hypothesis.assume`, so the test
only ever feeds the pipeline output the schema parser genuinely rejects. The
``GradingEngine`` is wired with ``max_json_retries=2`` (3 attempts total) and
the provider replays a non-conforming script across every attempt, so the
cascade is exhausted and raises ``TotalCascadeFailure`` -- exactly the
"after the allowed retries" condition of Property 8.

The test then asserts the post-condition holds for *any* such junk: the
Grading_Pipeline routes the Item to a review state -- ``PENDING_REVIEW`` status
and a single Review_Queue entry -- while persisting **no** grade and emitting
**no** lifecycle event (nothing conformed, so there is nothing to grade or
announce).
"""

from __future__ import annotations

import json
from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from rebridge_data.models import GradingMessage, ItemMeta, ItemStatus

from rebridge_service.confidence_gate import ConfidenceGate
from rebridge_service.eventing_service import EventingService
from rebridge_service.grade_schema import GradeSchemaError, parse_grade_assessment
from rebridge_service.grading_engine import GradingEngine
from rebridge_service.grading_pipeline import (
    GradingPipeline,
    PipelineOutcome,
)
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

ITEM_ID = "item-prop8"
PHOTO_KEYS = ["items/item-prop8/photo-0", "items/item-prop8/photo-1"]
EST_VALUE = Decimal("100")

# A high-contrast checkerboard: sharp (high variance-of-Laplacian) with mean
# brightness ~127 -> passes both quality-precheck checks so the flow always
# reaches the Grading_Engine (the precheck never short-circuits these runs).
SHARP_PIXELS = [[255 if (r + c) % 2 == 0 else 0 for c in range(5)] for r in range(5)]


def _decoder(_raw: bytes):
    return SHARP_PIXELS


def _build(provider_script):
    """Wire a pipeline over in-memory fakes with a scripted junk provider."""
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
    engine = GradingEngine(
        [FakeGradingProvider("nova", script=provider_script)],
        timeout=None,
        max_json_retries=2,
    )
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
    return pipeline, item_repo, review_repo, publisher


# ---------------------------------------------------------------------------
# Strategies: non-conforming model output
# ---------------------------------------------------------------------------

# Family 1: arbitrary junk text -- usually not JSON at all.
_junk_text = st.text(min_size=0, max_size=60)

# Family 2: hand-picked malformed JSON fragments and decodable-but-wrong-shape
# scalars/arrays (a conforming payload must be a JSON *object*).
_malformed_json = st.sampled_from(
    [
        "",
        "   ",
        "{",
        "}",
        "[",
        "]",
        "{,}",
        "{'grade': 'GOOD'}",  # single quotes: invalid JSON
        '{"grade": }',  # missing value
        '{"grade": "GOOD",}',  # trailing comma
        "null",
        "true",
        "false",
        "42",
        "3.14",
        '"a bare string"',
        "[1, 2, 3]",
        "{}",  # empty object: missing every required field
        "not json at all",
        "<html>nope</html>",
        "undefined",
        "NaN",
    ]
)


@st.composite
def _invalid_json_object(draw: st.DrawFn) -> str:
    """A decodable JSON object that violates the grade-assessment schema.

    Builds the canonical shape then perturbs it in at least one schema-breaking
    way: dropping required fields, corrupting types, using an unknown grade
    label, pushing confidence out of [0, 1], blanking the summary, or injecting
    an unknown extra field. The result is screened by ``assume`` downstream so
    any accidental conforming payload is discarded.
    """

    obj: dict = {
        "grade": draw(
            st.sampled_from(["MINT", "SUPERB", "bad", "", "good", "Like New", 1, None])
        ),
        "defects": draw(
            st.sampled_from(
                [
                    [],
                    "not-a-list",
                    [{"location": "corner"}],  # defect missing severity
                    [{"severity": "minor"}],  # defect missing location
                    [{"location": "", "severity": "minor"}],  # empty location
                    [{"location": "corner", "severity": "minor", "x": 1}],  # extra key
                    None,
                ]
            )
        ),
        "completeness": draw(
            st.sampled_from(
                [
                    {"is_complete": True, "missing_components": []},
                    {"is_complete": "yes", "missing_components": []},  # wrong type
                    {"missing_components": []},  # missing is_complete
                    {"is_complete": True},  # missing missing_components
                    "not-an-object",
                    None,
                ]
            )
        ),
        "confidence": draw(
            st.sampled_from([-0.5, 1.5, 2, "high", None, True, "0.9"])
        ),
        "summary": draw(st.sampled_from(["", 0, None, [], {"text": "x"}])),
    }

    # Randomly drop a subset of required keys (dropping all leaves "{}").
    droppable = draw(
        st.lists(
            st.sampled_from(
                ["grade", "defects", "completeness", "confidence", "summary"]
            ),
            max_size=5,
            unique=True,
        )
    )
    for key in droppable:
        obj.pop(key, None)

    # Optionally inject an unknown top-level field (rejected by the strict parser).
    if draw(st.booleans()):
        obj["unexpected_field"] = draw(st.sampled_from([1, "x", True, None]))

    return json.dumps(obj)


_non_conforming_value = st.one_of(_junk_text, _malformed_json, _invalid_json_object())


def _is_non_conforming(content: str) -> bool:
    """True iff the strict schema parser rejects ``content`` (Requirement 5.6)."""
    try:
        parse_grade_assessment(content)
        return False
    except GradeSchemaError:
        return True


# A provider script is a non-empty list of non-conforming strings; the fake
# replays them across the cascade's retry attempts.
_non_conforming_script = st.lists(_non_conforming_value, min_size=1, max_size=4)


@settings(max_examples=_ITERATIONS)
@given(_non_conforming_script)
def test_non_conforming_response_routes_to_review(script: list[str]) -> None:
    """Any non-conforming model output routes the Item to a review state.

    Validates Property 8 / Requirement 5.7: after the allowed JSON retries are
    exhausted on non-conforming output, the Grading_Pipeline sets the Item to a
    review state -- PENDING_REVIEW with exactly one Review_Queue entry -- and
    persists no grade and emits no lifecycle event.
    """

    # Only exercise genuinely non-conforming output: discard any rare generated
    # value the strict parser would actually accept.
    assume(all(_is_non_conforming(content) for content in script))

    pipeline, item_repo, review_repo, publisher = _build(script)

    result = pipeline.run(
        GradingMessage(item_id=ITEM_ID, idem_key="idem-key-1", photo_keys=list(PHOTO_KEYS))
    )

    # The Item is routed to a review state.
    assert result.outcome is PipelineOutcome.PENDING_REVIEW
    assert item_repo.get_item(ITEM_ID).meta.status is ItemStatus.PENDING_REVIEW

    # No grade was persisted -- nothing conformed, so there is no grade to keep.
    assert item_repo.get_grade(ITEM_ID) is None

    # Exactly one Review_Queue entry was enqueued for this Item.
    pending = review_repo.list_pending(10)
    assert len(pending) == 1
    assert pending[0].item_id == ITEM_ID

    # No lifecycle event is emitted for an Item that was never graded.
    assert publisher.events == []
