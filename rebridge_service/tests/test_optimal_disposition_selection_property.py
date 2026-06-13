"""Property-based test for optimal disposition selection.

# Feature: rebridge-backend, Property 16: Optimal disposition selection

Property 16 (design.md): *For any* combination of recoverable value and
per-path handling costs over {RESELL, REFURB, P2P, DONATE}, the Routing_Agent
SHALL select the path with maximum margin among paths whose value exceeds cost;
SHALL break ties toward the faster customer outcome (P2P over RESELL); and SHALL
select DONATE when no non-donate path has value greater than cost.

**Validates: Requirements 10.4, 10.5, 10.6**

This generates arbitrary value/cost maps over all four dispositions (spanning
the positive, zero, and negative margin regions, plus exact-margin ties) and
asserts that :func:`select_disposition` agrees with an independent brute-force
oracle: DONATE iff no non-donate path is profitable; otherwise an eligible
(value > cost) non-donate path whose margin is maximal, ties broken by the
lower customer-outcome speed rank (P2P over RESELL over REFURB).
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.models import Disposition
from rebridge_service.routing_agent import (
    DISPOSITION_SPEED_RANK,
    NON_DONATE_DISPOSITIONS,
    select_disposition,
)


# Money amounts with cents precision spanning a band that straddles every sign
# region so values can fall below, equal, or above their paired cost. A small,
# discrete-ish range deliberately makes exact-margin ties (Req 10.5) common.
_amount = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def _disposition_map():
    """A value (or cost) map assigning an amount to every Disposition."""

    return st.fixed_dictionaries(
        {disposition: _amount for disposition in Disposition}
    )


def _oracle(
    path_values: dict[Disposition, Decimal],
    path_costs: dict[Disposition, Decimal],
) -> Disposition:
    """Independent brute-force reference for the selection rule (Req 10.4-10.6).

    Enumerates the eligible non-donate paths (value strictly greater than cost),
    falls back to DONATE when none qualify, and otherwise picks the maximal
    margin breaking ties toward the lower speed rank (the faster customer
    outcome). Written without reusing the implementation's sort key so it is a
    genuinely independent check.
    """

    eligible = [
        d
        for d in NON_DONATE_DISPOSITIONS
        if path_values[d] > path_costs[d]
    ]
    if not eligible:
        return Disposition.DONATE

    best = eligible[0]
    best_margin = path_values[best] - path_costs[best]
    for d in eligible[1:]:
        margin = path_values[d] - path_costs[d]
        if margin > best_margin:
            best, best_margin = d, margin
        elif margin == best_margin and (
            DISPOSITION_SPEED_RANK[d] < DISPOSITION_SPEED_RANK[best]
        ):
            best = d
    return best


@settings(max_examples=200)
@given(values=_disposition_map(), costs=_disposition_map())
def test_select_disposition_matches_bruteforce_oracle(values, costs):
    chosen = select_disposition(values, costs)

    # 1) Agreement with the independent oracle across all sign regions and ties.
    assert chosen == _oracle(values, costs)

    eligible = [d for d in NON_DONATE_DISPOSITIONS if values[d] > costs[d]]

    if not eligible:
        # 2) DONATE iff no non-donate path has value greater than cost (Req 10.6).
        assert chosen is Disposition.DONATE
    else:
        # 3) The choice is an eligible non-donate path (Req 10.4)...
        assert chosen in eligible
        chosen_margin = values[chosen] - costs[chosen]
        best_margin = max(values[d] - costs[d] for d in eligible)
        # ...whose margin is maximal among eligible paths (Req 10.4)...
        assert chosen_margin == best_margin
        # ...and among equal-maximal-margin paths it is the faster customer
        # outcome, i.e. the minimum speed rank (Req 10.5).
        tied = [d for d in eligible if values[d] - costs[d] == best_margin]
        assert DISPOSITION_SPEED_RANK[chosen] == min(
            DISPOSITION_SPEED_RANK[d] for d in tied
        )
