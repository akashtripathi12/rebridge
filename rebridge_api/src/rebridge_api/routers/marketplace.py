"""Marketplace route: query listed items (task 17.1).

Maps ``GET /marketplace`` to the item repository's marketplace query (GSI1/GSI2
in the deployed system; the in-memory fake filters by category and geo prefix).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from rebridge_api.dependencies import (
    CurrentUser,
    Services,
    get_current_user,
    get_services,
)
from rebridge_api.models import ListingFacetModel, MarketplaceResponse

router = APIRouter(tags=["marketplace"])


@router.get("/marketplace", response_model=MarketplaceResponse)
def query_marketplace(
    category: str = Query(description="Listing category to browse"),
    geo: str | None = Query(default=None, description="Optional geohash prefix"),
    limit: int = Query(default=50, ge=1, le=200),
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_user),
) -> MarketplaceResponse:
    """Query listings for marketplace browse (Requirements 3.3, 13)."""

    listings = services.item_repo.query_marketplace(category, geo, limit)
    return MarketplaceResponse(
        listings=[ListingFacetModel.from_record(rec) for rec in listings]
    )
