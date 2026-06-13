"""Unit tests for :mod:`rebridge_service.routing_agent` (Requirements 10.4-10.8).

Covers task 10.2 behaviors:

* argmax-margin disposition selection among {RESELL, REFURB, P2P, DONATE} where
  recovered value exceeds total handling cost (Req 10.4),
* the exact-margin tie-break toward the faster customer outcome, P2P over RESELL
  (Req 10.5),
* the DONATE fallback when no non-donate path has value greater than cost
  (Req 10.6),
* a persisted DECISION facet whose rationale states value, cost, and margin
  (Req 10.7),
* identical decision output from the agent and pure-function strategies
  (Req 10.8),
* the RoutingAgent end-to-end against the seeded tools and the in-memory repo,
  including the graded-item precondition (Req 10.1).

Property-based coverage of equivalence lives in the separate property-test task
(10.5).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from rebridge_data.models import GradeRecord, ItemMeta, ItemStatus

from rebridge_service.models import Disposition, RoutingDecision
from rebridge_service.routing_agent import (
    AgentRoutingStrategy,
    GradeRequired,
    ItemNotFound,
    PureFunctionRoutingStrategy,
    RoutingAgent,
    RoutingContext,
    default_path_values,
    evaluate_routing,
    select_disposition,
)
from rebridge_service.routing_tools import CostModel, PriceBand, PriceEstimator

from tests.fakes import FakeItemRepository


# --- helpers ---------------------------------------------------------------


def _band(point: str = "20", low: str = "10", high: str = "30") -> PriceBand:
    return PriceBand(
        category="electronics",
        grade="Good",
        age_bucket="7-12",
        low=Decimal(low),
        high=Decimal(high),
        point=Decimal(point),
    )


def _ctx(
    values: dict[Disposition, str],
    costs: dict[Disposition, str],
    *,
    point: str = "20",
) -> RoutingContext:
    return RoutingContext(
        item_id="item-1",
        price_band=_band(point=point),
        path_values={d: Decimal(v) for d, v in values.items()},
        path_costs={d: Decimal(c) for d, c in costs.items()},
    )


def _seed_graded_item(
    repo: FakeItemRepository,
    *,
    item_id: str = "item-1",
    category: str = "electronics",
    grade: str = "Good",
    age_months: int = 12,
) -> None:
    repo.put_item_meta(
        ItemMeta(
            item_id=item_id,
            status=ItemStatus.GRADED,
            category=category,
            age_months=age_months,
            context_source="manual",
            created_at="2024-01-01T00:00:00+00:00",
        )
    )
    repo.put_grade(
        item_id,
        GradeRecord(grade=grade, confidence=0.95, summary="Working."),
    )


# --- core selection: argmax margin (Req 10.4) ------------------------------


def test_selects_max_margin_path():
    values = {
        Disposition.RESELL: "30",
        Disposition.REFURB: "50",
        Disposition.P2P: "30",
        Disposition.DONATE: "0",
    }
    costs = {
        Disposition.RESELL: "8",
        Disposition.REFURB: "12",  # margin 38 -> highest
        Disposition.P2P: "5",
        Disposition.DONATE: "5",
    }
    assert select_disposition(
        {d: Decimal(v) for d, v in values.items()},
        {d: Decimal(c) for d, c in costs.items()},
    ) == Disposition.REFURB


def test_excludes_paths_where_value_not_greater_than_cost():
    # RESELL is ineligible (value == cost is not strictly greater); P2P wins
    # over the only other eligible path on margin.
    values = {
        Disposition.RESELL: "8",
        Disposition.REFURB: "5",
        Disposition.P2P: "30",
        Disposition.DONATE: "0",
    }
    costs = {
        Disposition.RESELL: "8",  # equal -> excluded
        Disposition.REFURB: "12",  # value < cost -> excluded
        Disposition.P2P: "5",  # margin 25
        Disposition.DONATE: "5",
    }
    assert select_disposition(
        {d: Decimal(v) for d, v in values.items()},
        {d: Decimal(c) for d, c in costs.items()},
    ) == Disposition.P2P


# --- tie-break toward faster customer outcome (Req 10.5) -------------------


def test_tie_break_prefers_p2p_over_resell():
    # RESELL and P2P both have margin 15; P2P is the faster customer outcome.
    values = {
        Disposition.RESELL: "20",
        Disposition.REFURB: "0",
        Disposition.P2P: "17",
        Disposition.DONATE: "0",
    }
    costs = {
        Disposition.RESELL: "5",  # margin 15
        Disposition.REFURB: "100",  # ineligible
        Disposition.P2P: "2",  # margin 15
        Disposition.DONATE: "5",
    }
    assert select_disposition(
        {d: Decimal(v) for d, v in values.items()},
        {d: Decimal(c) for d, c in costs.items()},
    ) == Disposition.P2P


def test_tie_break_prefers_resell_over_refurb():
    # RESELL and REFURB both have margin 15; RESELL is the faster outcome.
    values = {
        Disposition.RESELL: "20",
        Disposition.REFURB: "30",
        Disposition.P2P: "0",
        Disposition.DONATE: "0",
    }
    costs = {
        Disposition.RESELL: "5",  # margin 15
        Disposition.REFURB: "15",  # margin 15
        Disposition.P2P: "100",  # ineligible
        Disposition.DONATE: "5",
    }
    assert select_disposition(
        {d: Decimal(v) for d, v in values.items()},
        {d: Decimal(c) for d, c in costs.items()},
    ) == Disposition.RESELL


# --- donate fallback (Req 10.6) --------------------------------------------


def test_donate_when_no_non_donate_path_is_profitable():
    values = {
        Disposition.RESELL: "5",
        Disposition.REFURB: "10",
        Disposition.P2P: "3",
        Disposition.DONATE: "0",
    }
    costs = {
        Disposition.RESELL: "8",
        Disposition.REFURB: "12",
        Disposition.P2P: "5",
        Disposition.DONATE: "5",
    }
    assert select_disposition(
        {d: Decimal(v) for d, v in values.items()},
        {d: Decimal(c) for d, c in costs.items()},
    ) == Disposition.DONATE


# --- rationale contents (Req 10.7) -----------------------------------------


def test_rationale_states_value_cost_and_margin():
    ctx = _ctx(
        values={
            Disposition.RESELL: "30",
            Disposition.REFURB: "20",
            Disposition.P2P: "30",
            Disposition.DONATE: "0",
        },
        costs={
            Disposition.RESELL: "8",
            Disposition.REFURB: "12",
            Disposition.P2P: "5",  # margin 25 -> chosen
            Disposition.DONATE: "5",
        },
    )
    decision = evaluate_routing(ctx)

    assert decision.disposition is Disposition.P2P
    assert decision.value == Decimal("30")
    assert decision.cost == Decimal("5")
    assert decision.margin == Decimal("25")
    # The rationale must surface the unit economics it was built from.
    assert "$30.00" in decision.rationale  # value
    assert "$5.00" in decision.rationale  # cost
    assert "$25.00" in decision.rationale  # margin
    assert "P2P" in decision.rationale


def test_donate_rationale_explains_fallback():
    ctx = _ctx(
        values={
            Disposition.RESELL: "5",
            Disposition.REFURB: "10",
            Disposition.P2P: "3",
            Disposition.DONATE: "0",
        },
        costs={
            Disposition.RESELL: "8",
            Disposition.REFURB: "12",
            Disposition.P2P: "5",
            Disposition.DONATE: "5",
        },
    )
    decision = evaluate_routing(ctx)

    assert decision.disposition is Disposition.DONATE
    assert decision.value == Decimal("0")
    assert decision.margin == Decimal("-5")
    assert "donated" in decision.rationale
    assert "$0.00" in decision.rationale  # value
    assert "$-5.00" in decision.rationale  # margin


# --- agent / pure-function equivalence (Req 10.8) --------------------------


@pytest.mark.parametrize(
    ("values", "costs"),
    [
        # A clear resell winner.
        (
            {Disposition.RESELL: "40", Disposition.REFURB: "20",
             Disposition.P2P: "30", Disposition.DONATE: "0"},
            {Disposition.RESELL: "8", Disposition.REFURB: "12",
             Disposition.P2P: "5", Disposition.DONATE: "5"},
        ),
        # A tie resolved toward P2P.
        (
            {Disposition.RESELL: "20", Disposition.REFURB: "0",
             Disposition.P2P: "17", Disposition.DONATE: "0"},
            {Disposition.RESELL: "5", Disposition.REFURB: "100",
             Disposition.P2P: "2", Disposition.DONATE: "5"},
        ),
        # A donate fallback.
        (
            {Disposition.RESELL: "5", Disposition.REFURB: "10",
             Disposition.P2P: "3", Disposition.DONATE: "0"},
            {Disposition.RESELL: "8", Disposition.REFURB: "12",
             Disposition.P2P: "5", Disposition.DONATE: "5"},
        ),
    ],
)
def test_agent_and_pure_function_produce_identical_output(values, costs):
    ctx = _ctx(values, costs)

    agent_decision = AgentRoutingStrategy().decide(ctx)
    pure_decision = PureFunctionRoutingStrategy().decide(ctx)

    assert agent_decision == pure_decision
    assert isinstance(agent_decision, RoutingDecision)


def test_agent_strategy_records_a_trace():
    ctx = _ctx(
        values={Disposition.RESELL: "40", Disposition.REFURB: "20",
                Disposition.P2P: "30", Disposition.DONATE: "0"},
        costs={Disposition.RESELL: "8", Disposition.REFURB: "12",
               Disposition.P2P: "5", Disposition.DONATE: "5"},
    )
    strategy = AgentRoutingStrategy()
    decision = strategy.decide(ctx)

    assert strategy.trace  # observability trace populated
    assert any(decision.disposition.value in step for step in strategy.trace)


# --- value model -----------------------------------------------------------


def test_default_value_model_maps_band_to_paths():
    band = _band(point="20", high="30")
    values = default_path_values(band)

    assert values[Disposition.RESELL] == Decimal("20")
    assert values[Disposition.P2P] == Decimal("20")
    assert values[Disposition.REFURB] == Decimal("30")  # refurb commands the high band
    assert values[Disposition.DONATE] == Decimal("0")


# --- RoutingAgent end-to-end (Req 10.1, 10.7) ------------------------------


def _agent(repo: FakeItemRepository) -> RoutingAgent:
    return RoutingAgent(
        price=PriceEstimator(),
        cost=CostModel(),
        item_repo=repo,
    )


def test_decide_persists_decision_facet():
    repo = FakeItemRepository()
    _seed_graded_item(repo)

    decision = _agent(repo).decide("item-1")

    stored = repo.get_item("item-1").decision
    assert stored is not None
    assert stored.disposition == decision.disposition.value
    assert stored.price == decision.price
    assert stored.value == decision.value
    assert stored.cost == decision.cost
    assert stored.margin == decision.margin
    assert stored.rationale == decision.rationale
    # Internal consistency of the persisted economics.
    assert stored.margin == stored.value - stored.cost
    assert stored.disposition in {d.value for d in Disposition}


def test_decide_uses_injected_strategy_consistently():
    repo = FakeItemRepository()
    _seed_graded_item(repo)

    agent_run = RoutingAgent(
        price=PriceEstimator(), cost=CostModel(), item_repo=repo,
        strategy=AgentRoutingStrategy(),
    ).decide("item-1")

    repo2 = FakeItemRepository()
    _seed_graded_item(repo2)
    pure_run = RoutingAgent(
        price=PriceEstimator(), cost=CostModel(), item_repo=repo2,
        strategy=PureFunctionRoutingStrategy(),
    ).decide("item-1")

    assert agent_run == pure_run


def test_decide_requires_a_persisted_grade():
    repo = FakeItemRepository()
    repo.put_item_meta(
        ItemMeta(
            item_id="item-1",
            status=ItemStatus.CREATED,
            category="electronics",
            age_months=12,
            context_source="manual",
            created_at="2024-01-01T00:00:00+00:00",
        )
    )
    with pytest.raises(GradeRequired):
        _agent(repo).decide("item-1")


def test_decide_unknown_item_raises():
    repo = FakeItemRepository()
    with pytest.raises(ItemNotFound):
        _agent(repo).decide("missing")
