"""Unit tests for the routing tools (Requirements 10.1, 10.2, 10.3).

Covers:
- PriceEstimator: loads the seeded category/grade/age CSV, resolves bands,
  applies the age-bucket mapping, accepts Grade enums and labels, and falls
  back to the general category for unknown categories (Req 10.1).
- CostModel: per-route handling costs broken into grading/logistics/relist
  (+extra), totals, and constructor overrides (Req 10.2).
- DemandProbe: seeded (geohash5, category) demand index, default fallback, and
  the buyer-repository-derived variant (Req 10.3).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from rebridge_data.models import BuyerPersona

from rebridge_service.models import Disposition, Grade
from rebridge_service.routing_tools import (
    CostBreakdown,
    CostModel,
    DemandLevel,
    DemandProbe,
    PriceBand,
    PriceEstimator,
    age_bucket_for_months,
)

from .fakes import FakeBuyerPersonaRepository


# --- age bucket mapping ----------------------------------------------------


@pytest.mark.parametrize(
    ("months", "expected"),
    [
        (0, "0-6"),
        (6, "0-6"),
        (7, "7-12"),
        (12, "7-12"),
        (13, "13-24"),
        (24, "13-24"),
        (25, "25+"),
        (120, "25+"),
        (-3, "0-6"),  # negative treated as youngest
    ],
)
def test_age_bucket_for_months(months, expected):
    assert age_bucket_for_months(months) == expected


def test_age_bucket_rejects_non_int():
    with pytest.raises(ValueError):
        age_bucket_for_months(6.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        age_bucket_for_months(True)  # type: ignore[arg-type]


# --- PriceEstimator (Req 10.1) ---------------------------------------------


def test_price_estimator_loads_packaged_seed_table():
    est = PriceEstimator()
    band = est.estimate("electronics", Grade.LIKE_NEW, 3)
    assert isinstance(band, PriceBand)
    assert band.category == "electronics"
    assert band.grade == "Like New"
    assert band.age_bucket == "0-6"
    # low < point < high and all positive
    assert band.low < band.point < band.high
    assert band.low > 0


def test_price_estimator_accepts_grade_label_and_name():
    est = PriceEstimator()
    by_enum = est.estimate("apparel", Grade.GOOD, 10)
    by_label = est.estimate("apparel", "Good", 10)
    by_name = est.estimate("apparel", "GOOD", 10)
    assert by_enum == by_label == by_name


def test_price_estimator_age_decay_is_monotonic_non_increasing():
    est = PriceEstimator()
    points = [
        est.estimate("home", Grade.VERY_GOOD, months).point
        for months in (1, 9, 18, 40)
    ]
    assert points == sorted(points, reverse=True)


def test_price_estimator_grade_ordering_non_increasing():
    est = PriceEstimator()
    points = [
        est.estimate("toys", g, 3).point
        for g in (
            Grade.LIKE_NEW,
            Grade.VERY_GOOD,
            Grade.GOOD,
            Grade.ACCEPTABLE,
            Grade.UNSELLABLE,
        )
    ]
    assert points == sorted(points, reverse=True)


def test_price_estimator_unknown_category_falls_back_to_general():
    est = PriceEstimator()
    band = est.estimate("kitchenware-not-in-table", Grade.GOOD, 5)
    assert band.category == "general"
    assert band.grade == "Good"


def test_price_estimator_category_case_insensitive():
    est = PriceEstimator()
    assert est.estimate("ELECTRONICS", Grade.GOOD, 3) == est.estimate(
        "electronics", Grade.GOOD, 3
    )


def test_price_estimator_injected_rows_override_seed():
    rows = [
        {
            "category": "widgets",
            "grade": "Good",
            "age_bucket": "0-6",
            "price_low": "10.00",
            "price_high": "20.00",
            "price_point": "15.00",
        }
    ]
    est = PriceEstimator(rows=rows)
    band = est.estimate("widgets", Grade.GOOD, 2)
    assert band.point == Decimal("15.00")
    assert band.low == Decimal("10.00")
    assert band.high == Decimal("20.00")


def test_price_estimator_missing_band_without_fallback_raises():
    rows = [
        {
            "category": "widgets",
            "grade": "Good",
            "age_bucket": "0-6",
            "price_low": "10",
            "price_high": "20",
            "price_point": "15",
        }
    ]
    est = PriceEstimator(rows=rows)
    with pytest.raises(KeyError):
        est.estimate("unknown", Grade.LIKE_NEW, 2)


def test_price_estimator_empty_table_rejected():
    with pytest.raises(ValueError):
        PriceEstimator(rows=[])


def test_price_estimator_original_price_logic():
    rows = [
        {
            "category": "widgets",
            "grade": "Like New",
            "age_bucket": "0-6",
            "price_low": "45.00",
            "price_high": "55.00",
            "price_point": "50.00",
        },
        {
            "category": "widgets",
            "grade": "Good",
            "age_bucket": "13-24",
            "price_low": "15.00",
            "price_high": "25.00",
            "price_point": "20.00",
        }
    ]
    est = PriceEstimator(rows=rows)
    # 20 / 50 = 0.4 multiplier
    # original_price = 100 -> tmv = 40
    
    # 1. No expected price -> use TMV (40)
    band1 = est.estimate("widgets", Grade.GOOD, 15, original_price=Decimal("100.00"))
    assert band1.point == Decimal("40.00")
    
    # 2. Expected price is realistic (within 15% of 40) -> 42
    band2 = est.estimate("widgets", Grade.GOOD, 15, original_price=Decimal("100.00"), expected_price=Decimal("42.00"))
    assert band2.point == Decimal("42.00")
    
    # 3. Expected price is overpriced (> 46) -> 60. Ignored, stays at TMV.
    band3 = est.estimate("widgets", Grade.GOOD, 15, original_price=Decimal("100.00"), expected_price=Decimal("60.00"))
    assert band3.point == Decimal("40.00")
    assert band3.high == Decimal("46.00")
    
    # 4. Expected price is underpriced (< 34) -> 30. Point stays TMV.
    band4 = est.estimate("widgets", Grade.GOOD, 15, original_price=Decimal("100.00"), expected_price=Decimal("30.00"))
    assert band4.point == Decimal("40.00")


# --- CostModel (Req 10.2) --------------------------------------------------


@pytest.mark.parametrize("disposition", list(Disposition))
def test_cost_model_breakdown_components_present(disposition):
    model = CostModel()
    breakdown = model.handling_cost(disposition)
    assert isinstance(breakdown, CostBreakdown)
    assert breakdown.disposition is disposition
    # Requirement 10.2: grading, logistics, and relist are all defined.
    assert breakdown.grading >= 0
    assert breakdown.logistics >= 0
    assert breakdown.relist >= 0
    assert breakdown.total == (
        breakdown.grading + breakdown.logistics + breakdown.relist + breakdown.extra
    )


def test_cost_model_total_matches_sum():
    model = CostModel()
    for disposition in Disposition:
        assert model.total_handling_cost(disposition) == model.handling_cost(
            disposition
        ).total


def test_cost_model_refurb_costs_more_than_resell():
    model = CostModel()
    assert model.total_handling_cost(Disposition.REFURB) > model.total_handling_cost(
        Disposition.RESELL
    )


def test_cost_model_donate_has_no_relist_cost():
    model = CostModel()
    assert model.handling_cost(Disposition.DONATE).relist == Decimal("0")


def test_cost_model_override_route_costs():
    override = {
        Disposition.RESELL: CostBreakdown(
            Disposition.RESELL,
            grading=Decimal("1.00"),
            logistics=Decimal("1.00"),
            relist=Decimal("0.50"),
        )
    }
    model = CostModel(route_costs=override)
    assert model.total_handling_cost(Disposition.RESELL) == Decimal("2.50")
    # Unspecified routes keep their defaults.
    assert model.total_handling_cost(Disposition.P2P) == Decimal("5.50")


def test_cost_model_override_disposition_mismatch_rejected():
    bad = {
        Disposition.RESELL: CostBreakdown(
            Disposition.P2P,
            grading=Decimal("1"),
            logistics=Decimal("1"),
            relist=Decimal("1"),
        )
    }
    with pytest.raises(ValueError):
        CostModel(route_costs=bad)


# --- DemandProbe (Req 10.3) ------------------------------------------------


def test_demand_probe_seeded_index_lookup():
    probe = DemandProbe()
    signal = probe.demand_index("9q8yy", "electronics")
    assert signal.geohash5 == "9q8yy"
    assert signal.category == "electronics"
    assert signal.index == pytest.approx(0.82)
    assert signal.level == DemandLevel.HIGH
    assert signal.source == "seed"


def test_demand_probe_default_for_unknown_key():
    probe = DemandProbe(default_index=0.25)
    signal = probe.demand_index("zzzzz", "electronics")
    assert signal.index == pytest.approx(0.25)
    assert signal.source == "default"
    assert signal.level == DemandLevel.LOW


def test_demand_probe_case_insensitive_keys():
    probe = DemandProbe()
    assert probe.demand_index("9Q8YY", "ELECTRONICS").index == pytest.approx(0.82)


def test_demand_probe_index_is_clamped_to_unit_interval():
    probe = DemandProbe(index={("aaaaa", "books"): 5.0})
    assert probe.demand_index("aaaaa", "books").index == 1.0


def test_demand_probe_levels():
    probe = DemandProbe(
        index={
            ("g1", "c"): 0.1,
            ("g2", "c"): 0.5,
            ("g3", "c"): 0.9,
        }
    )
    assert probe.demand_index("g1", "c").level == DemandLevel.LOW
    assert probe.demand_index("g2", "c").level == DemandLevel.MEDIUM
    assert probe.demand_index("g3", "c").level == DemandLevel.HIGH


def test_demand_probe_invalid_default_rejected():
    with pytest.raises(ValueError):
        DemandProbe(default_index=1.5)


def test_demand_probe_from_buyer_repository_derives_from_counts():
    personas = [
        BuyerPersona(
            buyer_id=f"b{i}",
            geohash5="9q8yy",
            persona_type="deal_seeker",
            category_interests=["electronics"],
        )
        for i in range(3)
    ]
    repo = FakeBuyerPersonaRepository(personas)
    probe = DemandProbe.from_buyer_repository(repo, saturation_count=5)
    signal = probe.demand_index("9q8yy", "electronics")
    # 3 candidates / saturation 5 = 0.6
    assert signal.index == pytest.approx(0.6)
    assert signal.source == "buyer_repo"
    assert signal.level == DemandLevel.MEDIUM


def test_demand_probe_from_buyer_repository_caps_at_one():
    personas = [
        BuyerPersona(
            buyer_id=f"b{i}",
            geohash5="dr5ru",
            persona_type="price_balker",
            category_interests=["books"],
        )
        for i in range(10)
    ]
    repo = FakeBuyerPersonaRepository(personas)
    probe = DemandProbe.from_buyer_repository(repo, saturation_count=4)
    assert probe.demand_index("dr5ru", "books").index == 1.0
