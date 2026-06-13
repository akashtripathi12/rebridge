"""Unit tests for the ConfidenceGate decision logic.

Covers Requirement 6:
- 6.1: confidence >= threshold auto-continues (inclusive boundary).
- 6.2: confidence < threshold routes to review.
- 6.3: default threshold is 0.80 and is injectable via the constructor.

The exact boundary behavior (confidence == threshold auto-continues) is tested
explicitly, since that is the one place an off-by-one comparison would hide.
"""

from __future__ import annotations

import pytest

from rebridge_service.confidence_gate import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ConfidenceGate,
    GateDecision,
    GateOutcome,
)


def test_default_threshold_is_080():
    # Requirement 6.3: default Confidence_Threshold is 0.80.
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.80
    assert ConfidenceGate().threshold == 0.80


def test_threshold_is_injectable():
    # Requirement 6.3: threshold read from config (injected via constructor).
    assert ConfidenceGate(threshold=0.5).threshold == 0.5
    assert ConfidenceGate(0.95).threshold == 0.95


def test_confidence_equal_to_threshold_auto_continues():
    # Requirement 6.1: the boundary is inclusive (>= threshold).
    decision = ConfidenceGate(threshold=0.80).decide(0.80)
    assert decision.outcome is GateOutcome.AUTO_CONTINUE
    assert decision.auto_continue is True
    assert decision.route_to_review is False


def test_confidence_just_below_threshold_routes_to_review():
    # Requirement 6.2: strictly-below threshold goes to review.
    decision = ConfidenceGate(threshold=0.80).decide(0.7999999)
    assert decision.outcome is GateOutcome.ROUTE_TO_REVIEW
    assert decision.route_to_review is True
    assert decision.auto_continue is False


def test_confidence_above_threshold_auto_continues():
    # Requirement 6.1.
    decision = ConfidenceGate(threshold=0.80).decide(0.95)
    assert decision.outcome is GateOutcome.AUTO_CONTINUE


def test_boundary_with_default_threshold():
    # The default-constructed gate also auto-continues exactly at 0.80.
    assert ConfidenceGate().decide(0.80).auto_continue is True
    assert ConfidenceGate().decide(0.79).route_to_review is True


@pytest.mark.parametrize(
    ("threshold", "confidence", "expected"),
    [
        (0.0, 0.0, GateOutcome.AUTO_CONTINUE),  # everything auto-continues at 0
        (1.0, 1.0, GateOutcome.AUTO_CONTINUE),  # only perfect certainty passes
        (1.0, 0.999, GateOutcome.ROUTE_TO_REVIEW),
        (0.5, 0.5, GateOutcome.AUTO_CONTINUE),
        (0.5, 0.4999, GateOutcome.ROUTE_TO_REVIEW),
    ],
)
def test_decision_matrix(threshold, confidence, expected):
    assert ConfidenceGate(threshold).decide(confidence).outcome is expected


def test_decision_carries_comparison_inputs():
    decision = ConfidenceGate(threshold=0.80).decide(0.42)
    assert isinstance(decision, GateDecision)
    assert decision.confidence == 0.42
    assert decision.threshold == 0.80


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        ConfidenceGate(threshold=1.5)
    with pytest.raises(ValueError):
        ConfidenceGate(threshold=-0.1)
    with pytest.raises(ValueError):
        ConfidenceGate(threshold=True)  # bool is not a valid threshold
    with pytest.raises(ValueError):
        ConfidenceGate(threshold="0.8")  # type: ignore[arg-type]


def test_invalid_confidence_rejected():
    gate = ConfidenceGate()
    with pytest.raises(ValueError):
        gate.decide(1.5)
    with pytest.raises(ValueError):
        gate.decide(-0.01)
    with pytest.raises(ValueError):
        gate.decide(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        gate.decide(float("nan"))


# ---------------------------------------------------------------------------
# Task 7.2: focused unit tests for confidence threshold *configuration*.
#
# These tests target Requirement 6.3 specifically: the default threshold value
# of 0.80 and the exact boundary behavior at the threshold. They complement the
# broader decision tests above by (a) exercising the config-default semantics
# through a config-style accessor, (b) pinning the boundary against the actual
# *configured* threshold value (not a duplicated literal) across several
# thresholds, and (c) using math.nextafter for an exact, representation-precise
# just-below check rather than an approximate decimal.
# ---------------------------------------------------------------------------

import math


def _gate_from_config(config: dict) -> ConfidenceGate:
    """Build a gate the way the composition root would: read the threshold from
    configuration, falling back to the default when unset (Requirement 6.3)."""

    return ConfidenceGate(
        threshold=config.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)
    )


class TestThresholdConfiguration:
    def test_absent_config_uses_default_080(self):
        # Requirement 6.3: missing config -> default Confidence_Threshold 0.80.
        gate = _gate_from_config({})
        assert gate.threshold == 0.80

    def test_present_config_overrides_default(self):
        # Requirement 6.3: configured value takes precedence over the default.
        gate = _gate_from_config({"confidence_threshold": 0.65})
        assert gate.threshold == 0.65

    def test_default_constant_is_exactly_080(self):
        # The default is exactly 0.80, not merely close to it.
        assert DEFAULT_CONFIDENCE_THRESHOLD == 0.80
        assert ConfidenceGate().threshold == DEFAULT_CONFIDENCE_THRESHOLD


class TestExactBoundaryAtConfiguredThreshold:
    @pytest.mark.parametrize(
        "threshold",
        [0.0, 0.25, 0.5, DEFAULT_CONFIDENCE_THRESHOLD, 0.9, 1.0],
    )
    def test_confidence_exactly_at_configured_threshold_auto_continues(self, threshold):
        # Requirement 6.1: the boundary is inclusive. Deciding at exactly the
        # gate's own configured threshold value must auto-continue.
        gate = ConfidenceGate(threshold=threshold)
        decision = gate.decide(gate.threshold)
        assert decision.auto_continue is True
        assert decision.outcome is GateOutcome.AUTO_CONTINUE

    @pytest.mark.parametrize(
        "threshold",
        [0.25, 0.5, DEFAULT_CONFIDENCE_THRESHOLD, 0.9, 1.0],
    )
    def test_smallest_representable_value_below_threshold_routes_to_review(
        self, threshold
    ):
        # Requirement 6.2: the *next* representable double below the threshold
        # (an exact, not approximate, just-below value) must route to review.
        gate = ConfidenceGate(threshold=threshold)
        just_below = math.nextafter(threshold, 0.0)
        decision = gate.decide(just_below)
        assert decision.route_to_review is True
        assert decision.outcome is GateOutcome.ROUTE_TO_REVIEW

    def test_default_threshold_boundary_is_exact(self):
        # The default-configured gate: exactly 0.80 passes, the next double
        # below 0.80 does not.
        gate = ConfidenceGate()
        assert gate.decide(0.80).auto_continue is True
        assert gate.decide(math.nextafter(0.80, 0.0)).route_to_review is True
