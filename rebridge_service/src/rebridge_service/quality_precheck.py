"""Image Quality Precheck (Requirement 4).

The :class:`QualityPrecheck` assesses each submitted photo for **blur** and
**lighting adequacy** *before* the Grading_Engine is invoked (Requirement 4.1).
If any photo fails, the precheck reports a ``RETAKE_REQUIRED`` outcome together
with a human-readable retake prompt that names every failing photo
(Requirement 4.2); when every photo passes, the Grading_Pipeline is cleared to
proceed (Requirement 4.3).

Design constraints honored here:

* **Pure, framework-free logic.** This module imports only the Python standard
  library and the service-layer domain models. It performs no I/O and holds no
  AWS dependency, matching the "pure-ish blur + exposure assessment per photo;
  returns pass/fail with the failing photo identified" description in
  ``design.md``.
* **Dependency-light blur metric.** Blur is measured by the
  *variance-of-Laplacian* computed directly over a simple 2D grayscale
  intensity matrix (no OpenCV / numpy). A sharp image has strong second-order
  intensity changes (edges) and therefore a high Laplacian variance; a blurry
  image smooths those edges away, collapsing the variance toward zero.
* **Abstracted photo input.** A :class:`Photo` carries a stable ``key`` (used to
  name the failing photo in the retake prompt) and its grayscale ``pixels``.
  The bytes→grayscale-matrix decode is the responsibility of the caller
  (the worker adapter), keeping this layer free of image codecs.

The actual persistence of the ``RETAKE_REQUIRED`` status is performed by the
``GradingPipeline`` (it owns the ``ItemRepository``); this component expresses
the *decision* by returning :attr:`PrecheckResult.status` set to
``ItemStatus.RETAKE_REQUIRED`` on failure, so the pipeline can apply it directly.

Threshold assumptions (configurable via :class:`PrecheckConfig`):
``design.md`` mandates a variance-of-Laplacian blur check and an exposure check
but does not fix numeric thresholds, so sensible defaults are chosen for an
8-bit (0–255) grayscale scale and documented on :class:`PrecheckConfig`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from rebridge_service.models import ItemStatus

__all__ = [
    "Photo",
    "PrecheckConfig",
    "PhotoAssessment",
    "PrecheckResult",
    "QualityPrecheck",
    "variance_of_laplacian",
    "mean_brightness",
    "BLUR_REASON",
    "UNDEREXPOSED_REASON",
    "OVEREXPOSED_REASON",
]

# Canonical failure-reason identifiers attached to a failing photo.
BLUR_REASON = "blurry"
UNDEREXPOSED_REASON = "underexposed"
OVEREXPOSED_REASON = "overexposed"

# Human-readable phrasing for each reason, used to build the retake prompt.
_REASON_PHRASES = {
    BLUR_REASON: "too blurry",
    UNDEREXPOSED_REASON: "too dark",
    OVEREXPOSED_REASON: "too bright",
}

# Grayscale matrix type: row-major rows of intensity values on the 0–255 scale.
PixelMatrix = Sequence[Sequence[float]]


@dataclass(frozen=True)
class Photo:
    """A single submitted photo to be quality-checked.

    ``key`` is the stable identifier (an S3 object key, slot name, or
    ``"photo-<index>"``) echoed back in the retake prompt so the owner knows
    *which* photo to retake (Requirement 4.2). ``pixels`` is a row-major 2D
    grayscale intensity matrix on the 0–255 scale.
    """

    key: str
    pixels: PixelMatrix


@dataclass(frozen=True)
class PrecheckConfig:
    """Tunable blur / exposure thresholds for the precheck.

    Defaults target an 8-bit (0–255) grayscale scale:

    * ``min_blur_variance`` — the minimum acceptable variance-of-Laplacian. A
      photo whose blur score is *below* this is rejected as too blurry. ``100.0``
      is a widely used variance-of-Laplacian focus cutoff for natural photos.
    * ``min_brightness`` / ``max_brightness`` — the acceptable mean-intensity
      band. Below ``min_brightness`` the photo is underexposed (too dark); above
      ``max_brightness`` it is overexposed (too bright / washed out). ``40`` and
      ``220`` leave headroom at both ends of the 0–255 range while still
      flagging near-black and near-white frames.
    """

    min_blur_variance: float = 100.0
    min_brightness: float = 40.0
    max_brightness: float = 220.0

    def __post_init__(self) -> None:
        if self.min_blur_variance < 0:
            raise ValueError("min_blur_variance must be non-negative")
        if not (0.0 <= self.min_brightness <= self.max_brightness <= 255.0):
            raise ValueError(
                "brightness band must satisfy 0 <= min_brightness <= "
                "max_brightness <= 255"
            )


@dataclass(frozen=True)
class PhotoAssessment:
    """The per-photo result of the blur and lighting checks (Requirement 4.1)."""

    key: str
    blur_score: float
    brightness: float
    passed: bool
    failure_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PrecheckResult:
    """The aggregate precheck outcome for a submitted photo set.

    ``passed`` is True only when every photo passed both checks. On failure,
    ``status`` is :attr:`ItemStatus.RETAKE_REQUIRED`, ``failing_keys`` lists the
    offending photos in submission order, and ``retake_prompt`` is a
    ready-to-show message naming them (Requirement 4.2). On success ``status``
    is ``None`` and ``retake_prompt`` is ``None`` (Requirement 4.3).
    ``assessments`` always contains one entry per submitted photo, in order,
    proving every photo was assessed before any gating decision.
    """

    passed: bool
    assessments: tuple[PhotoAssessment, ...]
    failing_keys: tuple[str, ...] = ()
    status: ItemStatus | None = None
    retake_prompt: str | None = None


def _validate_matrix(pixels: PixelMatrix, where: str) -> tuple[int, int]:
    """Return ``(rows, cols)`` for a rectangular matrix or raise ``ValueError``."""
    rows = len(pixels)
    if rows == 0:
        return 0, 0
    cols = len(pixels[0])
    for r, row in enumerate(pixels):
        if len(row) != cols:
            raise ValueError(
                f"{where}: ragged pixel matrix (row {r} has {len(row)} columns, "
                f"expected {cols})"
            )
    return rows, cols


def variance_of_laplacian(pixels: PixelMatrix) -> float:
    """Compute the variance of the discrete Laplacian over a grayscale matrix.

    Uses the standard 4-neighbor Laplacian kernel::

        0  1  0
        1 -4  1
        0  1  0

    applied to every interior pixel (those with a full 3×3 neighborhood), then
    returns the population variance of the responses. Higher values indicate a
    sharper, more in-focus image. Matrices smaller than 3×3 have no interior
    pixel and yield ``0.0`` (treated as maximally blurry, i.e. unusable).
    """
    rows, cols = _validate_matrix(pixels, "variance_of_laplacian")
    if rows < 3 or cols < 3:
        return 0.0

    responses: list[float] = []
    for r in range(1, rows - 1):
        prev_row = pixels[r - 1]
        cur_row = pixels[r]
        next_row = pixels[r + 1]
        for c in range(1, cols - 1):
            laplacian = (
                prev_row[c]
                + next_row[c]
                + cur_row[c - 1]
                + cur_row[c + 1]
                - 4.0 * cur_row[c]
            )
            responses.append(laplacian)

    n = len(responses)
    if n == 0:
        return 0.0
    mean = sum(responses) / n
    return sum((value - mean) ** 2 for value in responses) / n


def mean_brightness(pixels: PixelMatrix) -> float:
    """Return the mean grayscale intensity (exposure proxy) of a matrix.

    An empty matrix yields ``0.0`` (treated as fully underexposed).
    """
    _validate_matrix(pixels, "mean_brightness")
    total = 0.0
    count = 0
    for row in pixels:
        for value in row:
            total += value
            count += 1
    if count == 0:
        return 0.0
    return total / count


class QualityPrecheck:
    """Assess photos for blur and lighting before grading (Requirement 4).

    Construct with an optional :class:`PrecheckConfig` to override the default
    thresholds (the composition root passes configured values). The component is
    stateless and side-effect free; call :meth:`assess` per submitted photo set.
    """

    def __init__(self, config: PrecheckConfig | None = None) -> None:
        self._config = config or PrecheckConfig()

    @property
    def config(self) -> PrecheckConfig:
        return self._config

    def assess_photo(self, photo: Photo) -> PhotoAssessment:
        """Assess a single photo for blur and exposure (Requirement 4.1)."""
        blur_score = variance_of_laplacian(photo.pixels)
        brightness = mean_brightness(photo.pixels)

        reasons: list[str] = []
        if blur_score < self._config.min_blur_variance:
            reasons.append(BLUR_REASON)
        if brightness < self._config.min_brightness:
            reasons.append(UNDEREXPOSED_REASON)
        elif brightness > self._config.max_brightness:
            reasons.append(OVEREXPOSED_REASON)

        return PhotoAssessment(
            key=photo.key,
            blur_score=blur_score,
            brightness=brightness,
            passed=not reasons,
            failure_reasons=tuple(reasons),
        )

    def assess(self, photos: Sequence[Photo]) -> PrecheckResult:
        """Assess every photo in a submitted set and gate grading.

        Every photo is assessed (no short-circuit) so the retake prompt can name
        *all* failing photos and so the "assess each photo before grading"
        guarantee holds (Requirement 4.1). If any photo fails, the result
        carries ``ItemStatus.RETAKE_REQUIRED`` and a retake prompt
        (Requirement 4.2); otherwise it passes (Requirement 4.3).
        """
        if not photos:
            raise ValueError("a photo set must contain at least one photo")

        assessments = tuple(self.assess_photo(photo) for photo in photos)
        failing = tuple(a for a in assessments if not a.passed)

        if not failing:
            return PrecheckResult(passed=True, assessments=assessments)

        failing_keys = tuple(a.key for a in failing)
        return PrecheckResult(
            passed=False,
            assessments=assessments,
            failing_keys=failing_keys,
            status=ItemStatus.RETAKE_REQUIRED,
            retake_prompt=_build_retake_prompt(failing),
        )


def _build_retake_prompt(failing: Sequence[PhotoAssessment]) -> str:
    """Build a retake prompt naming each failing photo and why it failed."""
    parts: list[str] = []
    for assessment in failing:
        phrases = [
            _REASON_PHRASES.get(reason, reason) for reason in assessment.failure_reasons
        ]
        why = " and ".join(phrases) if phrases else "unusable"
        parts.append(f"'{assessment.key}' ({why})")
    listed = ", ".join(parts)
    return f"Please retake the following photo(s) before grading: {listed}."
