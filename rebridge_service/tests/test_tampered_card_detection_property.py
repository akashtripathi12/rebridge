"""Property-based test for tampered Product Health Card detection.

# Feature: rebridge-backend, Property 20: Tampered card detection

Property 20 (design.md): *For any* signed Product_Health_Card and any
non-identity mutation of a signed field, public verification SHALL return a
tampered result.

**Validates: Requirements 12.3**

The HMAC is computed over the canonical payload ``card_id | item_id | grade |
graded_at`` (see :mod:`rebridge_service.health_card_service`). After a card is
issued and signed, this test applies a single *non-identity* mutation drawn from
the realistic tamper surface and asserts that
:meth:`HealthCardService.verify_card` reports a tampered result
(``verified is False``) and surfaces no card contents (``card is None``), so
altered records are never presented as authentic.

Tamper vectors generated (each guaranteed to actually change the value):

* ``grade`` — the persisted GRADE facet is rewritten to a *different* grade, so
  the signature recomputed at verification time no longer matches the one signed
  at issuance;
* ``graded_at`` — the verification date stored on the CARD facet is rewritten to
  a different timestamp, again diverging the recomputed payload;
* ``stored_sig`` — the signature persisted on the CARD facet is mutated;
* ``presented_sig`` — the ``sig`` presented on the public QR link differs from
  the stored signature.

Generators are constrained to the valid issuance input space (a real grade, a
real signing key) and the mutations are constrained to be non-identity, so every
example is a genuine tamper that MUST be detected.
"""

from __future__ import annotations

import string

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from rebridge_data.models import Defect as DataDefect
from rebridge_data.models import GradeRecord

from rebridge_service.health_card_service import HealthCardService
from rebridge_service.models import Grade

from tests.fakes import FakeCardSigner, FakeItemRepository

# Minimum iterations per the spec's property-testing guideline (>= 100).
_ITERATIONS = 200

# URL/identifier-safe, non-empty identifiers for card and item ids.
_ident = st.text(
    alphabet=string.ascii_letters + string.digits + "-_",
    min_size=1,
    max_size=24,
)

# Verification-date timestamps drawn as ISO-8601 strings.
_graded_at = st.datetimes().map(lambda dt: dt.isoformat())

# A non-empty HMAC key so each example signs with a real keyed hash.
_signing_key = st.binary(min_size=1, max_size=32)

# Plain-language summary text and an optional list of observed defects.
_summary = st.text(max_size=40)
_defects = st.lists(
    st.builds(
        DataDefect,
        location=st.text(min_size=1, max_size=20),
        severity=st.text(min_size=1, max_size=20),
    ),
    max_size=3,
)


def _flip_hex_char(signature: str, pos: int) -> str:
    """Return ``signature`` with exactly one character changed (non-identity).

    The HMAC-SHA256 hexdigest is always non-empty, so flipping a single
    character at a generated position yields a guaranteed-different string.
    """

    i = pos % len(signature)
    replacement = "0" if signature[i] != "0" else "1"
    return signature[:i] + replacement + signature[i + 1 :]


@st.composite
def tamper_scenarios(draw: st.DrawFn) -> dict:
    """Generate a graded item, a signing key, and one non-identity mutation."""

    grade = draw(st.sampled_from(list(Grade)))
    scenario: dict = {
        "item_id": draw(_ident),
        "card_id": draw(_ident),
        "grade": grade,
        "graded_at": draw(_graded_at),
        "summary": draw(_summary),
        "defects": draw(_defects),
        "key": draw(_signing_key),
        "flip_pos": draw(st.integers(min_value=0, max_value=63)),
    }

    tamper = draw(
        st.sampled_from(["grade", "graded_at", "stored_sig", "presented_sig"])
    )
    scenario["tamper"] = tamper

    if tamper == "grade":
        # A different grade than the one signed at issuance.
        scenario["new_grade"] = draw(
            st.sampled_from([g for g in Grade if g is not grade])
        )
    elif tamper == "graded_at":
        # A different verification date than the one signed at issuance.
        new_graded_at = draw(_graded_at)
        assume(new_graded_at != scenario["graded_at"])
        scenario["new_graded_at"] = new_graded_at

    return scenario


@settings(max_examples=_ITERATIONS)
@given(tamper_scenarios())
def test_any_non_identity_mutation_yields_tampered_result(scenario: dict) -> None:
    """Any non-identity mutation of a signed field is detected as tampered.

    Validates Requirement 12.3: a Product_Health_Card whose recomputed signature
    does not match the stored signature (because the grade, the stored
    signature, the presented signature, or another signed field was altered)
    yields a tampered result with no card contents surfaced.
    """

    item_id = scenario["item_id"]
    card_id = scenario["card_id"]
    grade: Grade = scenario["grade"]

    repo = FakeItemRepository()
    repo.put_grade(
        item_id,
        GradeRecord(
            grade=grade.value,
            confidence=0.95,
            summary=scenario["summary"],
            defects=scenario["defects"],
        ),
    )
    svc = HealthCardService(
        signer=FakeCardSigner(key=scenario["key"]),
        item_repo=repo,
    )

    issued = svc.issue_card(
        item_id,
        graded_at=scenario["graded_at"],
        card_id=card_id,
    )

    presented_signature: str | None = None
    tamper = scenario["tamper"]

    if tamper == "grade":
        # Rewrite the persisted grade to a different value.
        repo.put_grade(
            item_id,
            GradeRecord(
                grade=scenario["new_grade"].value,
                confidence=0.95,
                summary=scenario["summary"],
                defects=scenario["defects"],
            ),
        )
    elif tamper == "graded_at":
        stored = repo.get_card(card_id)
        stored.graded_at = scenario["new_graded_at"]
        repo.put_card(item_id, stored)
    elif tamper == "stored_sig":
        stored = repo.get_card(card_id)
        stored.signature = _flip_hex_char(issued.signature, scenario["flip_pos"])
        repo.put_card(item_id, stored)
    elif tamper == "presented_sig":
        presented_signature = _flip_hex_char(issued.signature, scenario["flip_pos"])

    result = svc.verify_card(card_id, signature=presented_signature)

    # The mutation is detected: verification fails and no contents are surfaced.
    assert result.verified is False
    assert result.card is None
