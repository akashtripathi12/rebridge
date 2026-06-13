"""Unit tests for :class:`rebridge_service.health_card_service.HealthCardService`.

Covers task 11.1 behaviors against the in-memory :class:`FakeItemRepository`
and :class:`FakeCardSigner`:

* a card is rendered for a graded Item with the grade, annotated photos, a
  plain-language defect summary, a verification date, and a warranty stance,
  and is signed + persisted with a signature and QR target (Req 11.1, 11.2, 11.3),
* the canonical payload is exactly ``card_id | item_id | grade | graded_at``
  UTF-8 encoded (Req 11.2, 12.1),
* a sign/verify round-trip yields a verified result carrying the card contents
  (Req 12.1, 12.2),
* tampering with the grade, the stored signature, or the presented QR signature
  yields a tampered result with no contents surfaced (Req 12.3),
* a card cannot be issued before the Item is graded (Req 11.1).

Property-based coverage lives in the separate property-test tasks (11.2, 11.3).
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from rebridge_data.models import Defect as DataDefect
from rebridge_data.models import GradeRecord, ItemMeta, ItemStatus

from rebridge_service.health_card_service import (
    CANONICAL_SEPARATOR,
    CardNotFound,
    GradeRequired,
    HealthCardService,
    canonical_card_payload,
)
from rebridge_service.models import Grade

from tests.fakes import FakeCardSigner, FakeItemRepository


def _seed_graded_item(
    repo: FakeItemRepository,
    *,
    item_id: str = "item-1",
    grade: str = "Good",
    summary: str = "Solid working condition.",
    defects: list[DataDefect] | None = None,
) -> None:
    repo.put_item_meta(
        ItemMeta(
            item_id=item_id,
            status=ItemStatus.GRADED,
            category="electronics",
            age_months=12,
            context_source="manual",
            created_at="2024-01-01T00:00:00+00:00",
        )
    )
    repo.put_grade(
        item_id,
        GradeRecord(
            grade=grade,
            confidence=0.95,
            summary=summary,
            defects=defects or [],
        ),
    )


def _service(repo: FakeItemRepository, signer: FakeCardSigner) -> HealthCardService:
    return HealthCardService(
        signer=signer,
        item_repo=repo,
        id_factory=lambda: "card-1",
        clock=lambda: __import__("datetime").datetime(
            2024, 6, 1, tzinfo=__import__("datetime").timezone.utc
        ),
    )


# -- rendering + signing + persistence (11.1, 11.2, 11.3) -----------------
def test_issue_card_renders_all_required_contents():
    repo = FakeItemRepository()
    _seed_graded_item(
        repo,
        defects=[DataDefect(location="top-left corner", severity="minor scuff")],
    )
    svc = _service(repo, FakeCardSigner())

    card = svc.issue_card("item-1", annotated_photo_keys=["photos/a.jpg", "photos/b.jpg"])

    assert card.grade is Grade.GOOD
    assert card.annotated_photo_keys == ["photos/a.jpg", "photos/b.jpg"]
    assert card.graded_at == "2024-06-01T00:00:00+00:00"  # verification date
    assert card.warranty_stance  # a warranty stance is rendered
    # Plain-language defect summary mentions the condition and the defect.
    assert "Solid working condition." in card.defect_summary
    assert "minor scuff at top-left corner" in card.defect_summary
    assert card.signature  # signed
    assert card.qr_target == f"/cards/card-1/verify?sig={card.signature}"


def test_issue_card_persists_card_facet_with_signature_and_qr_target():
    repo = FakeItemRepository()
    _seed_graded_item(repo)
    svc = _service(repo, FakeCardSigner())

    card = svc.issue_card("item-1")

    stored = repo.get_card("card-1")
    assert stored is not None
    assert stored.item_id == "item-1"
    assert stored.signature == card.signature
    assert stored.qr_target == card.qr_target
    assert stored.graded_at == card.graded_at
    assert stored.warranty_stance == card.warranty_stance


def test_no_defects_renders_no_defects_statement():
    repo = FakeItemRepository()
    _seed_graded_item(repo, defects=[])
    svc = _service(repo, FakeCardSigner())

    card = svc.issue_card("item-1")
    assert "No defects observed." in card.defect_summary


def test_warranty_stance_can_be_overridden():
    repo = FakeItemRepository()
    _seed_graded_item(repo)
    svc = _service(repo, FakeCardSigner())

    card = svc.issue_card("item-1", warranty_stance="90-day extended")
    assert card.warranty_stance == "90-day extended"


def test_issue_card_requires_a_persisted_grade():
    repo = FakeItemRepository()
    repo.put_item_meta(
        ItemMeta(
            item_id="ungraded",
            status=ItemStatus.CREATED,
            category="toys",
            age_months=2,
            context_source="manual",
            created_at="2024-01-01T00:00:00+00:00",
        )
    )
    svc = _service(repo, FakeCardSigner())

    with pytest.raises(GradeRequired) as exc:
        svc.issue_card("ungraded")
    assert exc.value.item_id == "ungraded"


# -- canonical payload (11.2, 12.1) ---------------------------------------
def test_canonical_payload_is_exactly_pipe_joined_utf8():
    payload = canonical_card_payload("card-1", "item-1", Grade.GOOD, "2024-06-01T00:00:00+00:00")
    assert payload == b"card-1 | item-1 | Good | 2024-06-01T00:00:00+00:00"
    assert CANONICAL_SEPARATOR == " | "


def test_signature_is_hmac_sha256_over_canonical_payload():
    repo = FakeItemRepository()
    _seed_graded_item(repo, grade="Good")
    signer = FakeCardSigner(key=b"unit-test-key")
    svc = _service(repo, signer)

    card = svc.issue_card("item-1")

    expected = hmac.new(
        b"unit-test-key",
        b"card-1 | item-1 | Good | 2024-06-01T00:00:00+00:00",
        hashlib.sha256,
    ).hexdigest()
    assert card.signature == expected


# -- sign/verify round-trip (12.1, 12.2) ----------------------------------
def test_verify_round_trip_returns_verified_with_contents():
    repo = FakeItemRepository()
    _seed_graded_item(repo, defects=[DataDefect(location="back", severity="light wear")])
    svc = _service(repo, FakeCardSigner())

    issued = svc.issue_card("item-1", annotated_photo_keys=["photos/a.jpg"])
    result = svc.verify_card("card-1")

    assert result.verified is True
    assert result.card is not None
    assert result.card.card_id == "card-1"
    assert result.card.grade is Grade.GOOD
    assert result.card.signature == issued.signature
    assert result.card.annotated_photo_keys == ["photos/a.jpg"]
    assert "light wear at back" in result.card.defect_summary


def test_verify_with_matching_presented_signature_is_verified():
    repo = FakeItemRepository()
    _seed_graded_item(repo)
    svc = _service(repo, FakeCardSigner())

    issued = svc.issue_card("item-1")
    result = svc.verify_card("card-1", signature=issued.signature)
    assert result.verified is True
    assert result.card is not None


def test_verify_unknown_card_raises_not_found():
    repo = FakeItemRepository()
    svc = _service(repo, FakeCardSigner())
    with pytest.raises(CardNotFound):
        svc.verify_card("nope")


# -- tamper detection (12.3) ----------------------------------------------
def test_tampering_with_grade_is_detected_as_tampered():
    repo = FakeItemRepository()
    _seed_graded_item(repo, grade="Good")
    svc = _service(repo, FakeCardSigner())
    svc.issue_card("item-1")

    # Tamper: change the persisted grade so the recomputed payload differs.
    repo.put_grade(
        "item-1",
        GradeRecord(grade="Like New", confidence=0.95, summary="Solid working condition."),
    )

    result = svc.verify_card("card-1")
    assert result.verified is False
    assert result.card is None  # tampered contents are not surfaced


def test_tampering_with_stored_signature_is_detected():
    repo = FakeItemRepository()
    _seed_graded_item(repo)
    svc = _service(repo, FakeCardSigner())
    svc.issue_card("item-1")

    stored = repo.get_card("card-1")
    stored.signature = "deadbeef"
    repo.put_card("item-1", stored)

    result = svc.verify_card("card-1")
    assert result.verified is False
    assert result.card is None


def test_mismatched_presented_signature_is_detected_as_tampered():
    repo = FakeItemRepository()
    _seed_graded_item(repo)
    svc = _service(repo, FakeCardSigner())
    svc.issue_card("item-1")

    result = svc.verify_card("card-1", signature="0" * 64)
    assert result.verified is False
    assert result.card is None
