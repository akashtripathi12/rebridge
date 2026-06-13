"""API-layer smoke tests (task 17.9).

A small, focused smoke suite that drives the wired FastAPI app through
``TestClient`` against the in-memory fakes from ``conftest.py`` (no AWS), plus a
single configuration-default check. These intentionally re-assert the most
load-bearing API contracts as a fast, self-contained sanity gate:

* an unknown item id yields a 404 not-found (Req 1.5);
* the public Health Card verify route is reachable with **no** auth header at all
  (Req 16.3);
* creating a listing for an ungraded item is rejected 409 grade-required
  (Req 3.5);
* the ``ConfidenceGate`` threshold defaults to 0.80 from an empty config
  (Req 6.3).

The route checks reuse the shared ``client``/``harness`` fixtures so they run
against real service-layer logic; the config check builds ``Settings`` from an
empty mapping and a ``ConfidenceGate`` from it directly.
"""

from __future__ import annotations

import pytest

from rebridge_api import Settings
from rebridge_service.confidence_gate import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
)
from rebridge_data.models import GradeRecord


# ---------------------------------------------------------------------------
# Req 1.5 -- unknown item id -> 404
# ---------------------------------------------------------------------------


def test_get_unknown_item_returns_404(client):
    """Req 1.5: retrieving an item that does not exist yields a 404."""
    resp = client.get("/items/no-such-item")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Req 16.3 -- public verify route reachable without authentication
# ---------------------------------------------------------------------------


def test_public_verify_route_reachable_without_auth_header(client, harness):
    """Req 16.3: GET /cards/{id}/verify resolves with no Authorization header.

    The harness does install a stub auth override, but the public verify route
    must not depend on it: we send an explicitly empty header set and still get
    a successful, verified response.
    """
    harness.item_repo.put_grade(
        "item-smoke",
        GradeRecord(grade="Good", confidence=0.9, summary="solid condition"),
    )
    card = harness.card_service.issue_card("item-smoke")

    resp = client.get(
        f"/cards/{card.card_id}/verify",
        params={"sig": card.signature},
        headers={},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["verified"] is True


# ---------------------------------------------------------------------------
# Req 3.5 -- listing an ungraded item -> 409 grade-required
# ---------------------------------------------------------------------------


def test_create_listing_for_ungraded_item_returns_409(client):
    """Req 3.5: creating a listing for an item with no grade is rejected 409."""
    created = client.post(
        "/items",
        json={"context_source": "manual", "category": "electronics", "age_months": 6},
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["item_id"]

    resp = client.post(
        "/listings",
        json={
            "item_id": item_id,
            "category": "electronics",
            "price": "75.00",
            "geohash5": "9q8yy",
        },
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Req 6.3 -- ConfidenceGate threshold defaults to 0.80
# ---------------------------------------------------------------------------


def test_confidence_gate_threshold_defaults_to_080_from_empty_config():
    """Req 6.3: an empty config gives a 0.80 default confidence threshold."""
    settings = Settings.from_env({})
    assert settings.confidence_threshold == pytest.approx(0.80)
    assert settings.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD

    gate = ConfidenceGate(threshold=settings.confidence_threshold)
    assert gate.threshold == pytest.approx(0.80)
