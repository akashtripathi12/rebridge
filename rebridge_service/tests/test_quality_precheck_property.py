"""Property-based test for quality-precheck gating.

# Feature: rebridge-backend, Property 6: Quality precheck gates grading

Property 6 (design.md): *For any* submitted photo set, every photo SHALL be
assessed for blur and lighting before the Grading_Engine is invoked; *for any*
set containing at least one failing photo, the Item status SHALL become
RETAKE_REQUIRED with the failing photo identified and the Grading_Engine SHALL
NOT be invoked; *for any* all-passing set, the Grading_Engine SHALL be invoked.

**Validates: Requirements 4.1, 4.2, 4.3**

`QualityPrecheck` is the pure, framework-free component that owns the gating
*decision*: it assesses every photo (no short-circuit) and reports either a
clear-to-grade outcome (`passed=True`, no status, no prompt) or a
`RETAKE_REQUIRED` outcome whose `retake_prompt` names every failing photo. The
`GradingPipeline` applies that decision -- it only invokes the Grading_Engine
when the precheck passes -- so the precheck's pass/fail flag is exactly the gate
that controls Grading_Engine invocation.

The strategy generates photo sets spanning the four meaningful categories
(sharp/well-lit, blurry, too-dark, too-bright) so a generated set is an
arbitrary mix of passing and failing photos. Each generated photo carries the
pass/fail verdict its category implies, giving an *independent* oracle for the
per-photo blur+exposure check (4.1) on top of the set-level gating relationship
(4.2, 4.3).
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.models import ItemStatus
from rebridge_service.quality_precheck import (
    Photo,
    PrecheckConfig,
    QualityPrecheck,
)

# Minimum iterations per the spec's property-testing guideline.
_ITERATIONS = 200

# The component under test uses default thresholds; the generators below are
# built relative to these so each category's verdict is unambiguous.
_CONFIG = PrecheckConfig()


@dataclass(frozen=True)
class _LabeledPhoto:
    """A generated pixel matrix together with the verdict its category implies."""

    pixels: list[list[float]]
    expected_pass: bool


def _checkerboard(low: float, high: float, size: int) -> list[list[float]]:
    """A high-contrast (sharp) checkerboard alternating two intensities.

    For an even ``size`` the two values occur in equal counts, so the mean
    brightness is exactly ``(low + high) / 2`` -- which keeps each category's
    exposure verdict predictable.
    """
    return [
        [low if (r + c) % 2 == 0 else high for c in range(size)]
        for r in range(size)
    ]


def _uniform(value: float, size: int) -> list[list[float]]:
    """A flat, edgeless matrix: zero Laplacian variance (maximally blurry)."""
    return [[value for _ in range(size)] for _ in range(size)]


# Even sizes keep the checkerboard mean brightness exactly midway between the
# two intensities, so the exposure band membership is deterministic.
_sizes = st.sampled_from([4, 6, 8])


@st.composite
def _sharp_well_lit(draw: st.DrawFn) -> _LabeledPhoto:
    """Sharp edges with mean brightness comfortably inside the exposure band."""
    low = draw(st.integers(min_value=50, max_value=90))
    high = draw(st.integers(min_value=160, max_value=210))
    size = draw(_sizes)
    return _LabeledPhoto(_checkerboard(low, high, size), expected_pass=True)


@st.composite
def _blurry(draw: st.DrawFn) -> _LabeledPhoto:
    """Edgeless flat frame: in-band brightness but fails the blur check."""
    value = draw(st.integers(min_value=50, max_value=210))
    size = draw(_sizes)
    return _LabeledPhoto(_uniform(float(value), size), expected_pass=False)


@st.composite
def _too_dark(draw: st.DrawFn) -> _LabeledPhoto:
    """Sharp but underexposed: edges present, mean brightness below the band."""
    high = draw(st.integers(min_value=10, max_value=35))
    size = draw(_sizes)
    return _LabeledPhoto(_checkerboard(0.0, float(high), size), expected_pass=False)


@st.composite
def _too_bright(draw: st.DrawFn) -> _LabeledPhoto:
    """Sharp but overexposed: edges present, mean brightness above the band."""
    low = draw(st.integers(min_value=225, max_value=245))
    size = draw(_sizes)
    return _LabeledPhoto(_checkerboard(float(low), 255.0, size), expected_pass=False)


_labeled_photo = st.one_of(_sharp_well_lit(), _blurry(), _too_dark(), _too_bright())


@st.composite
def _photo_sets(draw: st.DrawFn) -> list[tuple[Photo, bool]]:
    """A non-empty list of photos with distinct keys, each tagged pass/fail.

    Distinct, quote-delimited keys (``'photo-0'`` ...) let the prompt-naming
    assertions test for an exact ``'<key>'`` token, avoiding substring
    false-positives between e.g. ``photo-1`` and ``photo-12``.
    """
    labeled = draw(st.lists(_labeled_photo, min_size=1, max_size=6))
    return [
        (Photo(key=f"photo-{i}", pixels=lp.pixels), lp.expected_pass)
        for i, lp in enumerate(labeled)
    ]


@settings(max_examples=_ITERATIONS)
@given(_photo_sets())
def test_precheck_gates_grading(photo_set: list[tuple[Photo, bool]]) -> None:
    precheck = QualityPrecheck(_CONFIG)
    photos = [photo for photo, _ in photo_set]

    # Independent oracle (Req 4.1): each photo's category verdict matches the
    # component's own per-photo blur + exposure assessment.
    for photo, expected_pass in photo_set:
        assert precheck.assess_photo(photo).passed is expected_pass

    expected_failing_keys = tuple(
        photo.key for photo, expected_pass in photo_set if not expected_pass
    )

    result = precheck.assess(photos)

    # Req 4.1: every submitted photo is assessed before any gating decision.
    assert len(result.assessments) == len(photos)
    assert tuple(a.key for a in result.assessments) == tuple(p.key for p in photos)

    # The set passes iff every photo passes both checks.
    assert result.passed is (len(expected_failing_keys) == 0)

    if result.passed:
        # Req 4.3: an all-passing set is cleared to grade -- no retake state.
        # `passed` is exactly the flag the pipeline checks before invoking the
        # Grading_Engine, so a passing result authorizes invocation.
        assert result.status is None
        assert result.retake_prompt is None
        assert result.failing_keys == ()
    else:
        # Req 4.2: any failing photo forces RETAKE_REQUIRED with a prompt that
        # names every failing photo (and the pipeline therefore does NOT invoke
        # the Grading_Engine, since the result did not pass).
        assert result.status is ItemStatus.RETAKE_REQUIRED
        assert result.failing_keys == expected_failing_keys
        assert result.retake_prompt is not None

        passing_keys = {
            photo.key for photo, expected_pass in photo_set if expected_pass
        }
        for key in result.failing_keys:
            assert f"'{key}'" in result.retake_prompt
        # No passing photo is named in the retake prompt.
        for key in passing_keys:
            assert f"'{key}'" not in result.retake_prompt
