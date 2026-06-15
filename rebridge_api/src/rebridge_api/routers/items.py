"""Item routes: create, presign, grade (async), retrieve, route (task 17.1).

Maps the item slice of the API contract (design.md "API Contracts") to
``ItemService`` / ``RoutingAgent`` calls and the grading work queue. Service
exceptions surface to the handlers registered in :mod:`rebridge_api.errors`, so
these handlers stay thin: validate transport, call the service, shape the
response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from rebridge_data.models import GradingMessage

from rebridge_api.dependencies import (
    CurrentUser,
    Services,
    get_current_operator,
    get_current_user,
    get_services,
)
from rebridge_api.models import (
    CreateItemRequest,
    GradeAcceptedResponse,
    GradeRequest,
    ItemAggregateResponse,
    ItemMetaResponse,
    PresignRequest,
    PresignResponse,
    PresignedUrlModel,
    RouteDecisionResponse,
    RouteRequest,
)

router = APIRouter(tags=["items"])


@router.post(
    "/items",
    status_code=status.HTTP_201_CREATED,
    response_model=ItemMetaResponse,
)
def create_item(
    body: CreateItemRequest,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_operator),
) -> ItemMetaResponse:
    """Create an Item from an order-scan or manual context (Req 1.1, 1.2, 1.3).

    The service performs required-field validation and names any missing field;
    that surfaces as a 422 via the registered handler (Requirement 1.3).
    """

    meta = services.item_service.create_item(body.to_service_request())
    return ItemMetaResponse.from_meta(meta)


@router.post(
    "/items/{item_id}/photos:presign",
    response_model=PresignResponse,
)
def presign_photos(
    item_id: str,
    body: PresignRequest,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_operator),
) -> PresignResponse:
    """Issue ``count`` presigned PUT URLs (2-4, 5-min TTL) (Req 2.1, 2.4).

    A count outside the 2-4 range raises ``InvalidPhotoCount`` -> 422; an unknown
    item raises ``ItemNotFound`` -> 404.
    """

    urls = services.item_service.request_photo_upload_urls(item_id, body.count)
    return PresignResponse(
        item_id=item_id,
        urls=[
            PresignedUrlModel(
                url=u.url, method=u.method, headers=dict(u.headers), expires_in=u.expires_in
            )
            for u in urls
        ],
    )


@router.post(
    "/items/{item_id}/grade",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GradeAcceptedResponse,
)
def enqueue_grade(
    item_id: str,
    body: GradeRequest,
    response: Response,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_operator),
) -> GradeAcceptedResponse:
    """Enqueue an async grading submission; return 202 + Idempotency-Key (Req 7.1, 7.2).

    The Idempotency-Key is derived from the item id and the photo-set hash unless
    an explicit override is supplied, then echoed in the ``Idempotency-Key``
    response header. An unknown item is rejected with 404 before enqueueing.
    """

    # Reject unknown items up front (raises ItemNotFound -> 404).
    services.item_service.get_item(item_id)

    idem_key = body.idempotency_key
    if not idem_key:
        # Derived here so the key is deterministic for the same item + photo set
        # (Requirement 7.2). Imported lazily to keep the module import graph flat.
        from rebridge_service.idempotency import derive_idempotency_key

        idem_key = derive_idempotency_key(item_id, body.photo_keys)

    services.queue.send_grading_message(
        GradingMessage(item_id=item_id, idem_key=idem_key, photo_keys=list(body.photo_keys))
    )

    response.headers["Idempotency-Key"] = idem_key
    return GradeAcceptedResponse(item_id=item_id, idempotency_key=idem_key)


@router.get("/items/{item_id}", response_model=ItemAggregateResponse)
def get_item(
    item_id: str,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_user),
) -> ItemAggregateResponse:
    """Return an Item's status plus exactly its persisted facets (Req 1.4).

    An unknown identifier raises ``ItemNotFound`` -> 404 (Requirement 1.5).
    """

    aggregate = services.item_service.get_item(item_id)
    return ItemAggregateResponse.from_aggregate(aggregate)


@router.post("/items/{item_id}/route", response_model=RouteDecisionResponse)
def route_item(
    item_id: str,
    body: RouteRequest | None = None,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_operator),
) -> RouteDecisionResponse:
    """Run the routing decision for a graded Item (Requirement 10).

    Persists the DECISION facet, emits a ROUTED lifecycle event identifying the
    Item and its disposition, and returns the decision with its unit-economics
    rationale (Requirement 10.7). An unknown item -> 404, an ungraded item ->
    409.
    """

    geohash5 = body.geohash5 if body is not None else None
    decision = services.routing.decide(item_id, geohash5=geohash5)
    services.eventing.emit_routed(item_id, decision.disposition)
    return RouteDecisionResponse(
        disposition=decision.disposition.value,
        price=decision.price,
        value=decision.value,
        cost=decision.cost,
        margin=decision.margin,
        rationale=decision.rationale,
    )
