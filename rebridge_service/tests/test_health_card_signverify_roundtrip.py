"""Property-based test for the Health Card sign/verify round-trip.

# Feature: rebridge-backend, Property 19: Health Card sign/verify round-trip

Property 19 (design.md): *For any* graded Item, the rendered
Product_Health_Card SHALL contain the grade, annotated photos, defect summary,
verification date, and warranty stance, and recomputing its HMAC-SHA256
signature over the canonical payload SHALL match the stored signature, yielding
a verified result with the card contents.

**Validates: Requirements 11.1, 11.2, 11.3, 12.1, 12.2**

The strategy seeds a single graded Item into a fresh
:class:`FakeItemRepository` with a varied grade (one of the five allowed
values), item identifier, plain-language summary, defect list, and annotated
photo-key set, then issues a card and immediately verifies it. The test asserts
the render-content invariant (grade, annotated photos, defect summary,
verification date, warranty stance are all present) and the round-trip
invariant (verification returns ``verified=True`` and surfaces card contents
that match exactly what was issued, including the HMAC signature).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import Defect as DataDefect
from rebridge_data.models import GradeRecord, ItemMeta, ItemStatus

from rebridge_service.health_card_service import HealthCardService
from rebridge_service.models import Grade

from tests.fakes import FakeCardSigner, FakeItemRepository

# Minimum iterations per the spec's property-testing guideline (>= 100).
_ITERATIONS = 200

# Text used for free-form fields. A modest alphabet keeps generated values
# readable while still exercising whitespace and punctuation in summaries.
_text = st.text(
    alphabet=st.characters(
        min_codepoint=32, max_codepoint=126, blacklist_characters="\x7f"
    ),
    max_size=40,
)
_nonempty_text = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=24,
)

# Any of the five allowed grades (Requirement 5.1 / 11.1).
_grades = st.sampled_from(list(Grade))


@st.composite
def _defects(draw: st.DrawFn) -> list[DataDefect]:
    """Generate a (possibly empty) list of observed defects."""

    return draw(
        st.lists(
            st.builds(DataDefect, location=_nonempty_text, severity=_nonempty_text),
            max_size=4,
        )
    )


@st.composite
def graded_card_cases(draw: st.DrawFn) -> dict:
    """Generate a fully-specified graded Item plus card issuance inputs."""

    return {
        "item_id": draw(_nonempty_text),
        "grade": draw(_grades),
        "summary": draw(_text),
        "defects": draw(_defects()),
        "photo_keys": draw(st.lists(_nonempty_text, max_size=4)),
        "graded_at": draw(_nonempty_text),
        "card_id": draw(_nonempty_text),
    }


def _seed_and_service(case: dict) -> HealthCardService:
    repo = FakeItemRepository()
    repo.put_item_meta(
        ItemMeta(
            item_id=case["item_id"],
            status=ItemStatus.GRADED,
            category="electronics",
            age_months=12,
            context_source="manual",
            created_at="2024-01-01T00:00:00+00:00",
        )
    )
    repo.put_grade(
        case["item_id"],
        GradeRecord(
            grade=case["grade"].value,
            confidence=0.95,
            summary=case["summary"],
            defects=list(case["defects"]),
        ),
    )
    return HealthCardService(signer=FakeCardSigner(), item_repo=repo)


@settings(max_examples=_ITERATIONS)
@given(graded_card_cases())
def test_sign_verify_round_trip(case: dict) -> None:
    """Issuing then verifying a card returns verified=True with matching contents."""

    svc = _seed_and_service(case)

    issued = svc.issue_card(
        case["item_id"],
        annotated_photo_keys=case["photo_keys"],
        graded_at=case["graded_at"],
        card_id=case["card_id"],
    )

    # Render-content invariant (Req 11.1): grade, annotated photos, defect
    # summary, verification date, and warranty stance are all present.
    assert issued.grade is case["grade"]
    assert issued.annotated_photo_keys == case["photo_keys"]
    assert issued.defect_summary != ""
    assert issued.graded_at == case["graded_at"]  # verification date
    assert issued.warranty_stance != ""
    # Signed and persisted with a signature + QR target (Req 11.2, 11.3).
    assert issued.signature != ""
    assert issued.qr_target.endswith(f"sig={issued.signature}")

    # Round-trip invariant (Req 12.1, 12.2): recompute-and-compare verifies and
    # surfaces the card contents.
    result = svc.verify_card(case["card_id"])

    assert result.verified is True
    assert result.card is not None
    verified = result.card
    assert verified.card_id == issued.card_id
    assert verified.item_id == issued.item_id
    assert verified.grade is issued.grade
    assert verified.graded_at == issued.graded_at
    assert verified.defect_summary == issued.defect_summary
    assert verified.warranty_stance == issued.warranty_stance
    assert verified.annotated_photo_keys == issued.annotated_photo_keys
    assert verified.signature == issued.signature
    assert verified.qr_target == issued.qr_target
