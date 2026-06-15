"""FastAPI application factory for the ReBridge API (task 17.1).

:func:`create_app` builds the FastAPI ``app``, registers the service-exception
handlers, and includes the routers. It is intentionally a *factory* (not a
module-level singleton) so the separate adapters and wiring tasks can each build
and configure an app without import-time side effects:

* task 17.2 (Cognito JWT auth) overrides the ``get_current_user`` dependency seam;
* task 17.4 (public verify route) adds a router via ``app.include_router`` -- it
  passes its router through ``extra_routers`` or includes it after construction;
* task 17.5 (Lambda HTTP adapter) wraps the returned ``app`` with Mangum;
* task 17.8 (composition root) builds the :class:`~rebridge_api.dependencies.Services`
  container from concrete data-layer implementations and attaches it via
  ``set_services(app, services)`` (or by passing ``services=`` here).

A test builds a container wired to the in-memory fakes and either passes it as
``services=`` or attaches it with ``set_services`` after creating the app.
"""

from __future__ import annotations

from typing import Iterable

from fastapi import APIRouter, FastAPI

from rebridge_api.dependencies import Services, set_services
from rebridge_api.errors import register_exception_handlers
from rebridge_api.routers import cards, items, listings, marketplace, matches, notifications, review

__all__ = ["create_app"]


def create_app(
    services: Services | None = None,
    extra_routers: Iterable[APIRouter] | None = None,
) -> FastAPI:
    """Construct the ReBridge FastAPI application.

    Parameters
    ----------
    services:
        Optional pre-built :class:`Services` container to attach to app state.
        The composition root (task 17.8) or a test passes one wired to concrete
        implementations or in-memory fakes respectively. When omitted, the app
        is created without a container and one must be attached with
        :func:`rebridge_api.dependencies.set_services` before serving requests.
    extra_routers:
        Optional additional routers to include (e.g. the public verify router
        from task 17.4), so adapters can extend the app without editing this
        factory.
    """

    app = FastAPI(title="ReBridge API", version="0.1.0")

    register_exception_handlers(app)

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict[str, str]:
        """Public, unauthenticated liveness probe.

        Used by the Lambda HTTP adapter (task 17.5) as a no-dependency smoke
        route to confirm the ASGI app serves requests end-to-end.
        """

        return {"status": "ok"}

    app.include_router(items.router)
    app.include_router(listings.router)
    app.include_router(marketplace.router)
    # Demand matches (G1) and review queue (G2) routes.
    app.include_router(matches.router)
    app.include_router(review.router)
    app.include_router(notifications.router)
    # Public, unauthenticated Health Card verification route (task 17.4); always
    # served so the QR target /cards/{card_id}/verify resolves (Req 12.4, 16.3).
    app.include_router(cards.router)
    for extra in extra_routers or ():
        app.include_router(extra)

    if services is not None:
        set_services(app, services)

    return app
