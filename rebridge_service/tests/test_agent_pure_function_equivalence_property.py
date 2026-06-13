"""Property-based test for agent/pure-function routing equivalence.

# Feature: rebridge-backend, Property 18: Agent and pure-function routing equivalence

Property 18 (design.md): *For any* Item, the decision output structure produced
by the agent-framework strategy SHALL equal the decision output structure
produced by the pure-function fallback strategy.

**Validates: Requirements 10.8**

This generates arbitrary :class:`RoutingContext` values -- a price band with
arbitrary low/point/high amounts plus independent recovered-value and
handling-cost maps over every :class:`Disposition` -- and asserts that the
agent-framework strategy and the pure-function fallback strategy return an
*identical* :class:`RoutingDecision` for the same context, across every sign
region and exact-margin tie. The inputs span the donate-fallback, clear-winner,
and tie-break cases so the equivalence is exercised over the whole decision
space, not just the happy path.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from rebridge_service.models import Disposition, RoutingDecision
from rebridge_service.routing_agent import (
    AgentRoutingStrategy,
    PureFunctionRoutingStrategy,
    RoutingContext,
)
from rebridge_service.routing_tools import PriceBand


# Money amounts with cents precision over a band that straddles every sign
# region, so any path's value can fall below, equal, or above its paired cost.
# The small discrete-ish range deliberately makes exact-margin ties (the
# tie-break case) common, stressing the part of the selection most likely to
# diverge between two implementations.
_amount = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def _disposition_map() -> st.SearchStrategy[dict[Disposition, Decimal]]:
    """A value (or cost) map assigning an amount to every Disposition."""

    return st.fixed_dictionaries(
        {disposition: _amount for disposition in Disposition}
    )


@st.composite
def _price_bands(draw: st.DrawFn) -> PriceBand:
    """An arbitrary recoverable price band with cents-precision amounts."""

    low = draw(_amount)
    high = draw(_amount)
    point = draw(_amount)
    return PriceBand(
        category=draw(st.sampled_from(["electronics", "apparel", "home", "_default"])),
        grade=draw(st.sampled_from(["Like New", "Very Good", "Good", "Acceptable"])),
        age_bucket=draw(st.sampled_from(["0-6", "7-12", "13-24", "25+"])),
        low=low,
        high=high,
        point=point,
    )


@st.composite
def _routing_contexts(draw: st.DrawFn) -> RoutingContext:
    """A fully-resolved routing context over an arbitrary band + value/cost."""

    return RoutingContext(
        item_id=draw(st.text(min_size=1, max_size=12)),
        price_band=draw(_price_bands()),
        path_values=draw(_disposition_map()),
        path_costs=draw(_disposition_map()),
    )


@settings(max_examples=200)
@given(ctx=_routing_contexts())
def test_agent_and_pure_function_strategies_are_equivalent(ctx):
    agent_decision = AgentRoutingStrategy().decide(ctx)
    pure_decision = PureFunctionRoutingStrategy().decide(ctx)

    # Identical decision output structure for the same Item (Req 10.8).
    assert agent_decision == pure_decision
    # Both strategies produce a well-formed decision (not, say, None).
    assert isinstance(agent_decision, RoutingDecision)
    assert isinstance(pure_decision, RoutingDecision)
