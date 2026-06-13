"""Property-based test for the model cascade ordering and fallback policy.

# Feature: rebridge-backend, Property 13: Model cascade ordering and fallback

Property 13 (design.md): *For any* photo set, the Grading_Engine SHALL invoke
the first provider (Nova Lite) first, and *for any* failure or timeout of a
provider SHALL fall through to the next provider in cascade order, using the
first successful schema-conforming result.

**Validates: Requirements 8.1, 8.2**

The strategy generates varied provider *scripts* over an ordered cascade. Each
provider is assigned one of four outcomes:

* ``conform``  - returns a unique schema-conforming JSON assessment;
* ``timeout``  - raises ``TimeoutError`` (Requirement 8.2 fallthrough);
* ``error``    - raises an arbitrary provider error (fallthrough);
* ``bad_json`` - always returns non-conforming JSON, so the engine exhausts its
  JSON retries against that provider and then falls through.

For each generated cascade the test asserts:

1. providers are invoked strictly in cascade order (a global invocation log is
   non-decreasing in provider index);
2. every provider up to and including the first ``conform`` provider is invoked,
   and no provider after it is touched;
3. the engine returns exactly the first ``conform`` provider's assessment - so a
   failing/timing-out prefix correctly falls through to the first later provider
   that yields conforming JSON;
4. when no provider conforms, ``TotalCascadeFailure`` is raised and every
   provider in the cascade was attempted.

All scenarios run against the in-memory programmable ``FakeGradingProvider`` -
no AWS calls and no real wall-clock sleeps (timeouts are scripted as
``TimeoutError`` while the engine runs calls inline with ``timeout=None``).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_data.models import CatalogContext, RawModelResponse

from rebridge_service.grade_schema import serialize_grade_assessment
from rebridge_service.grading_engine import GradingEngine, TotalCascadeFailure
from rebridge_service.models import (
    CompletenessResult,
    Defect,
    Grade,
    GradeAssessment,
)

from tests.fakes import FakeGradingProvider

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

_GRADES = list(Grade)
_OUTCOMES = ["conform", "timeout", "error", "bad_json"]


class _RecordingProvider(FakeGradingProvider):
    """A FakeGradingProvider that also appends its name to a shared log.

    The shared ``order_log`` captures the *global* invocation sequence across
    the whole cascade, letting the test assert strict cross-provider ordering
    (not just per-provider call counts).
    """

    def __init__(self, name, script, order_log):
        super().__init__(name, script)
        self._order_log = order_log

    def grade(self, images, catalog):
        self._order_log.append(self._name)
        return super().grade(images, catalog)


def _unique_assessment(index: int) -> GradeAssessment:
    """A schema-conforming assessment uniquely identifying ``index``.

    The summary embeds the provider index so the test can prove *which*
    provider's result the engine returned.
    """
    return GradeAssessment(
        grade=_GRADES[index % len(_GRADES)],
        defects=[Defect(location="corner", severity="minor")],
        completeness=CompletenessResult(is_complete=True, missing_components=[]),
        confidence=round(0.5 + (index % 5) * 0.1, 2),
        summary=f"provider-{index}",
    )


@st.composite
def cascades(draw: st.DrawFn):
    """Generate an ordered cascade as a list of per-provider outcome strings.

    Between 1 and 5 providers, each independently assigned an outcome. This
    covers prefixes of failures/timeouts/bad-json followed (or not) by a
    conforming provider.
    """
    n = draw(st.integers(min_value=1, max_value=5))
    outcomes = draw(
        st.lists(st.sampled_from(_OUTCOMES), min_size=n, max_size=n)
    )
    return outcomes


# Vary the photo set ("for any photo set"): 2-4 photos per submission.
_photo_sets = st.lists(
    st.binary(min_size=1, max_size=8), min_size=2, max_size=4
)


def _build_cascade(outcomes, order_log):
    """Construct recording providers and the matching expected assessments."""
    providers: list[_RecordingProvider] = []
    expected: dict[int, GradeAssessment] = {}
    for i, outcome in enumerate(outcomes):
        if outcome == "conform":
            assessment = _unique_assessment(i)
            expected[i] = assessment
            script = [serialize_grade_assessment(assessment)]
        elif outcome == "timeout":
            script = [TimeoutError(f"provider-{i} timed out")]
        elif outcome == "error":
            script = [RuntimeError(f"provider-{i} boom")]
        else:  # bad_json - single element repeats, exhausting JSON retries
            script = ["this is not json"]
        providers.append(_RecordingProvider(f"p{i}", script, order_log))
    return providers, expected


@settings(max_examples=_ITERATIONS)
@given(cascades(), _photo_sets)
def test_cascade_invokes_in_order_and_returns_first_conforming(outcomes, images):
    """Providers run strictly in order; first conforming result is returned."""

    order_log: list[str] = []
    providers, expected = _build_cascade(outcomes, order_log)
    catalog = CatalogContext(category="electronics")
    # timeout=None => scripted TimeoutError drives fallthrough deterministically.
    engine = GradingEngine(providers, timeout=None, max_json_retries=2)

    first_conform = next(
        (i for i, o in enumerate(outcomes) if o == "conform"), None
    )

    if first_conform is None:
        # Total cascade failure: every provider attempted, no result.
        try:
            engine.grade(images, catalog)
        except TotalCascadeFailure:
            pass
        else:
            raise AssertionError("expected TotalCascadeFailure when nothing conforms")
        called = {p.name for p in providers if p.calls}
        assert called == {p.name for p in providers}
    else:
        result = engine.grade(images, catalog)
        # Returns exactly the first conforming provider's assessment (8.2).
        assert result == expected[first_conform]
        # Every provider up to and including the first conform was invoked...
        for i in range(first_conform + 1):
            assert providers[i].calls, f"provider {i} should have been invoked"
        # ...and none after it was touched (cascade stops on first success).
        for i in range(first_conform + 1, len(providers)):
            assert providers[i].calls == [], f"provider {i} must not be invoked"

    # Strict ordering: the global invocation log is non-decreasing in index
    # (provider i is always invoked before provider j for i < j), allowing
    # repeats from same-provider JSON retries (Requirement 8.1).
    indices = [int(name[1:]) for name in order_log]
    assert indices == sorted(indices), f"out-of-order invocation: {order_log}"

    # The first provider (Nova Lite position) is always invoked first (8.1).
    if order_log:
        assert order_log[0] == "p0"

    # The photo set is forwarded unchanged to every invoked provider.
    for p in providers:
        for call in p.calls:
            assert call == (len(images), catalog)
