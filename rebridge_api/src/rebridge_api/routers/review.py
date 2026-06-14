"""Review-queue routes: list pending grades and confirm/override (G2).

Maps the human review console (Requirement 14) to the
:class:`rebridge_service.review_console_service.ReviewConsoleService`. Both
routes are private (depend on ``get_current_user``):

* ``GET /review/queue`` returns the prioritized queue (value x uncertainty
  descending) with server-computed priority tiers.
* ``POST /review/{item_id}`` applies a CONFIRM or OVERRIDE action and returns the
  updated Item aggregate (same shape as ``GET /items/{id}``), with status
  advanced to GRADED. An action on an item not in the queue raises
  ``NotPendingReview`` -> 409 (via the registered handler); an invalid override
  grade is rejected with 422.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from rebridge_data.models import GradeRecord

from rebridge_service.models import Grade

from rebridge_api.dependencies import (
    CurrentUser,
    Services,
    get_current_user,
    get_services,
)
from rebridge_api.models import (
    ItemAggregateResponse,
    ReviewActionRequest,
    ReviewQueueResponse,
)

router = APIRouter(tags=["review"])

# Valid grade labels accepted for an OVERRIDE action (Requirement 5.1).
_VALID_GRADES = {grade.value for grade in Grade}


def _require_review(services: Services) -> None:
    """Fail closed when no review service is wired into the container."""

    if services.review is None:
        raise HTTPException(
            status_code=503,
            detail="review console is not configured",
        )


@router.get("/review/queue", response_model=ReviewQueueResponse)
def get_review_queue(
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_user),
) -> ReviewQueueResponse:
    """Return the prioritized review queue with server-computed tiers (G2)."""

    _require_review(services)
    views = services.review.list_pending_view()
    return ReviewQueueResponse.from_views(views)


@router.post("/review/{item_id}", response_model=ItemAggregateResponse)
def review_action(
    item_id: str,
    body: ReviewActionRequest,
    services: Services = Depends(get_services),
    _user: CurrentUser = Depends(get_current_user),
) -> ItemAggregateResponse:
    """Confirm or override a pending grade; return the updated Item (G2).

    CONFIRM persists the existing grade as confirmed; OVERRIDE builds a grade
    from the item's current grade with the label replaced by ``override_grade``
    (carrying confidence/summary/defects/completeness). Both advance the item to
    GRADED. An action on a non-pending item -> 409; an invalid ``override_grade``
    -> 422.
    """

    _require_review(services)
    action = body.action

    if action == "CONFIRM":
        services.review.confirm(item_id)
    elif action == "OVERRIDE":
        new_grade = _build_override_grade(services, item_id, body.override_grade)
        services.review.override(item_id, new_grade)
    else:
        raise HTTPException(
            status_code=422,
            detail=f"action must be CONFIRM or OVERRIDE, got {action!r}",
        )

    # The service advances status to GRADED; emit the GRADED lifecycle event so
    # the human-review path matches the auto-grade path (Requirement 15.1), then
    # re-fetch the updated aggregate and return it (same shape as GET /items/{id}).
    services.eventing.emit_graded(item_id)
    aggregate = services.item_service.get_item(item_id)
    return ItemAggregateResponse.from_aggregate(aggregate)


def _build_override_grade(
    services: Services, item_id: str, override_grade: str | None
) -> GradeRecord:
    """Build the overriding GradeRecord, validating the new grade label (422)."""

    if override_grade not in _VALID_GRADES:
        raise HTTPException(
            status_code=422,
            detail=(
                "override_grade must be one of "
                f"{sorted(_VALID_GRADES)}, got {override_grade!r}"
            ),
        )

    current = services.item_repo.get_grade(item_id)
    if current is None:
        # Defensive: a pending item should carry a grade; fall back to neutral
        # carry-over fields so the override label is still applied.
        return GradeRecord(grade=override_grade, confidence=0.0, summary="")

    return GradeRecord(
        grade=override_grade,
        confidence=current.confidence,
        summary=current.summary,
        defects=list(current.defects),
        completeness=current.completeness,
    )
