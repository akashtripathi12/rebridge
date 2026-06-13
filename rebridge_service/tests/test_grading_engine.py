"""Unit tests for the GradingEngine cascade, timeout, and JSON-retry policy.

These exercise the engine against the programmable :class:`FakeGradingProvider`
(an in-memory implementation of the swappable provider seam) so there are no
AWS calls and no real wall-clock sleeps. Timeouts are driven by providers that
raise ``TimeoutError`` while the engine runs calls inline (``timeout=None``).

Covered behaviors (Requirements 5.1-5.6, 8.1, 8.2, 8.4):
* cascade ordering: the first provider (Nova Lite) is invoked first;
* success on the first provider returns without touching later providers;
* timeout / error on a provider falls through to the next;
* non-conforming JSON is retried against the same provider up to 2x, then
  falls through;
* the first schema-conforming result is returned regardless of provider id;
* total cascade failure raises :class:`TotalCascadeFailure`.
"""

from __future__ import annotations

import pytest

from rebridge_data.models import CatalogContext, RawModelResponse

from rebridge_service.grade_schema import serialize_grade_assessment
from rebridge_service.grading_engine import (
    GradingEngine,
    TotalCascadeFailure,
    thread_timeout_runner,
)
from rebridge_service.models import (
    CompletenessResult,
    Defect,
    Grade,
    GradeAssessment,
)

from tests.fakes import FakeGradingProvider

CATALOG = CatalogContext(category="electronics")
IMAGES = [b"img-0", b"img-1"]


def _assessment(grade: Grade = Grade.GOOD, confidence: float = 0.9) -> GradeAssessment:
    return GradeAssessment(
        grade=grade,
        defects=[Defect(location="corner", severity="minor")],
        completeness=CompletenessResult(is_complete=True, missing_components=[]),
        confidence=confidence,
        summary="Looks good overall.",
    )


def _valid_json(grade: Grade = Grade.GOOD, confidence: float = 0.9) -> str:
    return serialize_grade_assessment(_assessment(grade, confidence))


def _engine(*providers, **kwargs) -> GradingEngine:
    # Default to inline execution (no timeout) so TimeoutError scripted by a
    # fake provider drives fallthrough deterministically.
    kwargs.setdefault("timeout", None)
    return GradingEngine(list(providers), **kwargs)


# --- Happy path / cascade ordering -----------------------------------------


def test_first_provider_success_returns_and_skips_rest():
    nova = FakeGradingProvider("nova", script=[_valid_json(Grade.LIKE_NEW, 0.95)])
    claude = FakeGradingProvider("claude", script=[_valid_json(Grade.GOOD)])
    engine = _engine(nova, claude)

    result = engine.grade(IMAGES, CATALOG)

    assert result.grade is Grade.LIKE_NEW
    assert result.confidence == 0.95
    # Nova Lite invoked first; Claude never touched (Requirement 8.1).
    assert len(nova.calls) == 1
    assert claude.calls == []


def test_images_and_catalog_are_passed_to_provider():
    nova = FakeGradingProvider("nova", script=[_valid_json()])
    engine = _engine(nova)

    engine.grade(IMAGES, CATALOG)

    assert nova.calls == [(len(IMAGES), CATALOG)]


# --- Fallthrough on timeout / error (Requirement 8.2) ----------------------


def test_timeout_on_first_provider_falls_through_to_second():
    nova = FakeGradingProvider("nova", script=[TimeoutError("nova timed out")])
    claude = FakeGradingProvider("claude", script=[_valid_json(Grade.VERY_GOOD)])
    engine = _engine(nova, claude)

    result = engine.grade(IMAGES, CATALOG)

    assert result.grade is Grade.VERY_GOOD
    assert len(nova.calls) == 1  # tried once, no JSON retries on timeout
    assert len(claude.calls) == 1


def test_error_on_first_provider_falls_through_to_second():
    nova = FakeGradingProvider("nova", script=[RuntimeError("boom")])
    claude = FakeGradingProvider("claude", script=[_valid_json(Grade.ACCEPTABLE)])
    engine = _engine(nova, claude)

    result = engine.grade(IMAGES, CATALOG)

    assert result.grade is Grade.ACCEPTABLE
    assert len(nova.calls) == 1  # provider error short-circuits, no JSON retry
    assert len(claude.calls) == 1


# --- Invalid-JSON retry policy (Requirements 5.6, retry up to 2x) ----------


def test_invalid_json_is_retried_up_to_two_times_then_succeeds():
    # 2 bad responses then a good one => succeeds on the 3rd attempt.
    nova = FakeGradingProvider(
        "nova",
        script=["not json", '{"grade": "Nope"}', _valid_json(Grade.GOOD)],
    )
    engine = _engine(nova, max_json_retries=2)

    result = engine.grade(IMAGES, CATALOG)

    assert result.grade is Grade.GOOD
    assert len(nova.calls) == 3  # initial + 2 retries


def test_invalid_json_exhausts_retries_then_falls_through():
    # Nova always returns junk; engine retries 3 total then moves to Claude.
    nova = FakeGradingProvider("nova", script=["still not json"])  # single-elem repeats
    claude = FakeGradingProvider("claude", script=[_valid_json(Grade.GOOD)])
    engine = _engine(nova, claude, max_json_retries=2)

    result = engine.grade(IMAGES, CATALOG)

    assert result.grade is Grade.GOOD
    assert len(nova.calls) == 3  # initial + 2 retries before fallthrough
    assert len(claude.calls) == 1


def test_zero_retries_falls_through_on_first_invalid_json():
    nova = FakeGradingProvider("nova", script=["not json"])
    claude = FakeGradingProvider("claude", script=[_valid_json()])
    engine = _engine(nova, claude, max_json_retries=0)

    engine.grade(IMAGES, CATALOG)

    assert len(nova.calls) == 1


# --- Total cascade failure (Requirement 8.3) -------------------------------


def test_all_providers_fail_raises_total_cascade_failure():
    nova = FakeGradingProvider("nova", script=[TimeoutError("t")])
    claude = FakeGradingProvider("claude", script=[RuntimeError("e")])
    engine = _engine(nova, claude)

    with pytest.raises(TotalCascadeFailure) as exc_info:
        engine.grade(IMAGES, CATALOG)

    reasons = {a.reason for a in exc_info.value.attempts}
    assert reasons == {"timeout", "error"}


def test_all_providers_invalid_json_raises_total_cascade_failure():
    nova = FakeGradingProvider("nova", script=["junk"])
    claude = FakeGradingProvider("claude", script=["garbage"])
    engine = _engine(nova, claude, max_json_retries=2)

    with pytest.raises(TotalCascadeFailure) as exc_info:
        engine.grade(IMAGES, CATALOG)

    # 3 attempts per provider, all non-conforming.
    assert len(exc_info.value.attempts) == 6
    assert all(a.reason == "non_conforming_json" for a in exc_info.value.attempts)
    assert len(nova.calls) == 3 and len(claude.calls) == 3


def test_no_providers_raises_total_cascade_failure():
    engine = _engine()
    with pytest.raises(TotalCascadeFailure):
        engine.grade(IMAGES, CATALOG)


# --- Provider seam substitutability (Requirement 8.4 / Property 15) --------


def test_provider_identity_does_not_change_result():
    nova = FakeGradingProvider("nova", script=[_valid_json(Grade.GOOD, 0.88)])
    alt = FakeGradingProvider("some-other-model", script=[_valid_json(Grade.GOOD, 0.88)])

    via_nova = _engine(nova).grade(IMAGES, CATALOG)
    via_alt = _engine(alt).grade(IMAGES, CATALOG)

    assert via_nova == via_alt


# --- Injectable timeout runner ---------------------------------------------


def test_injected_timeout_runner_enforces_budget():
    # A runner that ignores the call and always times out drives fallthrough
    # without any real clock.
    def always_timeout(call, timeout):
        raise TimeoutError(f"budget {timeout} exceeded")

    nova = FakeGradingProvider("nova", script=[_valid_json(Grade.GOOD)])
    claude = FakeGradingProvider("claude", script=[_valid_json(Grade.GOOD)])
    engine = GradingEngine([nova, claude], timeout=1.0, timeout_runner=always_timeout)

    with pytest.raises(TotalCascadeFailure) as exc_info:
        engine.grade(IMAGES, CATALOG)
    assert all(a.reason == "timeout" for a in exc_info.value.attempts)
    # Providers were never actually invoked because the runner short-circuited.
    assert nova.calls == [] and claude.calls == []


def test_default_thread_runner_returns_value_within_budget():
    called = {}

    def call():
        called["ran"] = True
        return RawModelResponse(provider_name="nova", content=_valid_json())

    result = thread_timeout_runner(call, timeout=5.0)
    assert called["ran"] is True
    assert result.provider_name == "nova"


def test_negative_max_json_retries_rejected():
    with pytest.raises(ValueError):
        GradingEngine([FakeGradingProvider("nova")], max_json_retries=-1)
