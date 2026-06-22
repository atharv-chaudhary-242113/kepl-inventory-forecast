"""Financial summary from Purchase Vouchers (the authoritative value source).

DOMAIN_RULES.md makes PV the source of truth for procurement value and treats
freight as a separate cost component (current assumption 18%, pending business
validation). This module aggregates PV per (supplier, item) and layers freight on
top. All currency stays in Polars ``Decimal`` end to end — floating-point
currency accumulation is prohibited (PROJECT_CONSTITUTION.md; THREAT_MODEL.md
"Floating-Point Errors"). Pure over Polars LazyFrames.
"""

import polars as pl

from opstools.inventory_forecast.config import Settings

# Decimal scale matching the ingestion money contract (ingestion/schema.py
# MONEY_SCALE). Used to cast the Float64 quantity into Decimal space so that
# Decimal-by-Decimal division keeps the unit cost Decimal (a Decimal-by-Float
# division would silently downcast the result to Float64).
_MONEY: pl.datatypes.DataTypeClass | pl.Decimal = pl.Decimal(scale=4)


def build_financial_summary(pv: pl.LazyFrame, cfg: Settings) -> pl.LazyFrame:
    """Aggregate PV spend per (supplier, item) with a separate freight component.

    Args:
        pv: Canonical PV ledger — the authoritative procurement value source.
        cfg: Run settings supplying ``freight_rate`` (Decimal, default 0.18).

    Returns:
        A LazyFrame ``[supplier, item, quantity(Float64), unit_cost(Decimal),
        freight_cost(Decimal), total_cost(Decimal), total_spend(Decimal)]`` — the
        Financial_Summary sheet contract (WORKBOOK_SCHEMA.md). ``total_cost`` is
        the base PV spend, ``freight_cost`` the separate freight component, and
        ``total_spend`` their sum (landed cost).
    """
    return (
        pv.group_by(["supplier", "item"])
        .agg(
            pl.col("qty").sum().alias("quantity"),
            # Decimal in, Decimal out: the currency accumulation stays exact.
            pl.col("amount").sum().alias("total_cost"),
        )
        # Guard the weighted unit-cost division against zero-quantity groups.
        .filter(pl.col("quantity") > 0)
        .with_columns(
            # Decimal / Decimal -> Decimal (cast qty into Decimal space first).
            (pl.col("total_cost") / pl.col("quantity").cast(_MONEY)).alias("unit_cost"),
            # Freight as an isolated component: Decimal * Decimal -> Decimal.
            (pl.col("total_cost") * pl.lit(cfg.freight_rate)).alias("freight_cost"),
        )
        .with_columns(
            (pl.col("total_cost") + pl.col("freight_cost")).alias("total_spend")
        )
        .select(
            [
                "supplier",
                "item",
                "quantity",
                "unit_cost",
                "freight_cost",
                "total_cost",
                "total_spend",
            ]
        )
    )
