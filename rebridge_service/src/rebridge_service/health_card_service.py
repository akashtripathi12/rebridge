"""HealthCardService: render, sign, persist, and verify Product Health Cards.

This is the service-layer business logic for the Product Health Card
(design.md -> "Components and Interfaces -> Service Layer -> HealthCardService";
Requirements 11 and 12). It is programmed entirely against the abstract
:mod:`rebridge_data.interfaces` (``CardSigner`` and ``ItemRepository``) and
never imports boto3 or any web framework.

Responsibilities implemented here (task 11.1):

* **Render** a :class:`~rebridge_service.models.HealthCard` for an Item that has
  a persisted grade, containing the grade, annotated photo references, a
  plain-language defect summary, a verification date, and a warranty stance
  (Requirement 11.1).
* **Sign** the canonical payload with HMAC-SHA256 via the injected
  :class:`~rebridge_data.interfaces.CardSigner` (Requirement 11.2) and
  **persist** the CARD facet with the signature and a QR target reference
  (Requirement 11.3).
* **Verify** a card by recompute-and-compare, returning a *verified* result
  carrying the card contents when the recomputed signature matches the stored
  signature (Requirements 12.1, 12.2), or a *tampered* result when it does not
  (Requirement 12.3).

### Canonical signing payload

The HMAC is computed over the canonical concatenation

    card_id | item_id | grade | graded_at

(design.md: "The HMAC signing payload is the canonical concatenation
``card_id | item_id | grade | graded_at``"). The exact byte encoding is the
four fields joined by the literal separator ``" | "`` (space-pipe-space) and
encoded as UTF-8. ``grade`` is the human-readable grade label (the value of the
:class:`~rebridge_service.models.Grade` enum, e.g. ``"Good"``), which is exactly
what is persisted on the GRADE facet, so signing at issuance time and recompute
at verification time produce identical bytes. :func:`canonical_card_payload` is
the single source of truth for this encoding and is used by both signing and
verification so the two can never drift apart.

The grade is *not* stored on the CARD facet; verification recomputes it from the
persisted GRADE facet for the card's Item, which is what makes the signature
tamper-evident against any change to the underlying grade.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from rebridge_data.interfaces import CardSigner, ItemRepository
from rebridge_data.models import CardRecord, GradeRecord

from rebridge_service.models import Grade, HealthCard

__all__ = [
    "CANONICAL_SEPARATOR",
    "canonical_card_payload",
    "HealthCardError",
    "GradeRequired",
    "CardNotFound",
    "VerificationResult",
    "HealthCardService",
]

# The literal separator joining the four canonical payload fields. Signing and
# verification both go through canonical_card_payload, so this constant is the
# single point of definition for the wire encoding.
CANONICAL_SEPARATOR = " | "

# Default warranty stance rendered per grade. Like-new / very-good items carry
# the longer stance; good / acceptable a shorter one; an unsellable item carries
# no warranty. Callers may override the stance per card at issuance time.
_DEFAULT_WARRANTY_BY_GRADE: dict[Grade, str] = {
    Grade.LIKE_NEW: "30-day returns",
    Grade.VERY_GOOD: "30-day returns",
    Grade.GOOD: "14-day returns",
    Grade.ACCEPTABLE: "7-day returns",
    Grade.UNSELLABLE: "no warranty (not resellable)",
}


def canonical_card_payload(
    card_id: str,
    item_id: str,
    grade: Grade | str,
    graded_at: str,
) -> bytes:
    """Return the canonical signing payload bytes for a health card.

    The payload is the four fields ``card_id``, ``item_id``, ``grade``, and
    ``graded_at`` joined by :data:`CANONICAL_SEPARATOR` and UTF-8 encoded
    (Requirements 11.2, 12.1). ``grade`` may be a :class:`Grade` enum member or
    its already-resolved label string; either way the human-readable label is
    used so issuance and verification agree byte-for-byte.
    """

    grade_label = grade.value if isinstance(grade, Grade) else str(grade)
    return CANONICAL_SEPARATOR.join(
        [card_id, item_id, grade_label, graded_at]
    ).encode("utf-8")


class HealthCardError(Exception):
    """Base class for errors raised by :class:`HealthCardService`."""


class GradeRequired(HealthCardError):
    """A card was requested for an Item that has no persisted grade (Req 11.1)."""

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"cannot render a health card before the item is graded: {item_id}")


class CardNotFound(HealthCardError):
    """No CARD facet exists for the requested card identifier."""

    def __init__(self, card_id: str) -> None:
        self.card_id = card_id
        super().__init__(f"health card not found: {card_id}")


@dataclass
class VerificationResult:
    """The outcome of a public card verification (Requirements 12.2, 12.3).

    ``verified`` is True when the recomputed signature matches the stored
    signature; in that case ``card`` carries the rendered card contents
    (Requirement 12.2). When ``verified`` is False the card is *tampered* and
    ``card`` is ``None`` so altered contents are never surfaced as authentic
    (Requirement 12.3). ``reason`` is a short human-readable explanation.
    """

    verified: bool
    card: HealthCard | None = None
    reason: str = ""


@dataclass
class HealthCardService:
    """Render, sign, persist, and verify Product Health Cards (Req 11, 12).

    Collaborators are injected as abstract interfaces (the one-way dependency
    ``service -> data``). ``id_factory`` and ``clock`` are injectable to keep
    issuance deterministic under test. ``verify_path_prefix`` controls the QR
    target shape; it defaults to the public verification route ``/cards``.
    """

    signer: CardSigner
    item_repo: ItemRepository
    verify_path_prefix: str = "/cards"
    id_factory: Callable[[], str] = lambda: uuid.uuid4().hex
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    # -- issuance ----------------------------------------------------------
    def issue_card(
        self,
        item_id: str,
        *,
        annotated_photo_keys: list[str] | None = None,
        warranty_stance: str | None = None,
        graded_at: str | None = None,
        card_id: str | None = None,
    ) -> HealthCard:
        """Render, sign, and persist a Product Health Card for a graded Item.

        Requires a persisted GRADE facet for ``item_id`` (Requirement 11.1);
        raises :class:`GradeRequired` otherwise. Signs the canonical payload via
        the injected :class:`CardSigner` (Requirement 11.2) and persists the
        CARD facet with the signature and a QR target reference
        (Requirement 11.3). Returns the rendered :class:`HealthCard`.
        """

        grade_record = self.item_repo.get_grade(item_id)
        if grade_record is None:
            raise GradeRequired(item_id)

        grade = self._grade_of(grade_record)
        resolved_card_id = card_id or self.id_factory()
        # The verification date stamped on the card. Defaults to "now"; callers
        # may pass the actual grade time to stamp it instead.
        resolved_graded_at = graded_at or self.clock().isoformat()
        photos = list(annotated_photo_keys or [])
        stance = warranty_stance or self._default_warranty(grade)
        defect_summary = self._render_defect_summary(grade_record)

        payload = canonical_card_payload(
            resolved_card_id, item_id, grade, resolved_graded_at
        )
        signature = self.signer.sign(payload)
        qr_target = self._qr_target(resolved_card_id, signature)

        record = CardRecord(
            card_id=resolved_card_id,
            item_id=item_id,
            signature=signature,
            qr_target=qr_target,
            graded_at=resolved_graded_at,
            warranty_stance=stance,
            annotated_photo_keys=photos,
        )
        self.item_repo.put_card(item_id, record)

        return HealthCard(
            card_id=resolved_card_id,
            item_id=item_id,
            grade=grade,
            graded_at=resolved_graded_at,
            defect_summary=defect_summary,
            warranty_stance=stance,
            annotated_photo_keys=photos,
            signature=signature,
            qr_target=qr_target,
        )

    # -- verification ------------------------------------------------------
    def verify_card(
        self,
        card_id: str,
        signature: str | None = None,
    ) -> VerificationResult:
        """Verify a card by recompute-and-compare (Requirements 12.1-12.3).

        Looks up the persisted CARD facet and the GRADE facet of its Item,
        recomputes the canonical HMAC-SHA256 signature, and compares it against
        the stored signature (Requirement 12.1). Returns a verified result with
        the rendered card contents on a match (Requirement 12.2) or a tampered
        result on a mismatch (Requirement 12.3).

        When ``signature`` is supplied (the ``sig`` presented on the public QR
        link) it must also equal the stored signature; a presented signature
        that differs is reported as tampered without recomputation surfacing the
        contents.
        """

        card = self.item_repo.get_card(card_id)
        if card is None:
            raise CardNotFound(card_id)

        grade_record = self.item_repo.get_grade(card.item_id)
        if grade_record is None:
            # Without the GRADE facet the canonical payload cannot be
            # recomputed, so the card cannot be authenticated -> tampered.
            return VerificationResult(
                verified=False,
                card=None,
                reason="grade record unavailable; cannot recompute signature",
            )

        # A presented QR signature must match the stored signature exactly.
        if signature is not None and not _constant_time_eq(signature, card.signature):
            return VerificationResult(
                verified=False,
                card=None,
                reason="presented signature does not match the stored signature",
            )

        payload = canonical_card_payload(
            card.card_id, card.item_id, grade_record.grade, card.graded_at
        )
        if not self.signer.verify(payload, card.signature):
            return VerificationResult(
                verified=False,
                card=None,
                reason="recomputed signature does not match the stored signature",
            )

        return VerificationResult(
            verified=True,
            card=self._render_from_records(card, grade_record),
            reason="signature matches",
        )

    # -- rendering helpers -------------------------------------------------
    def _render_from_records(
        self, card: CardRecord, grade_record: GradeRecord
    ) -> HealthCard:
        """Build the rendered :class:`HealthCard` from persisted records."""

        return HealthCard(
            card_id=card.card_id,
            item_id=card.item_id,
            grade=self._grade_of(grade_record),
            graded_at=card.graded_at,
            defect_summary=self._render_defect_summary(grade_record),
            warranty_stance=card.warranty_stance,
            annotated_photo_keys=list(card.annotated_photo_keys),
            signature=card.signature,
            qr_target=card.qr_target,
        )

    @staticmethod
    def _grade_of(grade_record: GradeRecord) -> Grade:
        """Resolve the persisted grade label string to the domain Grade enum."""

        try:
            return Grade(grade_record.grade)
        except ValueError as exc:
            raise HealthCardError(
                f"persisted grade label is not a recognized Grade: {grade_record.grade!r}"
            ) from exc

    @staticmethod
    def _render_defect_summary(grade_record: GradeRecord) -> str:
        """Compose a plain-language defect summary (Requirement 11.1).

        Starts from the grade's plain-language condition summary and appends an
        enumeration of observed defects (location + severity), or a clear
        "no defects" statement when none were observed.
        """

        base = (grade_record.summary or "").strip()
        if grade_record.defects:
            phrases = [
                f"{defect.severity} at {defect.location}"
                for defect in grade_record.defects
            ]
            defects_sentence = "Observed defects: " + "; ".join(phrases) + "."
        else:
            defects_sentence = "No defects observed."
        return f"{base} {defects_sentence}".strip() if base else defects_sentence

    @staticmethod
    def _default_warranty(grade: Grade) -> str:
        """Return the default warranty stance for a grade."""

        return _DEFAULT_WARRANTY_BY_GRADE.get(grade, "no warranty")

    def _qr_target(self, card_id: str, signature: str) -> str:
        """Build the public QR verification target (Requirement 11.3)."""

        prefix = self.verify_path_prefix.rstrip("/")
        return f"{prefix}/{card_id}/verify?sig={signature}"


def _constant_time_eq(a: str, b: str) -> bool:
    """Constant-time string comparison for signature equality checks."""

    import hmac as _hmac

    return _hmac.compare_digest(a, b)
