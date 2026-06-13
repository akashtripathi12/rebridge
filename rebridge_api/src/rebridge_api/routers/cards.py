"""Public Product Health Card verification route (task 17.4).

Maps the single **public** endpoint ``GET /cards/{card_id}/verify?sig=`` to
:meth:`rebridge_service.health_card_service.HealthCardService.verify_card`. This
is the QR target stamped on a signed card, so the next buyer can scan and
confirm the record is authentic and untampered.

Unlike every other router, this handler deliberately does **not** depend on
``get_current_user``: Requirement 16.3 / 12.4 require the verification endpoint
to be reachable without a JWT. It depends only on ``get_services`` to obtain the
``HealthCardService`` and returns a verified result with the card contents on a
signature match (Requirement 12.2) or a tampered result with no contents on a
mismatch (Requirement 12.3). An unknown card id raises ``CardNotFound`` -> 404
via the handler registered in :mod:`rebridge_api.errors`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from rebridge_api.dependencies import Services, get_services
from rebridge_api.models import CardVerificationResponse

router = APIRouter(tags=["cards"])


@router.get("/cards/{card_id}/verify", response_model=CardVerificationResponse)
def verify_card(
    card_id: str,
    sig: str | None = Query(
        default=None, description="The signature presented on the public QR link"
    ),
    services: Services = Depends(get_services),
) -> CardVerificationResponse:
    """Publicly verify a Product Health Card (Requirements 12.1-12.4, 16.3).

    Recomputes the canonical HMAC-SHA256 signature and compares it against the
    stored signature. Returns ``verified=true`` with the rendered card contents
    on a match (Requirement 12.2) or ``verified=false`` with no contents when
    tampered (Requirement 12.3). This route requires no authentication
    (Requirements 12.4, 16.3). An unknown ``card_id`` yields a 404.
    """

    if services.card_service is None:  # pragma: no cover - wiring guard
        raise RuntimeError(
            "no card_service attached to the Services container; the composition "
            "root (or a test) must wire a HealthCardService to serve /cards verify"
        )

    result = services.card_service.verify_card(card_id, signature=sig)
    return CardVerificationResponse.from_result(result)
