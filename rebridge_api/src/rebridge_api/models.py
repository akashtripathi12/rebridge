"""Pydantic request/response models for the ReBridge API (task 17.1).

These transport models own the API's wire shape and serialization; they are the
boundary between FastAPI and the framework-free service-layer domain models.
The routers map a validated request model to a service call and map the
service's domain/record objects back to a response model via the
``from_*`` constructors here.

Design references:
- API Contracts table in design.md ("Components and Interfaces -> API Layer").
- Service-layer records in ``rebridge_data.models`` and domain models in
  ``rebridge_service.models``.

Money values are carried as :class:`~decimal.Decimal` so the unit-economics math
(routing margins, prices) survives the round trip without binary-float drift.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rebridge_data.models import (
    CardRecord,
    DecisionRecord,
    GradeRecord,
    ItemAggregate,
    ItemMeta,
    ListingPatch,
    ListingRecord,
)

__all__ = [
    "CreateItemRequest",
    "ItemMetaResponse",
    "PresignRequest",
    "PresignedUrlModel",
    "PresignResponse",
    "GradeRequest",
    "GradeAcceptedResponse",
    "DefectModel",
    "CompletenessModel",
    "GradeFacetModel",
    "CardFacetModel",
    "DecisionFacetModel",
    "ListingFacetModel",
    "ItemAggregateResponse",
    "RouteRequest",
    "RouteDecisionResponse",
    "CreateListingRequest",
    "UpdateListingRequest",
    "ListingResponse",
    "MarketListingModel",
    "MarketplaceResponse",
    "BuyResponse",
    "HealthCardModel",
    "CardVerificationResponse",
    "BuyerMatchModel",
    "MatchesResponse",
    "ReviewQueueItemModel",
    "ReviewQueueResponse",
    "ReviewActionRequest",
    "ErrorResponse",
]


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


class CreateItemRequest(BaseModel):
    """Create-item body (Requirements 1.1, 1.2, 1.3).

    All fields are optional at the transport layer so the *service* performs the
    authoritative required-field validation and names the missing field in its
    error (Requirement 1.3, mapped to 422). ``order_id`` is required only for an
    order-scan context; the service enforces that per context shape.
    """

    model_config = ConfigDict(extra="allow")

    context_source: str | None = Field(
        default=None, description="'order_scan' or 'manual'"
    )
    category: str | None = None
    age_months: int | None = None
    order_id: str | None = Field(
        default=None, description="Scanned order reference (order-scan context)"
    )
    expected_price: float | None = Field(
        default=None, description="User's expected selling price"
    )
    original_price: float | None = Field(
        default=None, description="Original retail price of the item"
    )

    def to_service_request(self) -> dict[str, Any]:
        """Return the mapping passed to ``ItemService.create_item``.

        Only fields the client actually set are forwarded, so an omitted
        required field surfaces as the service's ``MissingField`` (naming it)
        rather than being silently coerced.
        """

        return self.model_dump(exclude_unset=True)


class ItemMetaResponse(BaseModel):
    """The META facet of an Item returned on create and within an aggregate."""

    item_id: str
    status: str
    category: str
    age_months: int
    context_source: str
    created_at: str
    context_ref: str | None = None
    original_price: float | None = None
    expected_price: float | None = None

    @classmethod
    def from_meta(cls, meta: ItemMeta) -> "ItemMetaResponse":
        return cls(
            item_id=meta.item_id,
            status=meta.status.value if hasattr(meta.status, "value") else str(meta.status),
            category=meta.category,
            age_months=meta.age_months,
            context_source=meta.context_source,
            created_at=meta.created_at,
            context_ref=meta.context_ref,
            original_price=float(meta.original_price) if meta.original_price is not None else None,
            expected_price=float(meta.expected_price) if meta.expected_price is not None else None,
        )


# ---------------------------------------------------------------------------
# Presigned photo upload
# ---------------------------------------------------------------------------


class PresignRequest(BaseModel):
    """Presigned-upload request (Requirement 2.1, 2.4).

    ``count`` is the number of photo slots; the service rejects counts outside
    the inclusive 2-4 range with a 422 range error.
    """

    count: int = Field(description="Number of photo slots (2-4)")


class PresignedUrlModel(BaseModel):
    """A single presigned S3 PUT target (Requirement 2.1, 2.2)."""

    url: str
    method: str = "PUT"
    headers: dict[str, str] = Field(default_factory=dict)
    expires_in: int = 300


class PresignResponse(BaseModel):
    """The presigned upload targets for a grading submission."""

    item_id: str
    urls: list[PresignedUrlModel]


# ---------------------------------------------------------------------------
# Grade (async enqueue)
# ---------------------------------------------------------------------------


class GradeRequest(BaseModel):
    """Grade-submission body (Requirements 7.1, 7.2).

    ``photo_keys`` are the uploaded S3 object keys for the photo set; the
    Idempotency-Key is derived from the item id and the photo-set hash unless an
    explicit ``idempotency_key`` override is supplied.
    """

    photo_keys: list[str] = Field(
        default_factory=list, description="Uploaded photo object keys"
    )
    idempotency_key: str | None = Field(
        default=None, description="Optional explicit idempotency key override"
    )


class GradeAcceptedResponse(BaseModel):
    """202 Accepted body for an enqueued grading submission (Requirement 7.1)."""

    item_id: str
    idempotency_key: str
    status: str = "enqueued"


# ---------------------------------------------------------------------------
# Item aggregate retrieval
# ---------------------------------------------------------------------------


class DefectModel(BaseModel):
    location: str
    severity: str


class CompletenessModel(BaseModel):
    complete: bool
    missing_components: list[str] = Field(default_factory=list)


class GradeFacetModel(BaseModel):
    """The GRADE facet (Requirement 1.4)."""

    grade: str
    confidence: float
    summary: str
    defects: list[DefectModel] = Field(default_factory=list)
    completeness: CompletenessModel | None = None
    idem_key: str | None = None
    confirmed: bool = False

    @classmethod
    def from_record(cls, rec: GradeRecord) -> "GradeFacetModel":
        completeness = (
            CompletenessModel(
                complete=rec.completeness.complete,
                missing_components=list(rec.completeness.missing_components),
            )
            if rec.completeness is not None
            else None
        )
        return cls(
            grade=rec.grade,
            confidence=rec.confidence,
            summary=rec.summary,
            defects=[DefectModel(location=d.location, severity=d.severity) for d in rec.defects],
            completeness=completeness,
            idem_key=rec.idem_key,
            confirmed=rec.confirmed,
        )


class CardFacetModel(BaseModel):
    """The CARD facet (Requirement 1.4)."""

    card_id: str
    item_id: str
    signature: str
    qr_target: str
    graded_at: str
    warranty_stance: str
    annotated_photo_keys: list[str] = Field(default_factory=list)

    @classmethod
    def from_record(cls, rec: CardRecord) -> "CardFacetModel":
        return cls(
            card_id=rec.card_id,
            item_id=rec.item_id,
            signature=rec.signature,
            qr_target=rec.qr_target,
            graded_at=rec.graded_at,
            warranty_stance=rec.warranty_stance,
            annotated_photo_keys=list(rec.annotated_photo_keys),
        )


class DecisionFacetModel(BaseModel):
    """The DECISION facet (Requirement 1.4, 10.7)."""

    disposition: str
    price: Decimal
    value: Decimal
    cost: Decimal
    margin: Decimal
    rationale: str

    @classmethod
    def from_record(cls, rec: DecisionRecord) -> "DecisionFacetModel":
        return cls(
            disposition=rec.disposition,
            price=rec.price,
            value=rec.value,
            cost=rec.cost,
            margin=rec.margin,
            rationale=rec.rationale,
        )


class ListingFacetModel(BaseModel):
    """The LISTING facet (Requirement 1.4, 3.x)."""

    item_id: str
    status: str
    category: str
    price: Decimal
    geohash5: str
    listed_at: str

    @classmethod
    def from_record(cls, rec: ListingRecord) -> "ListingFacetModel":
        return cls(
            item_id=rec.item_id,
            status=rec.status,
            category=rec.category,
            price=rec.price,
            geohash5=rec.geohash5,
            listed_at=rec.listed_at,
        )


class ItemAggregateResponse(BaseModel):
    """An Item's status plus exactly its persisted facets (Requirement 1.4)."""

    meta: ItemMetaResponse
    grade: GradeFacetModel | None = None
    card: CardFacetModel | None = None
    decision: DecisionFacetModel | None = None
    listing: ListingFacetModel | None = None

    @classmethod
    def from_aggregate(cls, agg: ItemAggregate) -> "ItemAggregateResponse":
        return cls(
            meta=ItemMetaResponse.from_meta(agg.meta),
            grade=GradeFacetModel.from_record(agg.grade) if agg.grade is not None else None,
            card=CardFacetModel.from_record(agg.card) if agg.card is not None else None,
            decision=(
                DecisionFacetModel.from_record(agg.decision)
                if agg.decision is not None
                else None
            ),
            listing=(
                ListingFacetModel.from_record(agg.listing)
                if agg.listing is not None
                else None
            ),
        )


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class RouteRequest(BaseModel):
    """Routing request (Requirement 10).

    ``geohash5`` optionally attaches a neighborhood demand signal to the
    decision context; it never changes the margin-based selection.
    """

    geohash5: str | None = None


class RouteDecisionResponse(BaseModel):
    """The routing decision returned by ``POST /items/{id}/route`` (Req 10.7)."""

    disposition: str
    price: Decimal
    value: Decimal
    cost: Decimal
    margin: Decimal
    rationale: str
    # Demo-derived catalog MRP (original "price when new"); see MarketListingModel
    # (G4). Optional so the field is additive and the contract stays backward
    # compatible.
    price_new: Decimal | None = None


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------


class CreateListingRequest(BaseModel):
    """Create-listing body (Requirements 3.1, 3.5).

    Listing an Item requires it to be graded; the service rejects an ungraded
    Item with a 409 grade-required error.
    """

    item_id: str
    category: str
    price: Decimal
    geohash5: str
    status: str | None = None


class UpdateListingRequest(BaseModel):
    """Partial listing update (Requirement 3.2). Unset fields are unchanged."""

    status: str | None = None
    category: str | None = None
    price: Decimal | None = None
    geohash5: str | None = None

    def to_patch(self) -> ListingPatch:
        return ListingPatch(**self.model_dump(exclude_unset=True))


class ListingResponse(ListingFacetModel):
    """A listing returned by listing CRUD (Requirement 3.x)."""

    @classmethod
    def from_record(cls, rec: ListingRecord) -> "ListingResponse":
        return cls(
            item_id=rec.item_id,
            status=rec.status,
            category=rec.category,
            price=rec.price,
            geohash5=rec.geohash5,
            listed_at=rec.listed_at,
        )


class MarketListingModel(BaseModel):
    """A marketplace listing enriched for buyer browse (G3 + G4).

    Extends the base LISTING facet fields (``item_id``, ``status``,
    ``category``, ``price``, ``geohash5``, ``listed_at``) with the buyer-facing
    fields the marketplace tiles need:

    * ``listing_id`` — stable ``lst_<item_id>`` identifier;
    * ``grade`` — the item's GRADE facet label, or ``None`` if ungraded;
    * ``distance_km`` — haversine distance from the query ``geo`` to the
      listing's geohash, or a deterministic seeded distance when no ``geo`` is
      supplied (treated as authoritative by the frontend);
    * ``price_new`` — demo-derived catalog MRP (``round(price * 1.5, 2)``);
    * ``health_card_id`` — the item's CARD facet id, or ``None``;
    * ``title`` — best-effort title (the category);
    * ``thumb_key`` — a stable glyph id (the category string).
    """

    item_id: str
    listing_id: str
    status: str
    category: str
    price: Decimal
    price_new: Decimal
    geohash5: str
    listed_at: str
    grade: str | None = None
    distance_km: float
    health_card_id: str | None = None
    title: str
    thumb_key: str

    @classmethod
    def from_record(
        cls,
        rec: ListingRecord,
        *,
        grade: str | None,
        health_card_id: str | None,
        distance_km: float,
        thumb_key: str = "shoe",
    ) -> "MarketListingModel":
        """Build the enriched marketplace listing from a record + joined facets."""

        price_new = (rec.price * Decimal("1.5")).quantize(Decimal("0.01"))
        return cls(
            item_id=rec.item_id,
            listing_id=f"lst_{rec.item_id}",
            status=rec.status,
            category=rec.category,
            price=rec.price,
            price_new=price_new,
            geohash5=rec.geohash5,
            listed_at=rec.listed_at,
            grade=grade,
            distance_km=distance_km,
            health_card_id=health_card_id,
            title=rec.category,
            thumb_key=thumb_key,
        )


class MarketplaceResponse(BaseModel):
    """Marketplace query result (Requirement 3.3, 13; extended by G3/G4)."""

    listings: list[MarketListingModel] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Simulated checkout
# ---------------------------------------------------------------------------


class BuyResponse(BaseModel):
    """Simulated checkout result (Requirements 15.5, 18.4).

    Payments are simulated in v1: no payment is processed. The purchase
    transitions the Item to SOLD and a SOLD lifecycle event is emitted.
    """

    item_id: str
    status: str = "SOLD"
    order_id: str
    simulated: bool = True
    message: str = "Simulated checkout: no payment processed. SOLD event emitted."


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """A uniform error envelope returned by the exception handlers."""

    detail: str
    field: str | None = None


# ---------------------------------------------------------------------------
# Public card verification (task 17.4)
# ---------------------------------------------------------------------------


class HealthCardModel(BaseModel):
    """The verified contents of a Product Health Card (Requirements 11.1, 12.2).

    Returned only when verification succeeds; the grade is carried as its
    human-readable label and money/identifier fields are plain strings, so the
    public, unauthenticated payload exposes exactly the rendered card contents.
    """

    card_id: str
    item_id: str
    grade: str
    graded_at: str
    defect_summary: str
    warranty_stance: str
    annotated_photo_keys: list[str] = Field(default_factory=list)
    signature: str
    qr_target: str

    @classmethod
    def from_card(cls, card: Any) -> "HealthCardModel":
        """Map a service-layer ``HealthCard`` to the transport model."""

        grade = card.grade
        grade_label = grade.value if hasattr(grade, "value") else str(grade)
        return cls(
            card_id=card.card_id,
            item_id=card.item_id,
            grade=grade_label,
            graded_at=card.graded_at,
            defect_summary=card.defect_summary,
            warranty_stance=card.warranty_stance,
            annotated_photo_keys=list(card.annotated_photo_keys),
            signature=card.signature,
            qr_target=card.qr_target,
        )


class CardVerificationResponse(BaseModel):
    """Public verification outcome (Requirements 12.1-12.4, 16.3).

    ``verified`` is True when the recomputed signature matches the stored
    signature, and ``card`` then carries the rendered card contents
    (Requirement 12.2). When False the card is *tampered* and ``card`` is
    ``None`` so altered contents are never surfaced as authentic
    (Requirement 12.3). ``reason`` is a short human-readable explanation.
    """

    verified: bool
    card: HealthCardModel | None = None
    reason: str = ""

    @classmethod
    def from_result(cls, result: Any) -> "CardVerificationResponse":
        """Map a service-layer ``VerificationResult`` to the transport model."""

        return cls(
            verified=result.verified,
            card=(
                HealthCardModel.from_card(result.card)
                if result.verified and result.card is not None
                else None
            ),
            reason=result.reason,
        )


# ---------------------------------------------------------------------------
# Demand matches (G1: GET /items/{item_id}/matches)
# ---------------------------------------------------------------------------


class BuyerMatchModel(BaseModel):
    """A single ranked buyer match (G1).

    ``distance_km`` and ``match_score`` are JSON numbers; ``intent_tier`` is one
    of ``HIGH``/``MEDIUM``/``LOW``; ``display_label`` is PII-free.
    """

    buyer_id: str
    display_label: str
    distance_km: float
    match_score: float
    match_reasons: list[str] = Field(default_factory=list)
    intent_tier: str

    @classmethod
    def from_match(cls, match: Any) -> "BuyerMatchModel":
        return cls(
            buyer_id=match.buyer_id,
            display_label=match.display_label,
            distance_km=match.distance_km,
            match_score=match.match_score,
            match_reasons=list(match.match_reasons),
            intent_tier=match.intent_tier,
        )


class MatchesResponse(BaseModel):
    """Ranked buyer matches for a graded Item (G1).

    ``generated_at`` is the ISO-8601 instant the view was produced. An empty
    result carries ``matches: []``, ``match_count_within_5km: 0``, and
    ``top_reason: null``.
    """

    item_id: str
    generated_at: str
    matches: list[BuyerMatchModel] = Field(default_factory=list)
    match_count_within_5km: int = 0
    top_reason: str | None = None

    @classmethod
    def from_view(cls, view: Any, generated_at: str) -> "MatchesResponse":
        return cls(
            item_id=view.item_id,
            generated_at=generated_at,
            matches=[BuyerMatchModel.from_match(m) for m in view.matches],
            match_count_within_5km=view.match_count_within_5km,
            top_reason=view.top_reason,
        )


# ---------------------------------------------------------------------------
# Review queue (G2: GET /review/queue, POST /review/{item_id})
# ---------------------------------------------------------------------------


class ReviewQueueItemModel(BaseModel):
    """A single review-queue item (G2).

    ``confidence`` is a JSON number; ``est_value`` is a money string;
    ``priority`` is the server-computed tier (HIGH/MEDIUM/LOW).
    """

    item_id: str
    title: str
    ai_grade: str
    confidence: float
    est_value: Decimal
    priority: str
    photo_keys: list[str] = Field(default_factory=list)
    created_at: str

    @classmethod
    def from_view(cls, view: Any) -> "ReviewQueueItemModel":
        return cls(
            item_id=view.item_id,
            title=view.title,
            ai_grade=view.ai_grade,
            confidence=view.confidence,
            est_value=view.est_value,
            priority=view.priority,
            photo_keys=list(view.photo_keys),
            created_at=view.created_at,
        )


class ReviewQueueResponse(BaseModel):
    """The prioritized review queue (G2)."""

    queue: list[ReviewQueueItemModel] = Field(default_factory=list)
    total: int = 0

    @classmethod
    def from_views(cls, views: list[Any]) -> "ReviewQueueResponse":
        items = [ReviewQueueItemModel.from_view(v) for v in views]
        return cls(queue=items, total=len(items))


class ReviewActionRequest(BaseModel):
    """A reviewer confirm/override action (G2).

    ``action`` is ``CONFIRM`` or ``OVERRIDE``. When ``OVERRIDE``,
    ``override_grade`` must be a valid grade label; when ``CONFIRM`` it is
    ``null``.
    """

    action: str
    override_grade: str | None = None
