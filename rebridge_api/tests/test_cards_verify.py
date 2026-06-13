"""API tests for the public Health Card verification route (task 17.4).

Exercises ``GET /cards/{card_id}/verify?sig=`` against the real
``HealthCardService`` backed by in-memory fakes (no AWS, no auth). Covers the
verified path with card contents (Req 12.1, 12.2), the tampered paths with no
contents (Req 12.3), the unknown-card 404, and -- crucially -- that the route is
reachable with no authentication header at all (Req 12.4, 16.3).
"""

from __future__ import annotations

from rebridge_data.models import GradeRecord

from tests.conftest import Harness


def _seed_grade(harness: Harness, item_id: str, *, grade="Good") -> None:
    harness.item_repo.put_grade(
        item_id,
        GradeRecord(grade=grade, confidence=0.9, summary="solid condition"),
    )


def _issue_card(harness: Harness, item_id: str = "item-1", *, grade="Good"):
    """Seed a grade and issue (render+sign+persist) a card; return the card."""
    _seed_grade(harness, item_id, grade=grade)
    return harness.card_service.issue_card(item_id)


# ---------------------------------------------------------------------------
# verified path (Req 12.1, 12.2)
# ---------------------------------------------------------------------------


def test_verify_with_correct_signature_returns_verified_with_contents(client, harness):
    """Req 12.1, 12.2: a matching signature yields verified=true + card contents."""
    card = _issue_card(harness)

    resp = client.get(f"/cards/{card.card_id}/verify", params={"sig": card.signature})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verified"] is True
    assert body["card"] is not None
    assert body["card"]["card_id"] == card.card_id
    assert body["card"]["item_id"] == card.item_id
    assert body["card"]["grade"] == "Good"
    assert body["card"]["signature"] == card.signature


def test_verify_without_sig_query_recomputes_and_verifies(client, harness):
    """Req 12.1: with no presented sig the stored signature is recomputed -> verified."""
    card = _issue_card(harness)

    resp = client.get(f"/cards/{card.card_id}/verify")

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["card"]["card_id"] == card.card_id


# ---------------------------------------------------------------------------
# tampered paths (Req 12.3) -- no contents surfaced
# ---------------------------------------------------------------------------


def test_verify_with_wrong_signature_returns_tampered_without_contents(client, harness):
    """Req 12.3: a presented signature that differs is reported tampered, no card."""
    card = _issue_card(harness)

    resp = client.get(
        f"/cards/{card.card_id}/verify", params={"sig": "deadbeef-not-the-signature"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is False
    assert body["card"] is None
    assert body["reason"]


def test_verify_after_grade_changed_returns_tampered(client, harness):
    """Req 12.3: mutating the underlying grade breaks the recomputed signature."""
    card = _issue_card(harness, grade="Good")

    # Tamper: change the persisted grade after the card was signed. The canonical
    # payload now recomputes to a different signature -> tampered.
    _seed_grade(harness, card.item_id, grade="Like New")

    resp = client.get(f"/cards/{card.card_id}/verify", params={"sig": card.signature})

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is False
    assert body["card"] is None


# ---------------------------------------------------------------------------
# not found
# ---------------------------------------------------------------------------


def test_verify_unknown_card_returns_404(client):
    """An unknown card id raises CardNotFound -> 404."""
    resp = client.get("/cards/does-not-exist/verify", params={"sig": "x"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# public access (Req 12.4, 16.3)
# ---------------------------------------------------------------------------


def test_verify_route_is_public_no_auth_header_required(client, harness):
    """Req 12.4, 16.3: the route succeeds with no Authorization header at all."""
    card = _issue_card(harness)

    # No headers whatsoever -- proving the route does not depend on get_current_user.
    resp = client.get(
        f"/cards/{card.card_id}/verify",
        params={"sig": card.signature},
        headers={},
    )

    assert resp.status_code == 200
    assert resp.json()["verified"] is True
