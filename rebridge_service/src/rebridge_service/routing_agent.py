"""RoutingAgent: unit-economics disposition selection (Requirement 10).

This module implements the service-layer business logic that turns a graded
Item into a disposition decision driven by unit economics (design.md ->
"Components and Interfaces -> Service Layer -> RoutingAgent"; Requirements
10.4-10.8). It is programmed entirely against the abstract
:mod:`rebridge_data.interfaces` (``ItemRepository``) and the pure routing tools
in :mod:`rebridge_service.routing_tools` (``PriceEstimator``, ``CostModel``,
``DemandProbe``); it never imports boto3 or any web framework.

### The decision

For a graded Item the agent:

1. estimates a recoverable price band from ``(category, grade, age)`` via the
   :class:`~rebridge_service.routing_tools.PriceEstimator` (Requirement 10.1);
2. computes the per-path recovered value and the total handling cost of each
   candidate disposition in ``{RESELL, REFURB, P2P, DONATE}`` via the
   :class:`~rebridge_service.routing_tools.CostModel` (Requirement 10.2);
3. selects the disposition with the **maximum margin** (value - cost) among the
   non-donate paths whose recovered value exceeds their handling cost; breaks
   ties toward the **faster customer outcome** (P2P over RESELL); and falls back
   to **DONATE** when no non-donate path recovers more than its cost
   (Requirements 10.4, 10.5, 10.6);
4. persists a DECISION facet carrying the disposition, a price, and a one-line
   rationale stating the recovered value, total handling cost, and resulting
   margin (Requirement 10.7).

### Two strategies, one output (Requirement 10.8)

The selection logic lives behind a single :class:`RoutingStrategy` interface
with two interchangeable implementations:

* :class:`PureFunctionRoutingStrategy` — the deterministic pure-function policy.
* :class:`AgentRoutingStrategy` — the agent-framework path (LangGraph in the
  deployed system); in this framework-free core it walks the same gather ->
  evaluate -> select steps an agent would, recording a small trace, but
  **delegates the final selection to the identical shared core**.

Because both strategies route their final selection through the single
module-level :func:`evaluate_routing` function, they produce an *identical*
:class:`~rebridge_service.models.RoutingDecision` output structure for the same
inputs (Requirement 10.8, Property 18). Selection never depends on which
strategy is used.

All money math uses :class:`decimal.Decimal` (carried through from the routing
tools) to avoid binary-float rounding in the margin comparison.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Mapping

from rebridge_data.interfaces import ItemRepository
from rebridge_data.models import DecisionRecord

from rebridge_service.models import Disposition, Grade, RoutingDecision
from rebridge_service.routing_tools import (
    CostModel,
    DemandProbe,
    DemandSignal,
    PriceBand,
    PriceEstimator,
)

__all__ = [
    "NON_DONATE_DISPOSITIONS",
    "DISPOSITION_SPEED_RANK",
    "RoutingError",
    "ItemNotFound",
    "GradeRequired",
    "RoutingContext",
    "default_path_values",
    "select_disposition",
    "evaluate_routing",
    "RoutingStrategy",
    "PureFunctionRoutingStrategy",
    "AgentRoutingStrategy",
    "RoutingAgent",
]


# The three non-donate candidate paths considered before the donate fallback
# (Requirement 10.4). DONATE is the always-available fallback (Requirement 10.6).
NON_DONATE_DISPOSITIONS: tuple[Disposition, ...] = (
    Disposition.RESELL,
    Disposition.REFURB,
    Disposition.P2P,
)

# Customer-outcome speed ranking used only to break exact margin ties
# (Requirement 10.5). A *lower* rank is a faster customer outcome and is
# preferred. Peer-to-peer is the fastest local handoff; resell is next; refurb
# adds reconditioning time; donate is last. The requirement names P2P over
# RESELL explicitly; the full ordering makes the tie-break total and
# deterministic for any pair.
DISPOSITION_SPEED_RANK: dict[Disposition, int] = {
    Disposition.P2P: 0,
    Disposition.RESELL: 1,
    Disposition.REFURB: 2,
    Disposition.DONATE: 3,
}


def _money(value: Decimal | int | str) -> Decimal:
    """Coerce a value to :class:`~decimal.Decimal` for the margin math."""

    return value if isinstance(value, Decimal) else Decimal(str(value))


def _fmt(amount: Decimal) -> str:
    """Format a money amount to two decimal places for the rationale string."""

    return f"${_money(amount).quantize(Decimal('0.01'))}"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RoutingError(Exception):
    """Base class for errors raised by :class:`RoutingAgent`."""


class ItemNotFound(RoutingError):
    """No Item exists for the requested identifier."""

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"unknown item: {item_id}")


class GradeRequired(RoutingError):
    """Routing was requested for an Item that has no persisted grade (Req 10.1)."""

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(
            f"cannot route an item before it is graded: {item_id}"
        )


# ---------------------------------------------------------------------------
# Routing context + value model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingContext:
    """The fully-resolved economics a strategy needs to make a decision.

    ``price_band`` is the recoverable band from the Price_Estimator (its
    ``point`` is the headline recoverable price). ``path_values`` and
    ``path_costs`` map every candidate :class:`Disposition` to its recovered
    value and total handling cost respectively. ``demand`` is the optional
    seeded neighborhood demand signal (Requirement 10.3); it enriches the
    rationale but does not change the margin-based selection.
    """

    item_id: str
    price_band: PriceBand
    path_values: Mapping[Disposition, Decimal]
    path_costs: Mapping[Disposition, Decimal]
    demand: DemandSignal | None = None


def default_path_values(price_band: PriceBand) -> dict[Disposition, Decimal]:
    """Default per-path recovered value from a price band.

    * RESELL and P2P recover the band's central ``point`` estimate (a standard
      resale at the estimated market price).
    * REFURB recovers the band's ``high`` estimate (a reconditioned unit
      commands the top of the band; its added reconditioning cost is captured
      separately in the Cost_Model's ``extra``).
    * DONATE recovers no resale value (``0``) — it is the fallback that exists
      to clear items no path can resell profitably (Requirement 10.6).
    """

    return {
        Disposition.RESELL: _money(price_band.point),
        Disposition.REFURB: _money(price_band.high),
        Disposition.P2P: _money(price_band.point),
        Disposition.DONATE: Decimal("0"),
    }


# ---------------------------------------------------------------------------
# Core selection (shared by both strategies -> identical output, Req 10.8)
# ---------------------------------------------------------------------------


def select_disposition(
    path_values: Mapping[Disposition, Decimal],
    path_costs: Mapping[Disposition, Decimal],
) -> Disposition:
    """Select the disposition by argmax margin with the donate fallback.

    Implements Requirements 10.4-10.6 (Property 16):

    * Consider the non-donate paths ``{RESELL, REFURB, P2P}`` whose recovered
      value strictly exceeds their total handling cost.
    * Among those, choose the one with the maximum margin (value - cost).
    * Break exact margin ties toward the faster customer outcome — the lower
      :data:`DISPOSITION_SPEED_RANK` (P2P over RESELL) (Requirement 10.5).
    * If no non-donate path has value greater than cost, select DONATE
      (Requirement 10.6).
    """

    eligible = [
        d
        for d in NON_DONATE_DISPOSITIONS
        if _money(path_values[d]) > _money(path_costs[d])
    ]
    if not eligible:
        return Disposition.DONATE

    # Maximize margin; on an exact tie prefer the faster customer outcome
    # (a lower speed rank, hence the negation so ``max`` favors it).
    def sort_key(d: Disposition) -> tuple[Decimal, int]:
        margin = _money(path_values[d]) - _money(path_costs[d])
        return (margin, -DISPOSITION_SPEED_RANK[d])

    return max(eligible, key=sort_key)


def _build_rationale(
    chosen: Disposition,
    value: Decimal,
    cost: Decimal,
    margin: Decimal,
    *,
    donate_fallback: bool,
) -> str:
    """Compose the one-line rationale stating value, cost, and margin (10.7)."""

    economics = (
        f"recovered value {_fmt(value)}, "
        f"handling cost {_fmt(cost)}, "
        f"margin {_fmt(margin)}"
    )
    if donate_fallback:
        return (
            f"{chosen.value} selected: no non-donate path recovers more than "
            f"its handling cost, so the item is donated ({economics})."
        )
    return (
        f"{chosen.value} selected: highest-margin viable path ({economics})."
    )


def evaluate_routing(ctx: RoutingContext) -> RoutingDecision:
    """Produce the :class:`RoutingDecision` for a routing context.

    This is the single shared selection-and-rationale core both strategies call,
    which is what makes the agent and pure-function strategies produce identical
    output (Requirement 10.8, Property 18). The returned decision carries the
    selected disposition, the headline recoverable ``price`` (the band point),
    and the chosen path's ``value``/``cost``/``margin`` plus a rationale stating
    that math (Requirement 10.7).
    """

    chosen = select_disposition(ctx.path_values, ctx.path_costs)
    value = _money(ctx.path_values[chosen])
    cost = _money(ctx.path_costs[chosen])
    margin = value - cost
    donate_fallback = chosen is Disposition.DONATE

    return RoutingDecision(
        disposition=chosen,
        price=_money(ctx.price_band.point),
        value=value,
        cost=cost,
        margin=margin,
        rationale=_build_rationale(
            chosen, value, cost, margin, donate_fallback=donate_fallback
        ),
    )


# ---------------------------------------------------------------------------
# Strategies (Requirement 10.8)
# ---------------------------------------------------------------------------


class RoutingStrategy(ABC):
    """The interchangeable disposition-selection seam (Requirement 10.8).

    Implementations turn a fully-resolved :class:`RoutingContext` into a
    :class:`RoutingDecision`. Both shipped implementations route their final
    selection through :func:`evaluate_routing`, so their output structure is
    identical for identical inputs.
    """

    name: str = "routing-strategy"

    @abstractmethod
    def decide(self, ctx: RoutingContext) -> RoutingDecision:
        """Return the routing decision for ``ctx``."""


class PureFunctionRoutingStrategy(RoutingStrategy):
    """The deterministic pure-function routing policy.

    A thin, side-effect-free wrapper over :func:`evaluate_routing`. This is the
    reference policy and the always-available fallback when the agent framework
    is unavailable.
    """

    name = "pure-function"

    def decide(self, ctx: RoutingContext) -> RoutingDecision:
        return evaluate_routing(ctx)


class AgentRoutingStrategy(RoutingStrategy):
    """The agent-framework routing path (LangGraph in the deployed system).

    In the framework-free service core this strategy walks the same
    gather -> evaluate -> select steps an agent graph would, recording a small
    human-readable :attr:`trace` for observability, but delegates the final
    selection to the *identical* shared core (:func:`evaluate_routing`). Routing
    the decision through the same core is what guarantees it produces an output
    structure identical to :class:`PureFunctionRoutingStrategy` for the same
    inputs (Requirement 10.8, Property 18).
    """

    name = "agent"

    def __init__(self) -> None:
        self.trace: list[str] = []

    def decide(self, ctx: RoutingContext) -> RoutingDecision:
        # Agent-style deliberation steps. These are observational only; the
        # decision itself is produced by the shared core so it cannot diverge
        # from the pure-function strategy.
        self.trace = [
            f"observe: price band point {_fmt(ctx.price_band.point)}",
            "evaluate margins for {}".format(
                ", ".join(d.value for d in NON_DONATE_DISPOSITIONS)
            ),
        ]
        if ctx.demand is not None:
            self.trace.append(
                f"observe: demand {ctx.demand.level} ({ctx.demand.index:.2f})"
            )
        decision = evaluate_routing(ctx)
        self.trace.append(f"select: {decision.disposition.value}")
        return decision


# ---------------------------------------------------------------------------
# RoutingAgent
# ---------------------------------------------------------------------------


@dataclass
class RoutingAgent:
    """Computes unit economics and persists a disposition decision (Req 10).

    Collaborators are injected: the :class:`RoutingStrategy` (which selection
    policy to run), the pure routing tools (:class:`PriceEstimator`,
    :class:`CostModel`, and the optional :class:`DemandProbe`), and the
    :class:`~rebridge_data.interfaces.ItemRepository` used to read the graded
    Item and persist the DECISION facet. ``value_model`` maps a price band to
    per-path recovered values and defaults to :func:`default_path_values`.

    ``strategy`` defaults to :class:`PureFunctionRoutingStrategy` so the agent
    is usable without the agent framework; the composition root injects the
    configured strategy. Whichever strategy is used, the decision output is
    identical (Requirement 10.8).
    """

    price: PriceEstimator
    cost: CostModel
    item_repo: ItemRepository
    strategy: RoutingStrategy = field(default_factory=PureFunctionRoutingStrategy)
    demand: DemandProbe | None = None
    value_model: Callable[[PriceBand], Mapping[Disposition, Decimal]] = (
        default_path_values
    )

    def decide(self, item_id: str, *, geohash5: str | None = None) -> RoutingDecision:
        """Route a graded Item and persist its DECISION facet (Req 10.4-10.7).

        Reads the Item's META and GRADE facets, estimates the recoverable price
        band, computes per-path value and cost, selects a disposition via the
        configured strategy, persists the DECISION facet, and returns the
        decision. Raises :class:`ItemNotFound` for an unknown Item and
        :class:`GradeRequired` for an Item with no persisted grade
        (Requirement 10.1). ``geohash5``, when supplied alongside a configured
        :class:`DemandProbe`, is used only to attach a demand signal to the
        decision context (Requirement 10.3); it never changes the selection.
        """

        ctx = self.build_context(item_id, geohash5=geohash5)
        decision = self.strategy.decide(ctx)
        self.item_repo.put_decision(item_id, self._to_record(decision))
        return decision

    def build_context(
        self, item_id: str, *, geohash5: str | None = None
    ) -> RoutingContext:
        """Resolve the price band, per-path value/cost, and optional demand.

        Separated from :meth:`decide` so the resolved economics can be inspected
        (and so both strategies can be compared on the same context in tests).
        """

        aggregate = self.item_repo.get_item(item_id)
        if aggregate is None:
            raise ItemNotFound(item_id)
        if aggregate.grade is None:
            raise GradeRequired(item_id)

        meta = aggregate.meta
        grade = self._grade_of(aggregate.grade.grade)
        band = self.price.estimate(meta.category, grade, meta.age_months)

        path_values = dict(self.value_model(band))
        path_costs = {
            disposition: self.cost.total_handling_cost(disposition)
            for disposition in Disposition
        }

        demand_signal: DemandSignal | None = None
        if self.demand is not None and geohash5 is not None:
            demand_signal = self.demand.demand_index(geohash5, meta.category)

        return RoutingContext(
            item_id=item_id,
            price_band=band,
            path_values=path_values,
            path_costs=path_costs,
            demand=demand_signal,
        )

    @staticmethod
    def _grade_of(grade_label: str) -> Grade:
        """Resolve a persisted grade label to the domain :class:`Grade` enum."""

        try:
            return Grade(grade_label)
        except ValueError as exc:
            raise RoutingError(
                f"persisted grade label is not a recognized Grade: {grade_label!r}"
            ) from exc

    @staticmethod
    def _to_record(decision: RoutingDecision) -> DecisionRecord:
        """Map the domain decision to the persisted DECISION facet record."""

        return DecisionRecord(
            disposition=decision.disposition.value,
            price=decision.price,
            value=decision.value,
            cost=decision.cost,
            margin=decision.margin,
            rationale=decision.rationale,
        )
