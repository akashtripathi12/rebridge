"""Exception handlers mapping service errors to HTTP responses (task 17.1).

The service layer raises framework-free exceptions; this module maps each to the
HTTP status code the API contract / Error Handling table in design.md requires,
so routers can call services directly and let raised errors surface as the
correct response without per-handler try/except blocks.

Mapping (design.md "Error Handling"):

==================================  ======  ====================  ============
Service exception                   Status  Meaning               Requirement
==================================  ======  ====================  ============
ItemNotFound                        404     unknown item id       1.5
MissingField                        422     required field absent 1.3
InvalidField                        422     bad field value       1.3
InvalidPhotoCount                   422     count outside 2-4     2.4
GradeRequired                       409     listing before grade  3.5
NotPendingReview                    409     review on non-pending 14.4
==================================  ======  ====================  ============

``ItemNotFound`` and ``GradeRequired`` exist in more than one service module
(e.g. ``item_service`` and ``routing_agent``); every variant is registered so
the mapping holds regardless of which collaborator raised it.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rebridge_service.health_card_service import (
    CardNotFound as CardNotFoundError,
    GradeRequired as CardGradeRequired,
)
from rebridge_service.item_service import (
    GradeRequired as ListingGradeRequired,
    InvalidField,
    InvalidPhotoCount,
    ItemNotFound as ItemServiceNotFound,
    ListingNotFound,
    MissingField,
)
from rebridge_service.review_console_service import NotPendingReview
from rebridge_service.routing_agent import (
    GradeRequired as RoutingGradeRequired,
    ItemNotFound as RoutingItemNotFound,
)

__all__ = ["register_exception_handlers"]


def _error(status_code: int, detail: str, field: str | None = None) -> JSONResponse:
    body: dict[str, object] = {"detail": detail}
    if field is not None:
        body["field"] = field
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """Register every service-exception -> HTTP-status handler on ``app``."""

    # 404 not-found (Requirement 1.5) -- both the item-service and routing variants.
    @app.exception_handler(ItemServiceNotFound)
    @app.exception_handler(RoutingItemNotFound)
    async def _item_not_found(_: Request, exc: Exception) -> JSONResponse:
        return _error(404, str(exc))

    @app.exception_handler(ListingNotFound)
    async def _listing_not_found(_: Request, exc: Exception) -> JSONResponse:
        return _error(404, str(exc))

    @app.exception_handler(CardNotFoundError)
    async def _card_not_found(_: Request, exc: Exception) -> JSONResponse:
        return _error(404, str(exc))

    # 422 validation errors (Requirements 1.3, 2.4).
    @app.exception_handler(MissingField)
    async def _missing_field(_: Request, exc: MissingField) -> JSONResponse:
        return _error(422, str(exc), field=exc.field)

    @app.exception_handler(InvalidField)
    async def _invalid_field(_: Request, exc: InvalidField) -> JSONResponse:
        return _error(422, str(exc), field=exc.field)

    @app.exception_handler(InvalidPhotoCount)
    async def _invalid_photo_count(_: Request, exc: InvalidPhotoCount) -> JSONResponse:
        return _error(422, str(exc), field="count")

    # 409 conflict: grade required before listing (3.5) and routing/card guards.
    @app.exception_handler(ListingGradeRequired)
    @app.exception_handler(CardGradeRequired)
    @app.exception_handler(RoutingGradeRequired)
    async def _grade_required(_: Request, exc: Exception) -> JSONResponse:
        return _error(409, str(exc))

    # 409 conflict: review action on a non-pending item (14.4).
    @app.exception_handler(NotPendingReview)
    async def _not_pending_review(_: Request, exc: Exception) -> JSONResponse:
        return _error(409, str(exc))
