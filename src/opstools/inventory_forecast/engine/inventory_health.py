"""Inventory-health analytics per item.

Combines the valued closing-stock snapshot with reconstructed demand to estimate
how long current stock will last (months of cover) and to flag dead/over/under
stock. DOMAIN_RULES.md marks the exact health-scoring methodology as pending
business validation, so the cover thresholds live as named constants. Excess
inventory value stays Decimal-exact (THREAT_MODEL.md "Floating-Point Errors").
Pure over Polars LazyFrames.
"""

import polars as pl

from opstools.inventory_forecast.domain import InventoryStatus

# Decimal money scale (ingestion/schema.py MONEY_SCALE).
_MONEY: pl.datatypes.DataTypeClass | pl.Decimal = pl.Decimal(scale=4)

# Cover thresholds in months (pending business validation, DOMAIN_RULES.md):
#   below low  -> not enough on hand;  above overstock -> too much capital tied up.
# Excess is measured against the target cover.
_LOW_STOCK_MONTHS: float = 1.0
_OVERSTOCK_MONTHS: float = 12.0
_TARGET_MONTHS: float = 3.0


def build_inventory_health(
    valuation: pl.LazyFrame,
    demand: pl.LazyFrame,
) -> pl.LazyFrame:
    """Assess months-of-cover, health status, and excess value per item.

    Args:
        valuation: Inventory valuation from ``build_inventory_valuation``
            (``[item, quantity, unit_cost, inventory_value, snapshot_date]``).
        demand: Monthly Demand_History from ``reconstruct_demand``. Aggregated to
            item level (summed across suppliers, then averaged over months) to give
            an item-wide average monthly demand.

    Returns:
        A LazyFrame ``[item, quantity(Float64), avg_monthly_demand(Float64),
        months_of_cover(Float64), status(Utf8), excess_inventory_value(Decimal)]``,
        sorted by item. ``months_of_cover`` is null where there is no demand to
        divide by (an obsolescence signal captured by ``status``).
    """
    # Item-wide average monthly demand: total demand per month (across suppliers),
    # then the mean across the months that item was demanded.
    monthly = demand.group_by(["item", "period"]).agg(
        pl.col("demand_quantity").sum().alias("_monthly_qty")
    )
    avg_demand = monthly.group_by("item").agg(
        pl.col("_monthly_qty").mean().alias("avg_monthly_demand")
    )

    return (
        valuation.join(avg_demand, on="item", how="left")
        .with_columns(
            # Treat a missing/zero demand as zero so the math below is well-defined.
            pl.col("avg_monthly_demand").fill_null(0.0)
        )
        .with_columns(
            # Cover is undefined without demand -> null (flagged via status).
            pl.when(pl.col("avg_monthly_demand") > 0)
            .then(pl.col("quantity") / pl.col("avg_monthly_demand"))
            .otherwise(None)
            .alias("months_of_cover"),
            # Quantity held beyond the target cover, never negative.
            pl.max_horizontal(
                pl.col("quantity") - _TARGET_MONTHS * pl.col("avg_monthly_demand"),
                pl.lit(0.0),
            ).alias("_excess_qty"),
        )
        .with_columns(_status_expr())
        .with_columns(
            # excess_qty * unit_cost, kept Decimal (cast the float qty into Decimal
            # space so currency never accumulates in float).
            (pl.col("_excess_qty").cast(_MONEY) * pl.col("unit_cost"))
            .cast(_MONEY)
            .alias("excess_inventory_value")
        )
        .select(
            [
                "item",
                "quantity",
                "avg_monthly_demand",
                "months_of_cover",
                "status",
                "excess_inventory_value",
            ]
        )
        .sort("item")
    )


def _status_expr() -> pl.Expr:
    """Map cover and demand onto an InventoryStatus (thresholds pending validation)."""
    cover = pl.col("months_of_cover")
    has_demand = pl.col("avg_monthly_demand") > 0
    has_stock = pl.col("quantity") > 0
    return (
        # No demand but stock on hand -> dead stock; no demand and no stock -> healthy.
        pl.when(~has_demand)
        .then(
            pl.when(has_stock)
            .then(pl.lit(InventoryStatus.DEAD_STOCK.value))
            .otherwise(pl.lit(InventoryStatus.HEALTHY.value))
        )
        .when(cover < _LOW_STOCK_MONTHS)
        .then(pl.lit(InventoryStatus.LOW_STOCK.value))
        .when(cover > _OVERSTOCK_MONTHS)
        .then(pl.lit(InventoryStatus.OVERSTOCKED.value))
        .otherwise(pl.lit(InventoryStatus.HEALTHY.value))
        .alias("status")
    )
