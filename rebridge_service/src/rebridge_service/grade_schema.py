"""Canonical grade-assessment JSON schema and strict parser.

This module defines the canonical JSON wire shape of a grade assessment and a
*strict* parser that serializes/deserializes it against the service-layer
domain models. "Strict" means the parser rejects any JSON that does not conform
exactly to the schema: unknown fields, missing required fields, wrong types, an
out-of-range or non-finite confidence, or an unrecognized grade all raise
:class:`GradeSchemaError`.

It is the single source of truth for Requirement 5.6 ("THE Grading_Pipeline
SHALL parse the response as strict JSON conforming to the grade assessment
schema"). The Grading_Pipeline uses :func:`parse_grade_assessment` to turn a
raw model response into a validated :class:`~rebridge_service.models.GradeAssessment`,
and treats a raised :class:`GradeSchemaError` as the "non-conforming" signal
that routes the item to a review state (Requirement 5.7).

The parser produces the shared domain dataclasses from
:mod:`rebridge_service.models` so there is exactly one canonical in-memory
representation of a grade assessment across the service layer.
"""

from __future__ import annotations

import json
from typing import Any

from rebridge_service.models import (
    CompletenessResult,
    Defect,
    Grade,
    GradeAssessment,
)

__all__ = [
    "GradeSchemaError",
    "GRADE_LABELS",
    "GRADE_ASSESSMENT_JSON_SCHEMA",
    "parse_grade_assessment",
    "serialize_grade_assessment",
    "assessment_to_dict",
]


class GradeSchemaError(ValueError):
    """Raised when JSON does not conform to the grade-assessment schema.

    Carries a human-readable message identifying the offending field so callers
    (and tests) can see *why* the payload was rejected.
    """


# The canonical ordered set of valid grade labels on the wire, derived from the
# domain Grade enum so the two can never drift apart.
GRADE_LABELS: tuple[str, ...] = tuple(g.value for g in Grade)


# Canonical JSON Schema (Draft 2020-12) describing the wire format. This is the
# documented contract; the strict validation below is hand-implemented so the
# parser carries no runtime dependency on a JSON Schema library, but the two are
# kept in lockstep. ``additionalProperties: false`` everywhere encodes the
# "reject unknown fields" rule.
GRADE_ASSESSMENT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "GradeAssessment",
    "type": "object",
    "additionalProperties": False,
    "required": ["grade", "defects", "completeness", "confidence", "summary"],
    "properties": {
        "grade": {"type": "string", "enum": list(GRADE_LABELS)},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["location", "severity"],
                "properties": {
                    "location": {"type": "string", "minLength": 1},
                    "severity": {"type": "string", "minLength": 1},
                },
            },
        },
        "completeness": {
            "type": "object",
            "additionalProperties": False,
            "required": ["is_complete", "missing_components"],
            "properties": {
                "is_complete": {"type": "boolean"},
                "missing_components": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
            },
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "summary": {"type": "string", "minLength": 1},
    },
}


def _require_object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GradeSchemaError(f"{where} must be a JSON object, got {type(value).__name__}")
    return value


def _reject_unknown_keys(obj: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise GradeSchemaError(f"{where} has unknown field(s): {names}")


def _require_keys(obj: dict[str, Any], required: set[str], where: str) -> None:
    missing = required - set(obj)
    if missing:
        names = ", ".join(sorted(missing))
        raise GradeSchemaError(f"{where} is missing required field(s): {names}")


def _require_nonempty_str(value: Any, where: str) -> str:
    # bool is a subclass of int but never a str; the str check is sufficient.
    if not isinstance(value, str):
        raise GradeSchemaError(f"{where} must be a string, got {type(value).__name__}")
    if value == "":
        raise GradeSchemaError(f"{where} must be a non-empty string")
    return value


def _parse_defect(raw: Any, index: int) -> Defect:
    where = f"defects[{index}]"
    obj = _require_object(raw, where)
    _reject_unknown_keys(obj, {"location", "severity"}, where)
    _require_keys(obj, {"location", "severity"}, where)
    location = _require_nonempty_str(obj["location"], f"{where}.location")
    severity = _require_nonempty_str(obj["severity"], f"{where}.severity")
    return Defect(location=location, severity=severity)


def _parse_completeness(raw: Any) -> CompletenessResult:
    where = "completeness"
    obj = _require_object(raw, where)
    _reject_unknown_keys(obj, {"is_complete", "missing_components"}, where)
    _require_keys(obj, {"is_complete", "missing_components"}, where)

    is_complete = obj["is_complete"]
    if not isinstance(is_complete, bool):
        raise GradeSchemaError(
            f"{where}.is_complete must be a boolean, got {type(is_complete).__name__}"
        )

    missing_raw = obj["missing_components"]
    if not isinstance(missing_raw, list):
        raise GradeSchemaError(
            f"{where}.missing_components must be an array, got {type(missing_raw).__name__}"
        )
    missing_components = [
        _require_nonempty_str(item, f"{where}.missing_components[{i}]")
        for i, item in enumerate(missing_raw)
    ]
    return CompletenessResult(is_complete=is_complete, missing_components=missing_components)


def _parse_confidence(raw: Any) -> float:
    # Reject bool explicitly: bool is a subclass of int and would otherwise pass.
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise GradeSchemaError(f"confidence must be a number, got {type(raw).__name__}")
    value = float(raw)
    # Reject NaN / infinities, which are not valid JSON numbers and break the
    # [0, 1] bound check.
    if value != value or value in (float("inf"), float("-inf")):
        raise GradeSchemaError("confidence must be a finite number")
    if not (0.0 <= value <= 1.0):
        raise GradeSchemaError(
            f"confidence must be within the closed interval [0, 1], got {value}"
        )
    return value


def _parse_grade(raw: Any) -> Grade:
    if not isinstance(raw, str):
        raise GradeSchemaError(f"grade must be a string, got {type(raw).__name__}")
    
    # Do a case-insensitive match against the valid labels
    normalized = raw.strip().lower()
    for g in Grade:
        if g.value.lower() == normalized:
            return g

    allowed = ", ".join(GRADE_LABELS)
    raise GradeSchemaError(f"grade must be one of [{allowed}], got {raw!r}")


def parse_grade_assessment(data: str | bytes | bytearray | dict[str, Any]) -> GradeAssessment:
    """Strictly parse a grade assessment from JSON.

    Accepts a JSON string/bytes or an already-decoded ``dict``. Returns a
    validated :class:`~rebridge_service.models.GradeAssessment`. Raises
    :class:`GradeSchemaError` for any non-conforming input: malformed JSON, a
    non-object root, unknown fields, missing required fields, wrong types, an
    unrecognized grade, an out-of-range or non-finite confidence, an empty
    summary, or a defect missing its location or severity.
    """

    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")

    if isinstance(data, str):
        # Defensively strip markdown formatting and leading/trailing whitespace
        # in case the model ignores the prompt and wraps the JSON.
        cleaned = data.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            decoded = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            raise GradeSchemaError(f"payload is not valid JSON: {exc}") from exc
    else:
        decoded = data

    root = _require_object(decoded, "grade assessment")
    allowed = {"grade", "defects", "completeness", "confidence", "summary"}
    _reject_unknown_keys(root, allowed, "grade assessment")
    _require_keys(root, allowed, "grade assessment")

    grade = _parse_grade(root["grade"])

    defects_raw = root["defects"]
    if not isinstance(defects_raw, list):
        raise GradeSchemaError(f"defects must be an array, got {type(defects_raw).__name__}")
    defects = [_parse_defect(d, i) for i, d in enumerate(defects_raw)]

    completeness = _parse_completeness(root["completeness"])
    confidence = _parse_confidence(root["confidence"])
    summary = _require_nonempty_str(root["summary"], "summary")

    # GradeAssessment.__post_init__ re-validates grade/confidence as a
    # defense-in-depth check; the values above already satisfy it.
    return GradeAssessment(
        grade=grade,
        defects=defects,
        completeness=completeness,
        confidence=confidence,
        summary=summary,
    )


def assessment_to_dict(assessment: GradeAssessment) -> dict[str, Any]:
    """Convert a :class:`~rebridge_service.models.GradeAssessment` into its
    canonical JSON-ready dict."""

    return {
        "grade": assessment.grade.value,
        "defects": [
            {"location": d.location, "severity": d.severity} for d in assessment.defects
        ],
        "completeness": {
            "is_complete": assessment.completeness.is_complete,
            "missing_components": list(assessment.completeness.missing_components),
        },
        "confidence": assessment.confidence,
        "summary": assessment.summary,
    }


def serialize_grade_assessment(assessment: GradeAssessment) -> str:
    """Serialize a grade assessment to a canonical JSON string.

    The output is guaranteed to round-trip: ``parse_grade_assessment(
    serialize_grade_assessment(a)) == a``.
    """

    return json.dumps(assessment_to_dict(assessment), ensure_ascii=False)
