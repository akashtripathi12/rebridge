"""Property-based test for the grade-assessment schema round-trip.

# Feature: rebridge-backend, Property 7: Grade-assessment schema invariant and parse round-trip

Property 7 (design.md): *For any* schema-conforming grade assessment,
serializing then strictly parsing SHALL yield an equivalent assessment whose
grade is one of the five allowed values, whose every defect has a location and
severity, which includes a completeness result and a non-empty plain-language
summary, and whose confidence lies in the closed interval [0, 1].

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

The strategy below generates only schema-conforming ``GradeAssessment``
instances directly from the domain model, then exercises the canonical
serializer/parser pair. A complementary strategy mutates a valid wire dict into
a non-conforming one to confirm the strict parser rejects it with
``GradeSchemaError`` (Requirement 5.6).
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.grade_schema import (
    GRADE_LABELS,
    GradeSchemaError,
    assessment_to_dict,
    parse_grade_assessment,
    serialize_grade_assessment,
)
from rebridge_service.models import (
    CompletenessResult,
    Defect,
    Grade,
    GradeAssessment,
)

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

# Non-empty text for fields the schema requires to be non-empty strings
# (defect location/severity, missing-component names, summary).
_nonempty_text = st.text(min_size=1, max_size=40)


@st.composite
def grade_assessments(draw: st.DrawFn) -> GradeAssessment:
    """Generate a schema-conforming GradeAssessment.

    Constrained to the valid input space: a grade from the five allowed enum
    members, defects each with a non-empty location and severity, a
    completeness result with non-empty missing-component names, a confidence in
    the closed interval [0, 1], and a non-empty summary.
    """

    grade = draw(st.sampled_from(list(Grade)))
    defects = draw(
        st.lists(
            st.builds(Defect, location=_nonempty_text, severity=_nonempty_text),
            max_size=5,
        )
    )
    completeness = draw(
        st.builds(
            CompletenessResult,
            is_complete=st.booleans(),
            missing_components=st.lists(_nonempty_text, max_size=5),
        )
    )
    confidence = draw(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    )
    summary = draw(_nonempty_text)
    return GradeAssessment(
        grade=grade,
        defects=defects,
        completeness=completeness,
        confidence=confidence,
        summary=summary,
    )


@settings(max_examples=_ITERATIONS)
@given(grade_assessments())
def test_serialize_then_parse_is_identity(assessment: GradeAssessment) -> None:
    """parse(serialize(a)) == a for any schema-conforming assessment."""

    round_tripped = parse_grade_assessment(serialize_grade_assessment(assessment))
    assert round_tripped == assessment
    # Also round-trips from an already-decoded dict.
    assert parse_grade_assessment(assessment_to_dict(assessment)) == assessment


@settings(max_examples=_ITERATIONS)
@given(grade_assessments())
def test_schema_invariants_hold_after_roundtrip(assessment: GradeAssessment) -> None:
    """The parsed assessment satisfies every Property-7 invariant."""

    parsed = parse_grade_assessment(serialize_grade_assessment(assessment))

    # Req 5.1: grade is one of exactly the five allowed values.
    assert isinstance(parsed.grade, Grade)
    assert parsed.grade.value in GRADE_LABELS
    assert len(GRADE_LABELS) == 5

    # Req 5.2: every defect has a non-empty location and severity.
    for defect in parsed.defects:
        assert isinstance(defect, Defect)
        assert defect.location != ""
        assert defect.severity != ""

    # Req 5.3: a completeness result is present and well-formed.
    assert isinstance(parsed.completeness, CompletenessResult)
    assert isinstance(parsed.completeness.is_complete, bool)
    for component in parsed.completeness.missing_components:
        assert component != ""

    # Req 5.4: confidence lies in the closed interval [0, 1].
    assert 0.0 <= parsed.confidence <= 1.0

    # Req 5.5: a non-empty plain-language summary is present.
    assert isinstance(parsed.summary, str)
    assert parsed.summary != ""


# --- Non-conforming JSON is rejected (Requirement 5.6) ----------------------

# Each mutation turns a valid wire dict into a non-conforming one. Keyed by the
# rule it violates so failures point at the broken invariant.
def _drop_required(d: dict) -> dict:
    d.pop("grade", None)
    return d


def _unknown_field(d: dict) -> dict:
    d["unexpected"] = "x"
    return d


def _bad_grade(d: dict) -> dict:
    d["grade"] = "Mint Condition"
    return d


def _confidence_out_of_range(d: dict) -> dict:
    d["confidence"] = 1.5
    return d


def _empty_summary(d: dict) -> dict:
    d["summary"] = ""
    return d


def _defect_missing_severity(d: dict) -> dict:
    d["defects"] = [{"location": "corner"}]
    return d


def _confidence_wrong_type(d: dict) -> dict:
    d["confidence"] = "high"
    return d


_MUTATIONS = st.sampled_from(
    [
        _drop_required,
        _unknown_field,
        _bad_grade,
        _confidence_out_of_range,
        _empty_summary,
        _defect_missing_severity,
        _confidence_wrong_type,
    ]
)


@settings(max_examples=_ITERATIONS)
@given(grade_assessments(), _MUTATIONS)
def test_non_conforming_json_is_rejected(assessment: GradeAssessment, mutate) -> None:
    """A non-conforming payload raises GradeSchemaError (Req 5.6)."""

    payload = mutate(assessment_to_dict(assessment))
    try:
        parse_grade_assessment(json.dumps(payload))
    except GradeSchemaError:
        return
    raise AssertionError(
        f"expected GradeSchemaError for mutation {mutate.__name__}, none raised"
    )
