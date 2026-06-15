"""Listing routes: CRUD plus simulated checkout (task 17.1).

Maps the listing slice of the API contract to ``ItemService`` listing CRUD and
the ``EventingService``. The path id is the Item id (the LISTING facet is keyed
to its Item). Creating a listing emits a LISTED event (Requirement 15.3); the
simulated ``buy`` transitions the Item to SOLD and emits SOLD with no payment
processing (Requirements 15.5, 18.4).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from rebridge_data.models import ItemStatus

from rebridge_api.dependencies import (
    CurrentUser,
    Services,
    get_current_operator,
    get_current_user,
    get_services,
)
from rebridge_api.models import (
    BuyResponse,
    CreateListingRequest,
    ListingResponse,
    UpdateListingRequest,
)
from rebridge_service.item_service import ListingNotFound

router = APIRouter(tags=["listings"])


@router.post(
    "/listings",
    status_code=status.HTTP_201_CREATED,
    response_model=ListingResponse,
)
def create_listing(
    body: CreateListingRequest,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_operator),
) -> ListingResponse:
    """Create the LISTING facet for a graded Item (Req 3.1, 3.5, 15.3).

    An ungraded Item is rejected with 409 (grade required); an unknown Item with
    404. On success the Item transitions to LISTED and a LISTED event is emitted.
    """

    kwargs: dict[str, Any] = {
        "category": body.category,
        "price": body.price,
        "geohash5": body.geohash5,
    }
    if body.status is not None:
        kwargs["status"] = body.status

    listing = services.item_service.create_listing(body.item_id, **kwargs)

    # Connect Engine B: on the LISTED transition, run demand matching so the
    # top-N buyers are notified, the Item is placed on the Second-Chance shelf,
    # and a MATCHED event is emitted (Requirements 13.5, 15.4). Skipped cleanly
    # if no matching engine is wired into the container.
    if services.matching is not None:
        match_result = services.matching.match(
            item_id=body.item_id,
            geo=listing.geohash5,
            category=listing.category,
        )
        services.eventing.emit_seller_notified(
            item_id=body.item_id,
            seller_id=_user.subject,
            message={"match_count": len(match_result.notified)}
        )

    return ListingResponse.from_record(listing)


@router.get("/listings/{item_id}", response_model=ListingResponse)
def get_listing(
    item_id: str,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_user),
) -> ListingResponse:
    """Return the LISTING facet for an Item (Requirement 3.3).

    Unknown Item -> 404; an existing Item with no listing -> 404 (no listing).
    """

    listing = services.item_service.get_listing(item_id)
    if listing is None:
        raise ListingNotFound(item_id)
    return ListingResponse.from_record(listing)


@router.put("/listings/{item_id}", response_model=ListingResponse)
def update_listing(
    item_id: str,
    body: UpdateListingRequest,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_operator),
) -> ListingResponse:
    """Apply a partial update to an existing listing (Requirement 3.2).

    Unknown Item -> 404; an Item with no listing -> 404.
    """

    listing = services.item_service.update_listing(item_id, body.to_patch())
    return ListingResponse.from_record(listing)


@router.delete("/listings/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_listing(
    item_id: str,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_operator),
) -> Response:
    """Remove the LISTING facet for an Item (Requirement 3.4). Unknown Item -> 404."""

    services.item_service.delete_listing(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/listings/{item_id}/buy", response_model=BuyResponse)
def buy_listing(
    item_id: str,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_user),
) -> BuyResponse:
    """Simulated checkout for a listed Item (Requirements 15.5, 18.4).

    Payments are simulated in v1: no payment is processed. The purchase requires
    an existing listing (unknown Item or no listing -> 404), transitions the Item
    to SOLD, and emits a SOLD lifecycle event identifying the Item.
    """

    try:
        services.item_service.buy_listing(item_id)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail=str(e))
    return BuyResponse(item_id=item_id, order_id=uuid.uuid4().hex)
