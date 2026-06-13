"""Property-based test for decision-rationale unit economics.

# Feature: rebridge-backend, Property 17: Decision rationale exposes the unit economics

Property 17 (design.md): *For any* routing decision, the persisted DECISION
facet SHALL contain the selected disposition, a price, and a rationale string
stating the recovered value, total handling cost, and resulting margin.

**Validates: Requirements 10.7**

This generates arbitrary per-path value/cost maps over all four dispositions
(spanning the profitable, break-even, and donate-fallback regions) and asserts
that the :class:`~rebridge_service.models.RoutingDecision` produced by
:func:`evaluate_routing` exposes the chosen path's economics: the rationale
string contains the chosen value, cost, and margin formatted exactly as they
appear (``$X.XX``), and the decision's ``margin`` equals ``value - cost``.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.models import Disposition, RoutingDecision
from rebridge_service.routing_agent import RoutingContext, evaluate_routing
from rebridge_service.routing_tools import PriceBand


# Money amounts with cents precision spanning a band that straddles every sign
# region so chosen paths span profitable, break-even, and donate-fallback
# outcomes. Matches the generator used by the Property 16 selection test.
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


def _fmt(amount: Decimal) -> str:
    """Format a money amount exactly as the rationale builder does (``$X.XX``).

    Mirrors :func:`rebridge_service.routing_agent._fmt`: quantize to two decimal
    places and prefix ``$``. Written independently so the test asserts the money
    amounts surface "as they appear" rather than reusing private helpers.
    """

    return f"${amount.quantize(Decimal('0.01'))}"


@settings(max_examples=200)
@given(
    values=_disposition_map(),
    costs=_disposition_map(),
    point=_amount,
)
def test_rationale_exposes_chosen_path_economics(values, costs, point):
    ctx = RoutingContext(
        item_id="item-1",
        price_band=PriceBand(
            category="electronics",
            grade="Good",
            age_bucket="7-12",
            low=point,
            high=point,
            point=point,
        ),
        path_values=values,
        path_costs=costs,
    )

    decision = evaluate_routing(ctx)

    assert isinstance(decision, RoutingDecision)

    # 1) The decision's economics are internally consistent: margin = value - cost.
    assert decision.margin == decision.value - decision.cost

    # 2) The chosen path's value/cost are the ones reported on the decision.
    assert decision.value == values[decision.disposition]
    assert decision.cost == costs[decision.disposition]

    # 3) The rationale states the recovered value, handling cost, and margin,
    #    each formatted exactly as it appears on the decision (``$X.XX``).
    assert _fmt(decision.value) in decision.rationale
    assert _fmt(decision.cost) in decision.rationale
    assert _fmt(decision.margin) in decision.rationale

    # 4) The rationale also names the selected disposition (Req 10.7).
    assert decision.disposition.value in decision.rationale
