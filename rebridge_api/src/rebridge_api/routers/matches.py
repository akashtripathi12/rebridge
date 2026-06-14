"""Matches route: ranked buyer matches for a graded Item (G1).

Maps ``GET /items/{item_id}/matches`` to the Demand_Matching_Engine (Engine B,
:class:`rebridge_service.demand_matching_engine.DemandMatchingEngine`). The route
is private (depends on ``get_current_user``). It returns ranked buyer matches for
a graded Item, an empty result for an item that is not yet graded, and a 404 for
an unknown item (the item-service lookup raises ``ItemNotFound`` -> 404 via the
registered handler).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from rebridge_data.models import ItemStatus

from rebridge_api.dependencies import (
    CurrentUser,
    Services,
    get_current_user,
    get_services,
)
from rebridge_api.models import MatchesResponse

router = APIRouter(tags=["matches"])


def _now_iso() -> str:
    """Return the current instant as an ISO-8601 string with a ``Z`` suffix."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/items/{item_id}/matches", response_model=MatchesResponse)
def get_matches(
    item_id: str,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_user),
) -> MatchesResponse:
    """Return ranked buyer matches for a graded Item (G1).

    A 404 is raised for an unknown item (via the item-service lookup). An item
    that exists but is not yet graded (no GRADE facet or status not GRADED)
    returns an empty result: ``matches: []``, ``match_count_within_5km: 0``,
    ``top_reason: null``. The matching engine ranks candidate buyers and the view
    is rendered with PII-free labels, distances, reasons, and intent tiers.
    """

    generated_at = _now_iso()

    # Unknown item -> ItemNotFound -> 404 via the registered handler.
    aggregate = services.item_service.get_item(item_id)

    is_graded = (
        aggregate.grade is not None and aggregate.meta.status == ItemStatus.GRADED
    )
    if not is_graded or services.matching is None:
        return MatchesResponse(
            item_id=item_id,
            generated_at=generated_at,
            matches=[],
            match_count_within_5km=0,
            top_reason=None,
        )

    geo = aggregate.listing.geohash5 if aggregate.listing is not None else ""
    category = aggregate.meta.category
    view = services.matching.matches_for(item_id, geo, category)
    return MatchesResponse.from_view(view, generated_at)
