"""Dependency-injection seam for the ReBridge API (task 17.1).

This module defines the *seam* the composition root (task 17.8, ``wiring.py``)
plugs concrete, boto3-backed services into, and that tests override with
in-memory-fake-backed services. It deliberately constructs **no** concrete
data-layer implementation itself -- it only declares the shape of the service
container and how a router obtains it at request time.

### The container

:class:`Services` is a plain dataclass holding the already-constructed
service-layer objects a router needs. The composition root builds one and
stores it on ``app.state.services`` (see :func:`set_services`); routers read it
through the :func:`get_services` FastAPI dependency. Because the container is a
single object on app state, a test can build one wired to the in-memory fakes
from ``rebridge_service/tests`` and attach it with :func:`set_services` (or via
``app.dependency_overrides[get_services]``) without touching any AWS code.

### The auth seam

:func:`get_current_user` is the authentication dependency for private routes
(Requirements 16.1, 16.2). It pulls the bearer token from the ``Authorization``
header and validates it with the :class:`~rebridge_api.auth.JwtVerifier`
attached to ``app.state.jwt_verifier`` (see :func:`set_verifier`), rejecting any
missing/invalid/expired token with HTTP 401. The verifier is injected rather
than constructed here, so the composition root (task 17.8) attaches a real
Cognito verifier while a test attaches one backed by a locally generated RSA
keypair / fake JWKS -- and the dependency itself stays overridable via
``app.dependency_overrides[get_current_user]``. Routers depend on it through
``Depends(get_current_user)`` so the implementation is transparent to them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from fastapi import status as http_status
from fastapi.exceptions import HTTPException

from rebridge_api.auth import AuthError, JwtVerifier

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cost at runtime
    from rebridge_data.interfaces import ItemRepository, QueueClient
    from rebridge_service.demand_matching_engine import DemandMatchingEngine
    from rebridge_service.eventing_service import EventingService
    from rebridge_service.health_card_service import HealthCardService
    from rebridge_service.item_service import ItemService
    from rebridge_service.review_console_service import ReviewConsoleService
    from rebridge_service.routing_agent import RoutingAgent

__all__ = [
    "Services",
    "set_services",
    "get_services",
    "set_verifier",
    "get_verifier",
    "CurrentUser",
    "get_current_user",
    "RequireUser",
]


@dataclass
class Services:
    """Container of service-layer collaborators a router depends on.

    The composition root constructs each member from concrete data-layer
    implementations; tests construct them from in-memory fakes. Members are kept
    as the already-built service objects (not factories) so a request handler
    simply reads and calls them.

    Attributes
    ----------
    item_service:
        Item creation/retrieval, presigned-URL issuance, and listing CRUD.
    routing:
        Routing_Agent producing/persisting the DECISION facet.
    eventing:
        Lifecycle event emission (LISTED on create-listing, SOLD on buy).
    queue:
        Grading work queue used to enqueue async grading submissions.
    item_repo:
        Item repository, used directly for the marketplace query and the
        simulated-checkout status transition.
    card_service:
        Health Card render/sign/verify, used by the public verify route
        (task 17.4); optional so the container can be built without it.
    matching:
        Demand_Matching_Engine (Engine B), used by the matches route
        (GET /items/{id}/matches, G1); optional so the container can be built
        without it.
    review:
        Review_Console_API service, used by the review routes (GET /review/queue
        and POST /review/{id}, G2); optional so the container can be built
        without it.
    """

    item_service: "ItemService"
    routing: "RoutingAgent"
    eventing: "EventingService"
    queue: "QueueClient"
    item_repo: "ItemRepository"
    card_service: "HealthCardService | None" = None
    matching: "DemandMatchingEngine | None" = None
    review: "ReviewConsoleService | None" = None


def set_services(app, services: Services) -> None:
    """Attach a :class:`Services` container to the FastAPI app state.

    The composition root and tests both call this; routers read it back through
    :func:`get_services`.
    """

    app.state.services = services


def get_services(request: Request) -> Services:
    """FastAPI dependency returning the request app's :class:`Services`.

    Raises a clear runtime error when no container has been attached, which
    signals a wiring mistake (the composition root or a test must call
    :func:`set_services` before serving requests).
    """

    services = getattr(request.app.state, "services", None)
    if services is None:
        raise RuntimeError(
            "no Services container attached to app.state; the composition root "
            "(or a test) must call set_services(app, services) before handling "
            "requests"
        )
    return services


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated principal for a private route.

    Populated from a validated Cognito JWT: ``subject`` is the token ``sub``
    claim and ``claims`` is the full set of verified claims.
    """

    subject: str
    claims: dict[str, object]


def set_verifier(app, verifier: JwtVerifier) -> None:
    """Attach a JWT verifier to the FastAPI app state.

    The composition root attaches a real Cognito verifier; tests attach one
    backed by a locally generated RSA keypair / fake JWKS. :func:`get_current_user`
    reads it back via :func:`get_verifier`.
    """

    app.state.jwt_verifier = verifier


def get_verifier(request: Request) -> JwtVerifier:
    """Return the app's configured :class:`~rebridge_api.auth.JwtVerifier`.

    A missing verifier is a wiring mistake; we fail *closed* (401) rather than
    serve private routes without authentication.
    """

    verifier = getattr(request.app.state, "jwt_verifier", None)
    if verifier is None:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="authentication is not configured",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verifier


def _bearer_token(request: Request) -> str:
    """Extract the bearer token from the ``Authorization`` header, or 401."""

    header = request.headers.get("Authorization")
    if not header:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be a Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def get_current_user(request: Request) -> CurrentUser:
    """Authenticate a private-route request via its Cognito JWT (Req 16.1, 16.2).

    Pulls the bearer token from the ``Authorization`` header and validates it
    with the app's :class:`~rebridge_api.auth.JwtVerifier`. Any missing, malformed,
    expired, wrong-issuer, wrong-audience, or otherwise invalid token is rejected
    with HTTP 401. Routers depend on this via ``Depends(get_current_user)``; tests
    may override it through ``app.dependency_overrides``.
    """

    verifier = get_verifier(request)
    token = _bearer_token(request)
    try:
        claims = verifier.verify(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    subject = str(claims.get("sub", ""))
    return CurrentUser(subject=subject, claims=dict(claims))


# Convenience alias for router signatures; keeps the auth seam visible in the
# handler signature while remaining easy to override.
RequireUser = Depends(get_current_user)
