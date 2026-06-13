"""Confidence gating: auto-continue vs human-review decision.

This module implements the pure decision logic of Requirement 6 (Confidence
Gating). It compares a grade assessment's ``Confidence_Score`` against the
configured ``Confidence_Threshold`` and decides whether the Grading_Pipeline
should auto-continue (persist the grade and proceed to event emission) or route
the item to human review.

Requirement traceability:
- 6.1: WHEN confidence >= threshold, the pipeline auto-continues. The boundary
  is inclusive: a confidence *equal* to the threshold auto-continues.
- 6.2: IF confidence < threshold, the pipeline routes the item to review
  (status PENDING_REVIEW + Review_Queue entry).
- 6.3: the threshold is read from configuration with a default value of 0.80.

The :class:`ConfidenceGate` is intentionally a pure, dependency-free decision
component: it performs no persistence and emits no events. It receives its
threshold via the constructor (the composition root injects the configured
value), and returns a small typed :class:`GateDecision`. The orchestrating
``GradingPipeline`` acts on that decision (persist + continue, or set
PENDING_REVIEW + enqueue review).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "GateOutcome",
    "GateDecision",
    "ConfidenceGate",
]


# Requirement 6.3: the default Confidence_Threshold when configuration does not
# supply one.
DEFAULT_CONFIDENCE_THRESHOLD: float = 0.80


class GateOutcome(Enum):
    """The two mutually-exclusive outcomes of the confidence gate.

    ``AUTO_CONTINUE`` means the grade is sufficiently certain to persist and
    continue to event emission (Requirement 6.1). ``ROUTE_TO_REVIEW`` means the
    grade is below threshold and the item must go to human review
    (Requirement 6.2).
    """

    AUTO_CONTINUE = "AUTO_CONTINUE"
    ROUTE_TO_REVIEW = "ROUTE_TO_REVIEW"


@dataclass(frozen=True)
class GateDecision:
    """The typed result of a confidence-gate evaluation.

    Carries the ``outcome`` plus the ``confidence`` and ``threshold`` that
    produced it, so callers (and logs/rationale) can see the comparison that was
    made without re-deriving it. ``auto_continue`` is a convenience flag
    equivalent to ``outcome is GateOutcome.AUTO_CONTINUE``.
    """

    outcome: GateOutcome
    confidence: float
    threshold: float

    @property
    def auto_continue(self) -> bool:
        """True when the grade auto-continues (confidence >= threshold)."""

        return self.outcome is GateOutcome.AUTO_CONTINUE

    @property
    def route_to_review(self) -> bool:
        """True when the grade must be routed to human review."""

        return self.outcome is GateOutcome.ROUTE_TO_REVIEW


class ConfidenceGate:
    """Decides auto-continue vs human-review from a confidence score.

    The threshold is injected via the constructor (Requirement 6.3); when
    omitted it defaults to :data:`DEFAULT_CONFIDENCE_THRESHOLD` (0.80). The gate
    is stateless and may be reused across many evaluations.
    """

    def __init__(self, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        # Reject bool explicitly (bool is a subclass of int) and non-numbers, so
        # a misconfigured threshold fails fast at construction rather than
        # silently mis-gating every grade.
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError(
                f"threshold must be a number, got {type(threshold).__name__}"
            )
        threshold = float(threshold)
        if threshold != threshold:  # NaN
            raise ValueError("threshold must be a finite number, got NaN")
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(
                f"threshold must be within the closed interval [0, 1], got {threshold}"
            )
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        """The configured Confidence_Threshold this gate compares against."""

        return self._threshold

    def decide(self, confidence: float) -> GateDecision:
        """Return the gate decision for a given ``confidence`` score.

        ``confidence`` must be a real number in the closed interval [0, 1]
        (the Confidence_Score invariant, Requirement 5.4). When ``confidence``
        is greater than or equal to the configured threshold the outcome is
        ``AUTO_CONTINUE`` (Requirement 6.1, inclusive boundary); otherwise it is
        ``ROUTE_TO_REVIEW`` (Requirement 6.2).
        """

        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError(
                f"confidence must be a number, got {type(confidence).__name__}"
            )
        confidence = float(confidence)
        if confidence != confidence:  # NaN
            raise ValueError("confidence must be a finite number, got NaN")
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(
                f"confidence must be within the closed interval [0, 1], got {confidence}"
            )

        outcome = (
            GateOutcome.AUTO_CONTINUE
            if confidence >= self._threshold
            else GateOutcome.ROUTE_TO_REVIEW
        )
        return GateDecision(
            outcome=outcome, confidence=confidence, threshold=self._threshold
        )
