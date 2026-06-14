"""Pure routing tools used by the Routing_Agent (Requirements 10.1-10.3).

This module implements the three dependency-free tools the Routing_Agent uses to
turn a graded item into a unit-economics decision:

* :class:`PriceEstimator` (Requirement 10.1) -- estimates a recoverable price
  band from ``(category, grade, item age)`` using a seeded category/grade/age
  CSV table loaded as package data.
* :class:`CostModel` (Requirement 10.2) -- returns the total handling cost for a
  disposition path, broken down into grading, logistics, and relist components
  (plus an optional route-specific reconditioning extra), from seeded,
  configurable constants.
* :class:`DemandProbe` (Requirement 10.3) -- returns a seeded neighborhood
  demand index keyed by ``(geohash5, category)``.

Everything here is framework-free: only the Python standard library (``csv``,
``decimal``, ``importlib.resources``) is used. The seed data ships as package
data but every tool accepts injected overrides so the composition root (or a
later cache/OpenSearch-backed implementation) can substitute its own data
without changing the service layer.

All money values are :class:`decimal.Decimal` to avoid binary-float rounding in
the margin math the Routing_Agent performs downstream.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from importlib import resources
from typing import Iterable, Mapping

from rebridge_data.interfaces import BuyerPersonaRepository

from rebridge_service.models import Disposition, Grade

__all__ = [
    "AGE_BUCKETS",
    "DEFAULT_CATEGORY",
    "PriceBand",
    "PriceEstimator",
    "CostBreakdown",
    "CostModel",
    "DEFAULT_ROUTE_COSTS",
    "DemandLevel",
    "DemandSignal",
    "DemandProbe",
    "DEFAULT_DEMAND_INDEX",
    "age_bucket_for_months",
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# The catch-all category used when a requested category is not in the table.
DEFAULT_CATEGORY = "general"

# Age buckets (months) in ascending order. The last bucket is open-ended.
AGE_BUCKETS: tuple[str, ...] = ("0-6", "7-12", "13-24", "25+")


def age_bucket_for_months(age_months: int) -> str:
    """Map an item age in months to its price-table age bucket.

    Buckets are ``0-6``, ``7-12``, ``13-24`` and the open-ended ``25+``. A
    negative age is treated as the youngest bucket.
    """

    if isinstance(age_months, bool) or not isinstance(age_months, int):
        raise ValueError(
            f"age_months must be an int, got {type(age_months).__name__}"
        )
    if age_months <= 6:
        return "0-6"
    if age_months <= 12:
        return "7-12"
    if age_months <= 24:
        return "13-24"
    return "25+"


def _grade_label(grade: Grade | str) -> str:
    """Normalize a ``Grade`` enum member or its label to the wire label."""

    if isinstance(grade, Grade):
        return grade.value
    if isinstance(grade, str):
        # Accept either the human label ("Like New") or the enum name ("LIKE_NEW").
        try:
            return Grade(grade).value
        except ValueError:
            try:
                return Grade[grade].value
            except KeyError:
                raise ValueError(f"unknown grade: {grade!r}") from None
    raise ValueError(f"grade must be a Grade or str, got {type(grade).__name__}")


# ---------------------------------------------------------------------------
# PriceEstimator (Requirement 10.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceBand:
    """A recoverable price band for a ``(category, grade, age)`` combination.

    ``point`` is the central estimate; ``low``/``high`` bracket it. All three
    are USD :class:`~decimal.Decimal` amounts. ``category`` is the category the
    band was actually resolved against (the fallback :data:`DEFAULT_CATEGORY`
    when the requested category was unknown).
    """

    category: str
    grade: str
    age_bucket: str
    low: Decimal
    high: Decimal
    point: Decimal


class PriceEstimator:
    """Estimates a recoverable price band from category, grade, and age.

    The lookup table is a CSV with the columns ``category, grade, age_bucket,
    price_low, price_high, price_point``. By default the seeded placeholder
    table shipped as package data (``data/price_bands.csv``) is loaded; pass
    ``csv_path`` to load an alternate file or ``rows`` to inject an in-memory
    table (used by tests and by later cache-backed implementations).

    When a requested category is absent from the table the estimator falls back
    to the :data:`DEFAULT_CATEGORY` ("general") row for the same grade and age,
    so a price band is always available for the Routing_Agent (Requirement
    10.1). Lines beginning with ``#`` in the CSV are treated as comments.
    """

    _PACKAGE = "rebridge_service"
    _RESOURCE = "data/price_bands.csv"

    def __init__(
        self,
        csv_path: str | None = None,
        rows: Iterable[Mapping[str, str]] | None = None,
    ) -> None:
        if rows is not None:
            raw_rows = list(rows)
        elif csv_path is not None:
            with open(csv_path, "r", encoding="utf-8", newline="") as fh:
                raw_rows = list(csv.DictReader(_strip_comments(fh)))
        else:
            raw_rows = list(_load_packaged_csv(self._PACKAGE, self._RESOURCE))

        # Index by (category, grade, age_bucket) -> PriceBand.
        self._table: dict[tuple[str, str, str], PriceBand] = {}
        for row in raw_rows:
            band = _row_to_band(row)
            self._table[(band.category, band.grade, band.age_bucket)] = band

        if not self._table:
            raise ValueError("price-band table is empty")

    def estimate(
        self,
        category: str,
        grade: Grade | str,
        age_months: int,
        expected_price: Decimal | None = None,
    ) -> PriceBand:
        """Return the price band for ``(category, grade, age_months)``.

        ``grade`` may be a :class:`~rebridge_service.models.Grade` member or its
        label/name. ``category`` matching is case-insensitive. Falls back to the
        :data:`DEFAULT_CATEGORY` table entry when the category is unknown.
        If ``expected_price`` is provided, it is used as the base reference price
        instead of the static lookup table, applying the same relative depreciation
        multipliers.
        """

        cat = _normalize_category(category)
        label = _grade_label(grade)
        bucket = age_bucket_for_months(age_months)

        band = self._table.get((cat, label, bucket))
        if band is None:
            band = self._table.get((DEFAULT_CATEGORY, label, bucket))

        if band is None:
            raise KeyError(
                f"no price band for category={category!r} grade={label!r} "
                f"age_bucket={bucket!r} (and no {DEFAULT_CATEGORY!r} fallback)"
            )

        if expected_price is not None:
            ref_band = self._table.get((band.category, Grade.LIKE_NEW.value, "0-6"))
            if ref_band and ref_band.point > 0:
                multiplier = band.point / ref_band.point
                point = (expected_price * multiplier).quantize(Decimal("0.01"))
                # Using 15% spread as defined in the system
                low = (point * Decimal("0.85")).quantize(Decimal("0.01"))
                high = (point * Decimal("1.15")).quantize(Decimal("0.01"))
                return PriceBand(
                    category=band.category,
                    grade=band.grade,
                    age_bucket=band.age_bucket,
                    low=low,
                    high=high,
                    point=point,
                )

        return band


def _normalize_category(category: str) -> str:
    if not isinstance(category, str):
        raise ValueError(
            f"category must be a str, got {type(category).__name__}"
        )
    return category.strip().lower()


def _strip_comments(lines: Iterable[str]) -> list[str]:
    return [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def _load_packaged_csv(package: str, resource: str) -> list[dict[str, str]]:
    ref = resources.files(package).joinpath(resource)
    text = ref.read_text(encoding="utf-8")
    return list(csv.DictReader(_strip_comments(text.splitlines())))


def _row_to_band(row: Mapping[str, str]) -> PriceBand:
    try:
        return PriceBand(
            category=row["category"].strip().lower(),
            grade=_grade_label(row["grade"].strip()),
            age_bucket=row["age_bucket"].strip(),
            low=Decimal(str(row["price_low"]).strip()),
            high=Decimal(str(row["price_high"]).strip()),
            point=Decimal(str(row["price_point"]).strip()),
        )
    except KeyError as exc:
        raise ValueError(f"price-band row missing column: {exc}") from exc


# ---------------------------------------------------------------------------
# CostModel (Requirement 10.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostBreakdown:
    """The handling-cost components for a single disposition path.

    Requirement 10.2 calls out grading, logistics, and relist costs explicitly;
    ``extra`` carries any route-specific reconditioning/handling cost (e.g.
    refurbishment) and defaults to zero. ``total`` is the sum of all four.
    """

    disposition: Disposition
    grading: Decimal
    logistics: Decimal
    relist: Decimal
    extra: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        """Total handling cost = grading + logistics + relist + extra."""

        return self.grading + self.logistics + self.relist + self.extra


# Seeded, placeholder per-route handling costs (USD). Configurable via the
# CostModel constructor. These are synthetic v1 estimates, not measured costs.
DEFAULT_ROUTE_COSTS: dict[Disposition, CostBreakdown] = {
    Disposition.RESELL: CostBreakdown(
        Disposition.RESELL,
        grading=Decimal("2.50"),
        logistics=Decimal("4.00"),
        relist=Decimal("1.50"),
        extra=Decimal("0"),
    ),
    Disposition.REFURB: CostBreakdown(
        Disposition.REFURB,
        grading=Decimal("2.50"),
        logistics=Decimal("5.00"),
        relist=Decimal("2.00"),
        extra=Decimal("12.00"),  # reconditioning labor + parts
    ),
    Disposition.P2P: CostBreakdown(
        Disposition.P2P,
        grading=Decimal("2.50"),
        logistics=Decimal("2.00"),  # local handoff, cheaper logistics
        relist=Decimal("1.00"),
        extra=Decimal("0"),
    ),
    Disposition.DONATE: CostBreakdown(
        Disposition.DONATE,
        grading=Decimal("2.50"),
        logistics=Decimal("3.00"),  # pickup / processing
        relist=Decimal("0"),  # nothing relisted
        extra=Decimal("0"),
    ),
}


class CostModel:
    """Per-route handling costs from seeded, configurable constants.

    The Routing_Agent calls :meth:`handling_cost` (or :meth:`total_handling_cost`)
    for each disposition to obtain the total handling cost including grading,
    logistics, and relist (Requirement 10.2). Defaults come from
    :data:`DEFAULT_ROUTE_COSTS`; pass ``route_costs`` to override some or all of
    them (unspecified routes fall back to the defaults).
    """

    def __init__(
        self,
        route_costs: Mapping[Disposition, CostBreakdown] | None = None,
    ) -> None:
        merged = dict(DEFAULT_ROUTE_COSTS)
        if route_costs:
            for disposition, breakdown in route_costs.items():
                if not isinstance(disposition, Disposition):
                    raise ValueError(
                        f"route_costs key must be a Disposition, got {disposition!r}"
                    )
                if breakdown.disposition is not disposition:
                    raise ValueError(
                        "route_costs breakdown disposition mismatch: "
                        f"key={disposition} breakdown={breakdown.disposition}"
                    )
                merged[disposition] = breakdown
        self._costs = merged

    def handling_cost(self, disposition: Disposition) -> CostBreakdown:
        """Return the full :class:`CostBreakdown` for a disposition path."""

        if not isinstance(disposition, Disposition):
            raise ValueError(
                f"disposition must be a Disposition, got {disposition!r}"
            )
        return self._costs[disposition]

    def total_handling_cost(self, disposition: Disposition) -> Decimal:
        """Return just the total handling cost for a disposition path."""

        return self.handling_cost(disposition).total


# ---------------------------------------------------------------------------
# DemandProbe (Requirement 10.3)
# ---------------------------------------------------------------------------


class DemandLevel:
    """Coarse demand labels derived from the demand index."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class DemandSignal:
    """A seeded neighborhood demand reading for a ``(geohash5, category)``.

    ``index`` is a normalized demand index in the closed interval ``[0, 1]``;
    ``level`` is its coarse :class:`DemandLevel` label; ``source`` records how it
    was produced ("seed", "default", or "buyer_repo").
    """

    geohash5: str
    category: str
    index: float
    level: str
    source: str


def _demand_level(index: float) -> str:
    if index >= 0.66:
        return DemandLevel.HIGH
    if index >= 0.33:
        return DemandLevel.MEDIUM
    return DemandLevel.LOW


# Seeded neighborhood demand index keyed by (geohash5, category) -> index in
# [0, 1]. Placeholder v1 values; geohash5 keys are illustrative neighborhoods.
DEFAULT_DEMAND_INDEX: dict[tuple[str, str], float] = {
    ("9q8yy", "electronics"): 0.82,
    ("9q8yy", "apparel"): 0.55,
    ("9q8yy", "home"): 0.40,
    ("dr5ru", "electronics"): 0.70,
    ("dr5ru", "books"): 0.60,
    ("dr5ru", "toys"): 0.35,
    ("gcpvj", "apparel"): 0.75,
    ("gcpvj", "home"): 0.50,
    ("u4pru", "electronics"): 0.45,
    ("u4pru", "toys"): 0.65,
}


class DemandProbe:
    """Returns a seeded neighborhood demand index keyed by geohash/category.

    By default the probe reads from a seeded ``(geohash5, category) -> index``
    table (:data:`DEFAULT_DEMAND_INDEX`) and returns :attr:`default_index` for
    unknown keys. Pass ``index`` to override the seed table and ``default_index``
    to change the fallback. :meth:`from_buyer_repository` builds a probe that
    instead derives the demand index from the count of seeded candidate buyers
    in a :class:`~rebridge_data.interfaces.BuyerPersonaRepository`, bridging the
    seeded demand-matching data source (design ``DemandProbe(buyers)``).
    """

    def __init__(
        self,
        index: Mapping[tuple[str, str], float] | None = None,
        default_index: float = 0.30,
        *,
        buyer_repo: BuyerPersonaRepository | None = None,
        saturation_count: int = 5,
    ) -> None:
        if not (0.0 <= default_index <= 1.0):
            raise ValueError(
                f"default_index must be in [0, 1], got {default_index}"
            )
        self._index = dict(DEFAULT_DEMAND_INDEX if index is None else index)
        self._default = float(default_index)
        self._buyer_repo = buyer_repo
        if saturation_count <= 0:
            raise ValueError("saturation_count must be positive")
        self._saturation = saturation_count

    @classmethod
    def from_buyer_repository(
        cls,
        buyer_repo: BuyerPersonaRepository,
        default_index: float = 0.30,
        saturation_count: int = 5,
    ) -> "DemandProbe":
        """Build a probe that derives demand from seeded buyer-persona counts."""

        return cls(
            index={},
            default_index=default_index,
            buyer_repo=buyer_repo,
            saturation_count=saturation_count,
        )

    def demand_index(self, geohash5: str, category: str) -> DemandSignal:
        """Return the seeded :class:`DemandSignal` for a geohash and category.

        Lookup precedence: an explicit seed-table entry wins; otherwise, if a
        buyer repository was supplied, the index is derived from the candidate
        count (normalized by ``saturation_count`` and capped at 1.0); otherwise
        the configured default index is returned.
        """

        cat = _normalize_category(category)
        geo = _normalize_geohash(geohash5)
        key = (geo, cat)

        if key in self._index:
            value = _clamp_unit(self._index[key])
            return DemandSignal(geo, cat, value, _demand_level(value), "seed")

        if self._buyer_repo is not None:
            count = len(self._buyer_repo.candidates(geo, cat))
            value = _clamp_unit(count / self._saturation)
            return DemandSignal(geo, cat, value, _demand_level(value), "buyer_repo")

        value = _clamp_unit(self._default)
        return DemandSignal(geo, cat, value, _demand_level(value), "default")


def _normalize_geohash(geohash5: str) -> str:
    if not isinstance(geohash5, str):
        raise ValueError(
            f"geohash5 must be a str, got {type(geohash5).__name__}"
        )
    return geohash5.strip().lower()


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
