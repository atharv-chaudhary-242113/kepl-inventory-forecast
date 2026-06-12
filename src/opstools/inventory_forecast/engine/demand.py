"""Demand reconstruction from replenishment intent.

DOMAIN_RULES.md defines the business as operating a replenishment-driven
inventory model rather than exposing a direct sales ledger.

When inventory is consumed internally, used in production, or sold to a
customer, the business initiates replenishment by creating a Purchase Order
Voucher (POV). This makes the POV the earliest observable demand signal in the
ERP workflow and the canonical source for demand reconstruction.

Document roles:

POV
    Replenishment intent.
    Primary source for demand reconstruction.

GRN
    Physical receipt confirmation.
    Used by lead-time and supplier-performance analytics.

PV
    Financial recognition of purchases.
    Used by accounting and financial analytics.

Closing Stock
    Inventory-position snapshot.
    Represents the stock level maintained by the business and serves as the
    baseline inventory reference.

Demand is therefore reconstructed directly from POV activity rather than
indirectly inferred from downstream procurement lifecycle events.
"""

import polars as pl

# WORKBOOK_SCHEMA.md fixes Demand_History granularity to monthly periods.
# Each transaction date is truncated to the first day of its month so all
# replenishment activity within the same month aggregates into one demand
# period.
_MONTHLY: str = "1mo"


def reconstruct_demand(
    pov: pl.LazyFrame,
) -> pl.LazyFrame:
    """Construct a monthly per-item demand history from POV records.

    The business creates a POV when inventory must be replenished following
    consumption, production usage, or customer sales. Consequently, POV rows
    are treated as the canonical demand signal.

    Args:
        pov:
            Canonical Purchase Order Voucher ledger.

    Returns:
        LazyFrame with schema:

        [
            period(Date, month-start),
            supplier(Utf8),
            item(Utf8),
            demand_quantity(Float64),
            demand_value(Decimal),
        ]

        One row per (supplier, item, month).

        demand_quantity
            Monthly replenishment quantity.

        demand_value
            Monthly replenishment value.

        Decimal accumulation is preserved to avoid financial rounding drift.
    """
    return (
        _project_demand(pov)
        .group_by(["period", "supplier", "item"])
        .agg(
            pl.col("demand_quantity").sum(),
            pl.col("demand_value").sum(),
        )
        .sort(["period", "supplier", "item"])
        .select(
            [
                "period",
                "supplier",
                "item",
                "demand_quantity",
                "demand_value",
            ]
        )
    )


def _project_demand(pov: pl.LazyFrame) -> pl.LazyFrame:
    """Project POV records onto the demand-history shape.

    Rows with null dates are excluded because they cannot be placed on a
    chronological forecasting axis.

    Dates are truncated to month-start boundaries so multiple replenishment
    events occurring within the same month contribute to a single demand
    period.
    """
    return pov.filter(pl.col("date").is_not_null()).select(
        pl.col("date").dt.truncate(_MONTHLY).alias("period"),
        pl.col("supplier"),
        pl.col("item"),
        pl.col("qty").alias("demand_quantity"),
        pl.col("amount").alias("demand_value"),
    )
