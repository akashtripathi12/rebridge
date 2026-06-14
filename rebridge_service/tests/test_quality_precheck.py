"""Unit tests for the Image Quality Precheck (Requirement 4, task 5.1).

These example/edge-case tests cover the blur (variance-of-Laplacian) and
exposure metrics and the gating decision: a clean set passes and clears
grading (4.3); a set with any failing photo yields ``RETAKE_REQUIRED`` with a
retake prompt naming every failing photo (4.2). The universal property for this
behavior (Property 6) is covered separately by the property-based test task.
"""

from __future__ import annotations

import pytest

from rebridge_data.models import ItemStatus
from rebridge_service.quality_precheck import (
    BLUR_REASON,
    OVEREXPOSED_REASON,
    UNDEREXPOSED_REASON,
    Photo,
    PrecheckConfig,
    QualityPrecheck,
    mean_brightness,
    variance_of_laplacian,
)


# --- Pixel-matrix fixtures --------------------------------------------------

def _uniform(value: float, size: int = 8) -> list[list[float]]:
    """A flat, edgeless matrix: zero Laplacian variance (maximally blurry)."""
    return [[value for _ in range(size)] for _ in range(size)]


def _high_contrast_checkerboard(size: int = 8) -> list[list[float]]:
    """A sharp, well-exposed checkerboard: high Laplacian variance, mid brightness."""
    return [
        [0.0 if (r + c) % 2 == 0 else 255.0 for c in range(size)]
        for r in range(size)
    ]


def _mid_grey_sharp(size: int = 8) -> list[list[float]]:
    """Sharp edges centered on a mid-grey level so brightness sits in-band."""
    return [
        [40.0 if (r + c) % 2 == 0 else 215.0 for c in range(size)]
        for r in range(size)
    ]


# --- Metric functions -------------------------------------------------------

def test_uniform_image_has_zero_laplacian_variance() -> None:
    assert variance_of_laplacian(_uniform(128.0)) == 0.0


def test_checkerboard_has_high_laplacian_variance() -> None:
    assert variance_of_laplacian(_high_contrast_checkerboard()) > 100.0


def test_mean_brightness_of_uniform_matrix() -> None:
    assert mean_brightness(_uniform(100.0)) == 100.0


def test_matrix_smaller_than_kernel_is_treated_as_blurry() -> None:
    # No interior pixel exists for a 2x2, so variance is 0.0 (unusable).
    assert variance_of_laplacian([[10.0, 250.0], [250.0, 10.0]]) == 0.0


def test_empty_matrix_brightness_is_zero() -> None:
    assert mean_brightness([]) == 0.0


def test_ragged_matrix_raises() -> None:
    with pytest.raises(ValueError):
        variance_of_laplacian([[1.0, 2.0, 3.0], [1.0, 2.0]])


# --- Single-photo assessment ------------------------------------------------

def test_sharp_well_lit_photo_passes() -> None:
    precheck = QualityPrecheck()
    result = precheck.assess_photo(Photo(key="front", pixels=_mid_grey_sharp()))
    assert result.passed
    assert result.failure_reasons == ()


def test_blurry_photo_is_flagged() -> None:
    precheck = QualityPrecheck()
    # Mid-grey flat image: in-band brightness but zero blur variance.
    result = precheck.assess_photo(Photo(key="back", pixels=_uniform(128.0)))
    assert not result.passed
    assert BLUR_REASON in result.failure_reasons
    assert UNDEREXPOSED_REASON not in result.failure_reasons
    assert OVEREXPOSED_REASON not in result.failure_reasons


def test_dark_photo_is_flagged_underexposed() -> None:
    precheck = QualityPrecheck()
    # Sharp but very dark: edges present, mean brightness below the band.
    dark = [[0.0 if (r + c) % 2 == 0 else 20.0 for c in range(8)] for r in range(8)]
    result = precheck.assess_photo(Photo(key="dark", pixels=dark))
    assert not result.passed
    assert UNDEREXPOSED_REASON in result.failure_reasons


def test_bright_photo_is_flagged_overexposed() -> None:
    precheck = QualityPrecheck()
    # Sharp but washed out: edges present, mean brightness above the band.
    bright = [
        [235.0 if (r + c) % 2 == 0 else 255.0 for c in range(8)] for r in range(8)
    ]
    result = precheck.assess_photo(Photo(key="bright", pixels=bright))
    assert not result.passed
    assert OVEREXPOSED_REASON in result.failure_reasons


# --- Photo-set gating -------------------------------------------------------

def test_all_passing_set_clears_grading() -> None:
    precheck = QualityPrecheck()
    photos = [
        Photo(key="front", pixels=_mid_grey_sharp()),
        Photo(key="back", pixels=_mid_grey_sharp()),
    ]
    result = precheck.assess(photos)
    assert result.passed
    assert result.status is None
    assert result.retake_prompt is None
    assert result.failing_keys == ()
    assert len(result.assessments) == 2


def test_failing_set_requires_retake_and_names_failing_photo() -> None:
    precheck = QualityPrecheck()
    photos = [
        Photo(key="front", pixels=_mid_grey_sharp()),  # passes
        Photo(key="blurry-back", pixels=_uniform(128.0)),  # fails (blur)
    ]
    result = precheck.assess(photos)
    assert not result.passed
    assert result.status is ItemStatus.RETAKE_REQUIRED
    assert result.failing_keys == ("blurry-back",)
    assert "blurry-back" in result.retake_prompt
    assert "front" not in result.retake_prompt
    # Every photo was still assessed before the gating decision.
    assert len(result.assessments) == 2


def test_retake_prompt_names_all_failing_photos() -> None:
    precheck = QualityPrecheck()
    photos = [
        Photo(key="p0", pixels=_uniform(128.0)),  # blurry
        Photo(key="p1", pixels=_mid_grey_sharp()),  # passes
        Photo(key="p2", pixels=_uniform(5.0)),  # blurry + dark
    ]
    result = precheck.assess(photos)
    assert not result.passed
    assert result.failing_keys == ("p0", "p2")
    assert "p0" in result.retake_prompt
    assert "p2" in result.retake_prompt
    assert "too dark" in result.retake_prompt


def test_empty_photo_set_raises() -> None:
    with pytest.raises(ValueError):
        QualityPrecheck().assess([])


# --- Configurable thresholds ------------------------------------------------

def test_custom_threshold_changes_blur_verdict() -> None:
    checker = _high_contrast_checkerboard()
    blur_score = variance_of_laplacian(checker)
    # A threshold above the actual score should now reject the sharp image.
    strict = QualityPrecheck(PrecheckConfig(min_blur_variance=blur_score + 1.0))
    result = strict.assess_photo(Photo(key="front", pixels=checker))
    assert not result.passed
    assert BLUR_REASON in result.failure_reasons


def test_invalid_config_brightness_band_raises() -> None:
    with pytest.raises(ValueError):
        PrecheckConfig(min_brightness=200.0, max_brightness=100.0)
