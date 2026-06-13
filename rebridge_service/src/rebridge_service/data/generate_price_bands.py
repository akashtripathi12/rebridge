"""Generator for the placeholder ``price_bands.csv`` seed table.

This script produces the category/grade/age -> price-band table loaded by
:class:`rebridge_service.routing_tools.PriceEstimator`. The values it emits are
**placeholder seed values** for the v1 (48-hour) build, derived from a simple
model (per-category reference price x grade multiplier x age-decay multiplier),
NOT from real recovered-price data. Re-run it to regenerate the CSV::

    python generate_price_bands.py

The committed ``price_bands.csv`` is the artifact actually used at runtime; this
generator is kept only for documentation and reproducibility.
"""

from __future__ import annotations

import csv
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# Reference recoverable price (USD) for a Like-New, 0-6 month-old item per
# category. "general" is the catch-all fallback category. Placeholder values.
CATEGORY_REFERENCE: dict[str, Decimal] = {
    "electronics": Decimal("240"),
    "apparel": Decimal("55"),
    "home": Decimal("95"),
    "toys": Decimal("32"),
    "books": Decimal("14"),
    "general": Decimal("60"),
}

# Grade condition multipliers relative to the Like-New reference.
GRADE_MULTIPLIER: dict[str, Decimal] = {
    "Like New": Decimal("1.00"),
    "Very Good": Decimal("0.80"),
    "Good": Decimal("0.60"),
    "Acceptable": Decimal("0.38"),
    "Unsellable": Decimal("0.07"),
}

# Age-bucket decay multipliers (months since manufacture/purchase).
AGE_MULTIPLIER: dict[str, Decimal] = {
    "0-6": Decimal("1.00"),
    "7-12": Decimal("0.85"),
    "13-24": Decimal("0.68"),
    "25+": Decimal("0.52"),
}

# Half-width of the price band around the point estimate.
BAND_SPREAD = Decimal("0.15")

HEADER_COMMENT = (
    "# PLACEHOLDER SEED DATA - ReBridge v1. category/grade/age -> recoverable "
    "price band (USD).\n"
    "# Values are synthetic (reference price x grade x age decay), NOT real "
    "market data. Override via config/injection.\n"
)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for category, reference in CATEGORY_REFERENCE.items():
        for grade, gmult in GRADE_MULTIPLIER.items():
            for age_bucket, amult in AGE_MULTIPLIER.items():
                point = _money(reference * gmult * amult)
                low = _money(point * (Decimal("1") - BAND_SPREAD))
                high = _money(point * (Decimal("1") + BAND_SPREAD))
                rows.append(
                    {
                        "category": category,
                        "grade": grade,
                        "age_bucket": age_bucket,
                        "price_low": str(low),
                        "price_high": str(high),
                        "price_point": str(point),
                    }
                )
    return rows


def main() -> None:
    out_path = Path(__file__).resolve().parent / "price_bands.csv"
    rows = build_rows()
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(HEADER_COMMENT)
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "category",
                "grade",
                "age_bucket",
                "price_low",
                "price_high",
                "price_point",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} price-band rows to {out_path}")


if __name__ == "__main__":
    main()
