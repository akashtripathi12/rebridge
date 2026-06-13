"""Property-based test for provider seam substitutability.

# Feature: rebridge-backend, Property 15: Provider seam substitutability

Property 15 (design.md): *For any* GradingProvider implementation that returns
schema-conforming output, the downstream pipeline behavior (gating,
persistence, branching) SHALL be identical, independent of the provider's
identity.

**Validates: Requirements 8.4**

The grading provider is a swappable seam: the GradingEngine is constructed with
an ordered list of :class:`~rebridge_data.interfaces.GradingProvider`
implementations and depends only on their *output*, never their identity or
name. This test pins that contract from two angles:

1. **Engine level** -- for the same conforming response content, the
   :class:`~rebridge_service.grading_engine.GradingEngine` returns the *same*
   :class:`~rebridge_service.models.GradeAssessment` regardless of the
   provider's ``name``.
2. **Pipeline level** -- running the full
   :class:`~rebridge_service.grading_pipeline.GradingPipeline` with providers
   that differ only in identity yields identical downstream behavior: the same
   gating outcome, the same persisted GRADE facet and Item status, the same
   Health Card, and the same Review_Queue contents.

The strategies generate varied (distinct) provider names and schema-conforming
grade assessments, constrained to the valid input space.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import (
    CatalogContext,
    GradingMessage,
    ItemMeta,
    ItemStatus,
)

from rebridge_service.confidence_gate import ConfidenceGate
from rebridge_service.eventing_service import EventingService
from rebridge_service.grade_schema import serialize_grade_assessment
from rebridge_service.grading_engine import GradingEngine
from rebridge_service.grading_pipeline import GradingPipeline, PipelineResult
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

ITEM_ID = "item-seam-1"
PHOTO_KEYS = ["items/item-seam-1/photo-0", "items/item-seam-1/photo-1"]
EST_VALUE = Decimal("100")
THRESHOLD = 0.80

# A high-contrast checkerboard: high variance-of-Laplacian (sharp) and a mean
# brightness around 127 -> passes both precheck checks (mirrors the pipeline
# unit tests). Decoded from the seeded object bytes below.
SHARP_PIXELS = [[255 if (r + c) % 2 == 0 else 0 for c in range(5)] for r in range(5)]

_nonempty_text = st.text(min_size=1, max_size=40)


def _decoder(_raw: bytes):
    return SHARP_PIXELS


@st.composite
def grade_assessments(draw: st.DrawFn) -> GradeAssessment:
    """Generate a schema-conforming GradeAssessment (the valid input space)."""

    grade = draw(st.sampled_from(list(Grade)))
    defects = draw(
        st.lists(
            st.builds(Defect, location=_nonempty_text, severity=_nonempty_text),
            max_size=5,
        )
    )
    completeness = draw(
        st.builds(
            CompletenessResult,
            is_complete=st.booleans(),
            missing_components=st.lists(_nonempty_text, max_size=5),
        )
    )
    confidence = draw(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    )
    summary = draw(_nonempty_text)
    return GradeAssessment(
        grade=grade,
        defects=defects,
        completeness=completeness,
        confidence=confidence,
        summary=summary,
    )


# Two-or-more distinct provider names (identities) to swap behind the seam.
provider_names = st.lists(_nonempty_text, min_size=2, max_size=4, unique=True)


def _engine_for(name: str, content: str) -> GradingEngine:
    """A single-provider cascade whose only provider has identity ``name``."""

    return GradingEngine(
        [FakeGradingProvider(name, script=[content])],
        timeout=None,
        max_json_retries=2,
    )


def _run_pipeline(provider_name: str, content: str) -> tuple[PipelineResult, FakeItemRepository, FakeReviewQueueRepository, FakeEventPublisher]:
    """Run the full pipeline with a provider of the given identity.

    Card issuance is made deterministic (fixed id + clock) so the only thing
    that varies between runs is the provider identity -- everything else is
    held constant, isolating the seam.
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
    review_repo = FakeReviewQueueRepository()
    publisher = FakeEventPublisher()

    card_service = HealthCardService(
        FakeCardSigner(),
        item_repo,
        id_factory=lambda: "card-fixed",
        clock=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    pipeline = GradingPipeline(
        item_repo=item_repo,
        object_store=store,
        review_repo=review_repo,
        precheck=QualityPrecheck(),
        grading_engine=_engine_for(provider_name, content),
        confidence_gate=ConfidenceGate(threshold=THRESHOLD),
        card_service=card_service,
        eventing=EventingService(publisher),
        router=None,
        pixel_decoder=_decoder,
        value_estimator=lambda meta, assessment: EST_VALUE,
        catalog_provider=None,
    )

    message = GradingMessage(item_id=ITEM_ID, idem_key="idem-seam-1", photo_keys=list(PHOTO_KEYS))
    result = pipeline.run(message)
    return result, item_repo, review_repo, publisher


@settings(max_examples=_ITERATIONS)
@given(grade_assessments(), provider_names)
def test_engine_returns_same_assessment_regardless_of_provider_name(
    assessment: GradeAssessment, names: list[str]
) -> None:
    """The parsed assessment is independent of which provider produced it."""

    content = serialize_grade_assessment(assessment)
    catalog = CatalogContext(category="electronics")
    images = [b"img-0", b"img-1"]

    results = [_engine_for(name, content).grade(images, catalog) for name in names]

    # Every provider identity yields an assessment equal to the source and to
    # each other -- the seam carries no provider-specific behavior.
    first = results[0]
    assert first == assessment
    for other in results[1:]:
        assert other == first


@settings(max_examples=_ITERATIONS)
@given(grade_assessments(), provider_names)
def test_pipeline_behavior_identical_regardless_of_provider_identity(
    assessment: GradeAssessment, names: list[str]
) -> None:
    """Gating, persistence, and branching are identical across providers."""

    content = serialize_grade_assessment(assessment)

    baseline = _run_pipeline(names[0], content)
    base_result, base_items, base_review, base_pub = baseline

    for name in names[1:]:
        result, items, review, pub = _run_pipeline(name, content)

        # Same gating outcome / branch taken.
        assert result.outcome is base_result.outcome
        # Same persisted GRADE facet (grade, confidence, confirmed flag, etc.).
        assert items.get_grade(ITEM_ID) == base_items.get_grade(ITEM_ID)
        # Same resulting Item status.
        assert (
            items.get_item(ITEM_ID).meta.status
            is base_items.get_item(ITEM_ID).meta.status
        )
        # Same Review_Queue contents (entries + ordering + priority).
        assert review.list_pending(10) == base_review.list_pending(10)
        # Same emitted lifecycle events.
        assert [e.event_type for e in pub.events] == [
            e.event_type for e in base_pub.events
        ]
        # Same Health Card (signature, contents) when one was produced.
        assert result.card == base_result.card
