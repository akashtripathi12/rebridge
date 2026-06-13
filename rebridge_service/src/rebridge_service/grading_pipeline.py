"""The GradingPipeline: the worker-side grading orchestration (task 9.1).

This is the conductor that satisfies Requirements 4-9 (design.md ->
"Components and Interfaces -> Service Layer -> GradingPipeline"). It is invoked
by the SQS grading worker (and, in the 48h demo, synchronously inside the HTTP
request) with the identical interface in both paths, so flipping sync->async
requires no business-logic change (Requirement 7.1, 9.1).

The :meth:`GradingPipeline.run` flow, in order, is:

1. **Idempotency check** (Requirement 7.3). The submission's
   ``Idempotency_Key`` is derived from the item id and the photo-set hash
   (:func:`rebridge_service.idempotency.derive_idempotency_key`) when not
   supplied. If a grade for this item with the same key is already persisted,
   the pipeline skips reprocessing and retains the existing grade.
2. **Fetch images** through :class:`~rebridge_data.interfaces.ObjectStore`.
3. **Quality precheck** (Requirement 4). Every photo is assessed for blur and
   lighting; on failure the Item is set to ``RETAKE_REQUIRED`` and a retake
   prompt is returned without invoking the model.
4. **Catalog context** is assembled from the Item's META facet (overridable via
   an injected ``catalog_provider``).
5. **GradingEngine** drives the model cascade with strict-JSON parsing and
   retry (Requirements 5, 8). Non-conforming JSON after retries and total
   cascade failure both surface as
   :class:`~rebridge_service.grading_engine.TotalCascadeFailure`; the pipeline
   catches it and routes the Item to a review state
   (Requirements 5.7, 8.3).
6. **ConfidenceGate** compares the score against the configured threshold
   (Requirement 6).
7. **Branch** (Requirements 6.1, 6.2):

   * confidence >= threshold -> persist the GRADE (idempotent conditional
     write), set status ``GRADED``, render + sign + persist the Health Card,
     emit the ``GRADED`` lifecycle event, and invoke the injected router to
     produce and persist the routing DECISION.
   * confidence < threshold -> persist the GRADE (unconfirmed), set status
     ``PENDING_REVIEW``, and enqueue a Review_Queue entry with priority
     ``est_value * (1 - confidence)``.

### Injected router seam

The Routing_Agent (task 10.2) is built in parallel, so the pipeline depends on
a minimal injected **router protocol** rather than importing a concrete
``RoutingAgent``. Any object exposing ``route(item_id) -> decision`` (where the
returned decision carries a ``disposition`` attribute) satisfies
:class:`RoutingPort`; a plain callable is adapted via :class:`CallableRouter`.
The router owns persisting the DECISION facet and emitting the ``ROUTED`` event;
the pipeline only invokes it. When no router is injected the routing step is
skipped (the grade, card, and ``GRADED`` event are still produced), which keeps
the pipeline runnable while task 10.2 lands.

This module imports only the standard library, the service-layer components and
domain models, and the abstract data-layer types. It never imports boto3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from rebridge_data.interfaces import ItemRepository, ObjectStore, ReviewQueueRepository
from rebridge_data.models import (
    CatalogContext,
    CompletenessResult as DataCompletenessResult,
    Defect as DataDefect,
    GradeRecord,
    GradingMessage,
    ItemMeta,
    ItemStatus,
    ReviewQueueEntry,
)

from rebridge_service.confidence_gate import ConfidenceGate
from rebridge_service.eventing_service import EventingService
from rebridge_service.grading_engine import GradingEngine, TotalCascadeFailure
from rebridge_service.health_card_service import HealthCardService
from rebridge_service.models import GradeAssessment, HealthCard
from rebridge_service.quality_precheck import Photo, PixelMatrix, QualityPrecheck

__all__ = [
    "PixelDecoder",
    "ValueEstimator",
    "CatalogProvider",
    "RoutingResult",
    "RoutingPort",
    "CallableRouter",
    "PipelineError",
    "ItemNotFound",
    "PhotoDecoderRequired",
    "PipelineOutcome",
    "PipelineResult",
    "GradingPipeline",
]


# A decoder turns a fetched photo's raw bytes into the grayscale pixel matrix
# the QualityPrecheck consumes. The image-codec dependency lives in the worker
# adapter, not the service layer, so the decoder is injected.
PixelDecoder = Callable[[bytes], PixelMatrix]

# Estimates the recoverable value of an Item used for the review-queue priority
# (priority = est_value * (1 - confidence)). Receives the Item META and the
# grade assessment (``None`` on a total cascade failure where no grade exists).
ValueEstimator = Callable[[ItemMeta, "GradeAssessment | None"], Decimal]

# Builds the catalog context passed to the grading engine for an Item.
CatalogProvider = Callable[[ItemMeta], CatalogContext]


@runtime_checkable
class RoutingResult(Protocol):
    """Structural type of whatever the injected router returns.

    The pipeline only needs the selected disposition to emit observability; the
    router itself owns persisting the DECISION facet and emitting ``ROUTED``.
    """

    @property
    def disposition(self) -> Any: ...


@runtime_checkable
class RoutingPort(Protocol):
    """Minimal router seam the pipeline depends on (task 10.2 built in parallel).

    Any object exposing ``route(item_id)`` that computes, persists, and returns
    a routing decision satisfies this protocol. Concretely the Routing_Agent
    implements it; tests inject a fake; a bare callable is adapted by
    :class:`CallableRouter`.
    """

    def route(self, item_id: str) -> RoutingResult: ...


@dataclass
class CallableRouter:
    """Adapt a bare ``route(item_id) -> decision`` callable to :class:`RoutingPort`."""

    fn: Callable[[str], RoutingResult]

    def route(self, item_id: str) -> RoutingResult:
        return self.fn(item_id)


class PipelineError(Exception):
    """Base class for orchestration errors raised by :class:`GradingPipeline`."""


class ItemNotFound(PipelineError):
    """The submission referenced an Item that has no persisted META facet."""

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"item not found: {item_id}")


class PhotoDecoderRequired(PipelineError):
    """The precheck step was reached without an injected pixel decoder."""

    def __init__(self) -> None:
        super().__init__(
            "a pixel decoder must be injected to run the quality precheck; "
            "the worker adapter supplies the bytes->grayscale-matrix decode"
        )


class PipelineOutcome(Enum):
    """The mutually-exclusive terminal outcomes of a pipeline run."""

    SKIPPED_IDEMPOTENT = "SKIPPED_IDEMPOTENT"
    RETAKE_REQUIRED = "RETAKE_REQUIRED"
    GRADED = "GRADED"
    PENDING_REVIEW = "PENDING_REVIEW"


@dataclass
class PipelineResult:
    """The structured result of a single :meth:`GradingPipeline.run` call.

    Carries the terminal ``outcome`` plus whatever artifacts that path
    produced, so the worker (and tests) can observe exactly what happened
    without re-reading persistence.
    """

    outcome: PipelineOutcome
    item_id: str
    idem_key: str
    assessment: GradeAssessment | None = None
    grade: GradeRecord | None = None
    card: HealthCard | None = None
    decision: RoutingResult | None = None
    review_entry: ReviewQueueEntry | None = None
    retake_prompt: str | None = None
    reason: str = ""


@dataclass
class GradingPipeline:
    """Orchestrates idempotent grading from photos to grade/card/route/review.

    Collaborators are injected as abstract interfaces / already-built service
    components (the one-way ``service -> data`` dependency). The ``router`` is a
    minimal :class:`RoutingPort` so the concrete Routing_Agent (task 10.2) can be
    built in parallel; ``pixel_decoder``, ``value_estimator``, and
    ``catalog_provider`` are injectable seams that keep the orchestration pure
    and deterministic under test.
    """

    item_repo: ItemRepository
    object_store: ObjectStore
    review_repo: ReviewQueueRepository
    precheck: QualityPrecheck
    grading_engine: GradingEngine
    confidence_gate: ConfidenceGate
    card_service: HealthCardService
    eventing: EventingService
    router: RoutingPort | None = None
    pixel_decoder: PixelDecoder | None = None
    value_estimator: ValueEstimator | None = None
    catalog_provider: CatalogProvider | None = None

    # -- public entrypoint -------------------------------------------------
    def run(self, message: GradingMessage) -> PipelineResult:
        """Process one grading submission end to end.

        ``message`` carries the Item id, the photo object keys, and the
        ``Idempotency_Key`` (derived here when blank). Returns a
        :class:`PipelineResult` describing the terminal outcome. Raises
        :class:`ItemNotFound` for an unknown Item and
        :class:`PhotoDecoderRequired` when the precheck is reached without a
        decoder.
        """

        item_id = message.item_id
        photo_keys = list(message.photo_keys)
        idem_key = message.idem_key or self._derive_key(item_id, photo_keys)

        meta = self._load_meta(item_id)

        # 1. Idempotency check (Requirement 7.3): a grade already persisted under
        #    this key means we skip reprocessing and retain the existing grade.
        existing = self.item_repo.get_grade(item_id)
        if existing is not None and existing.idem_key == idem_key:
            return PipelineResult(
                outcome=PipelineOutcome.SKIPPED_IDEMPOTENT,
                item_id=item_id,
                idem_key=idem_key,
                grade=existing,
                reason="idempotency key already produced a persisted grade",
            )

        # The Item is now being graded.
        self.item_repo.update_status(item_id, ItemStatus.GRADING)

        # 2. Fetch images through the object store (never proxied via the API).
        images = [self.object_store.get_bytes(key) for key in photo_keys]

        # 3. Quality precheck (Requirement 4): gate before invoking the model.
        precheck_result = self._run_precheck(photo_keys, images)
        if not precheck_result.passed:
            self.item_repo.update_status(item_id, ItemStatus.RETAKE_REQUIRED)
            return PipelineResult(
                outcome=PipelineOutcome.RETAKE_REQUIRED,
                item_id=item_id,
                idem_key=idem_key,
                retake_prompt=precheck_result.retake_prompt,
                reason="one or more photos failed the quality precheck",
            )

        # 4. Catalog context for the grading engine.
        catalog = self._catalog_for(meta)

        # 5. Grading engine: cascade + strict parse + retry. A non-conforming
        #    response after retries or a total cascade failure both raise
        #    TotalCascadeFailure -> route to PENDING_REVIEW (Req 5.7, 8.3).
        try:
            assessment = self.grading_engine.grade(images, catalog)
        except TotalCascadeFailure as exc:
            return self._route_cascade_failure_to_review(
                item_id, idem_key, meta, str(exc)
            )

        # 6. Confidence gate (Requirement 6).
        decision = self.confidence_gate.decide(assessment.confidence)

        # 7. Branch on the gate decision.
        if decision.auto_continue:
            return self._auto_continue(item_id, idem_key, photo_keys, assessment)
        return self._route_to_review(item_id, idem_key, meta, assessment)

    # -- branch: confidence >= threshold -----------------------------------
    def _auto_continue(
        self,
        item_id: str,
        idem_key: str,
        photo_keys: list[str],
        assessment: GradeAssessment,
    ) -> PipelineResult:
        """Persist a confirmed grade, make the card, emit GRADED, route."""

        grade_record = self._to_grade_record(assessment, idem_key, confirmed=True)
        written = self.item_repo.put_grade_if_absent(item_id, idem_key, grade_record)
        if not written:
            # A concurrent submission persisted this grade first: honour
            # idempotency and retain the existing grade rather than double-process.
            existing = self.item_repo.get_grade(item_id)
            return PipelineResult(
                outcome=PipelineOutcome.SKIPPED_IDEMPOTENT,
                item_id=item_id,
                idem_key=idem_key,
                grade=existing,
                reason="grade already present for this idempotency key",
            )

        self.item_repo.update_status(item_id, ItemStatus.GRADED)

        # Render + sign + persist the Product Health Card (Requirements 11, 12).
        card = self.card_service.issue_card(
            item_id, annotated_photo_keys=list(photo_keys)
        )

        # Continue to event emission (Requirement 6.1): the confirmed grade.
        self.eventing.emit_graded(item_id)

        # Invoke the injected router; it owns persisting DECISION and emitting
        # ROUTED. Skipped cleanly when no router is wired yet (task 10.2).
        routing_result: RoutingResult | None = None
        if self.router is not None:
            routing_result = self.router.route(item_id)

        return PipelineResult(
            outcome=PipelineOutcome.GRADED,
            item_id=item_id,
            idem_key=idem_key,
            assessment=assessment,
            grade=grade_record,
            card=card,
            decision=routing_result,
            reason="confidence at or above threshold; graded and routed",
        )

    # -- branch: confidence < threshold ------------------------------------
    def _route_to_review(
        self,
        item_id: str,
        idem_key: str,
        meta: ItemMeta,
        assessment: GradeAssessment,
    ) -> PipelineResult:
        """Persist an unconfirmed grade, set PENDING_REVIEW, enqueue review."""

        grade_record = self._to_grade_record(assessment, idem_key, confirmed=False)
        written = self.item_repo.put_grade_if_absent(item_id, idem_key, grade_record)
        if not written:
            existing = self.item_repo.get_grade(item_id)
            return PipelineResult(
                outcome=PipelineOutcome.SKIPPED_IDEMPOTENT,
                item_id=item_id,
                idem_key=idem_key,
                grade=existing,
                reason="grade already present for this idempotency key",
            )

        self.item_repo.update_status(item_id, ItemStatus.PENDING_REVIEW)

        est_value = self._estimate_value(meta, assessment)
        entry = self._build_review_entry(
            item_id, est_value, assessment.confidence, grade_record
        )
        self.review_repo.enqueue(entry)

        return PipelineResult(
            outcome=PipelineOutcome.PENDING_REVIEW,
            item_id=item_id,
            idem_key=idem_key,
            assessment=assessment,
            grade=grade_record,
            review_entry=entry,
            reason="confidence below threshold; routed to human review",
        )

    # -- branch: total cascade failure / non-conforming JSON ---------------
    def _route_cascade_failure_to_review(
        self,
        item_id: str,
        idem_key: str,
        meta: ItemMeta,
        detail: str,
    ) -> PipelineResult:
        """Set PENDING_REVIEW and enqueue review when grading cannot complete.

        Covers both a non-conforming model response after the allowed retries
        (Requirement 5.7) and a total cascade failure where every provider
        failed or timed out (Requirement 8.3). No grade exists, so the queued
        entry carries confidence 0.0 and a best-effort value estimate.
        """

        self.item_repo.update_status(item_id, ItemStatus.PENDING_REVIEW)

        est_value = self._estimate_value(meta, None)
        entry = self._build_review_entry(item_id, est_value, 0.0, None)
        self.review_repo.enqueue(entry)

        return PipelineResult(
            outcome=PipelineOutcome.PENDING_REVIEW,
            item_id=item_id,
            idem_key=idem_key,
            review_entry=entry,
            reason=f"grading could not produce a conforming grade: {detail}",
        )

    # -- helpers -----------------------------------------------------------
    def _derive_key(self, item_id: str, photo_keys: list[str]) -> str:
        # Imported lazily to keep the module import graph flat and obvious.
        from rebridge_service.idempotency import derive_idempotency_key

        return derive_idempotency_key(item_id, photo_keys)

    def _load_meta(self, item_id: str) -> ItemMeta:
        aggregate = self.item_repo.get_item(item_id)
        if aggregate is None:
            raise ItemNotFound(item_id)
        return aggregate.meta

    def _run_precheck(self, photo_keys: list[str], images: list[bytes]):
        if self.pixel_decoder is None:
            raise PhotoDecoderRequired()
        photos = [
            Photo(key=key, pixels=self.pixel_decoder(raw))
            for key, raw in zip(photo_keys, images)
        ]
        return self.precheck.assess(photos)

    def _catalog_for(self, meta: ItemMeta) -> CatalogContext:
        if self.catalog_provider is not None:
            return self.catalog_provider(meta)
        return CatalogContext(category=meta.category)

    def _estimate_value(
        self, meta: ItemMeta, assessment: GradeAssessment | None
    ) -> Decimal:
        if self.value_estimator is None:
            return Decimal("0")
        return Decimal(self.value_estimator(meta, assessment))

    @staticmethod
    def _build_review_entry(
        item_id: str,
        value: Decimal,
        confidence: float,
        grade: GradeRecord | None,
    ) -> ReviewQueueEntry:
        priority = float(value) * (1.0 - float(confidence))
        return ReviewQueueEntry(
            item_id=item_id,
            value=value,
            confidence=float(confidence),
            priority=priority,
            grade=grade,
        )

    @staticmethod
    def _to_grade_record(
        assessment: GradeAssessment, idem_key: str, *, confirmed: bool
    ) -> GradeRecord:
        """Map a service-layer :class:`GradeAssessment` to a data GradeRecord."""

        completeness = DataCompletenessResult(
            complete=assessment.completeness.is_complete,
            missing_components=list(assessment.completeness.missing_components),
        )
        defects = [
            DataDefect(location=d.location, severity=d.severity)
            for d in assessment.defects
        ]
        return GradeRecord(
            grade=assessment.grade.value,
            confidence=assessment.confidence,
            summary=assessment.summary,
            defects=defects,
            completeness=completeness,
            idem_key=idem_key,
            confirmed=confirmed,
        )
