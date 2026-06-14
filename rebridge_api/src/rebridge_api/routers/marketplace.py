"""Marketplace route: query listed items, enriched for buyer browse (G3/G4/G9).

Maps ``GET /marketplace`` to the item repository's marketplace query (GSI1/GSI2
in the deployed system; the in-memory fake filters by category and geo prefix)
and enriches each listing with the buyer-facing fields the frontend needs:
grade, distance, demo MRP (``price_new``), health-card id, title, thumb glyph,
and a stable ``listing_id`` (G3 + G4). The grade and card are joined per listing
via ``item_repo.get_item`` (N+1 is acceptable for the demo at limit <= 200).

G9: a ``category`` of ``"all"`` is accepted and returns listings across every
known category rather than requiring a specific one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from rebridge_data.geohash import geohash_distance_km, seeded_distance_km
from rebridge_data.models import ListingRecord

from rebridge_api.dependencies import (
    CurrentUser,
    Services,
    get_current_user,
    get_services,
)
from rebridge_api.models import MarketListingModel, MarketplaceResponse

router = APIRouter(tags=["marketplace"])

# G9: the sentinel category that means "every category" (the frontend "Nearby"
# default chip). When requested, listings are gathered across the known demo
# categories and merged.
ALL_CATEGORY = "all"

from rebridge_service.models import KNOWN_CATEGORIES


@router.get("/marketplace", response_model=MarketplaceResponse)
def query_marketplace(
    category: str = Query(description="Listing category to browse ('all' for every category)"),
    geo: str | None = Query(default=None, description="Optional geohash prefix"),
    limit: int = Query(default=50, ge=1, le=200),
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_user),
) -> MarketplaceResponse:
    """Query listings for marketplace browse, enriched for buyers (Req 3.3, 13)."""

    records = _query_records(services, category, geo, limit)

    item_ids = [rec.item_id for rec in records]
    aggregates = services.item_repo.batch_get_items(item_ids)
    agg_by_id = {agg.meta.item_id: agg for agg in aggregates}

    listings: list[MarketListingModel] = []
    for rec in records:
        agg = agg_by_id.get(rec.item_id)
        grade = agg.grade.grade if agg and agg.grade else None
        health_card_id = agg.card.card_id if agg and agg.card else None
        
        distance_km = (
            geohash_distance_km(geo, rec.geohash5)
            if geo
            else seeded_distance_km(rec.item_id)
        )
        listings.append(
            MarketListingModel.from_record(
                rec,
                grade=grade,
                health_card_id=health_card_id,
                distance_km=distance_km,
            )
        )

    return MarketplaceResponse(listings=listings)


def _query_records(
    services: Services, category: str, geo: str | None, limit: int
) -> list[ListingRecord]:
    """Return listing records for the request, handling the ``all`` category (G9)."""

    if category != ALL_CATEGORY:
        return services.item_repo.query_marketplace(category, geo, limit)

    # G9: gather across known categories and merge, preserving order and
    # de-duplicating by item_id, then bound by limit.
    seen: set[str] = set()
    merged: list[ListingRecord] = []
    for known in KNOWN_CATEGORIES:
        for rec in services.item_repo.query_marketplace(known, geo, limit):
            if rec.item_id in seen:
                continue
            seen.add(rec.item_id)
            merged.append(rec)
            if len(merged) >= limit:
                return merged
    return merged



