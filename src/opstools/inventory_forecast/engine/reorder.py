"""Reorder-point recommendations.

API_CONTRACT.md / README §3 define the reorder point as:

    reorder_point = (avg_monthly_demand * lead_time_months)
                    + (service_z * demand_std * sqrt(lead_time_months))

The first term is expected demand over the lead time; the second is safety stock
sized to the configured service level. When an item has no observed lead time we
fall back to ``cfg.default_lead_time_days`` (README §10). Lead time is converted
to months because demand is reconstructed monthly (WORKBOOK_SCHEMA.md). Pure over
Polars LazyFrames.
"""

import polars as pl

from opstools.inventory_forecast.config.settings import Settings

# Average month length used to convert lead-time *days* into the *months* the
# demand series is expressed in. A fixed 30 keeps the conversion deterministic
# (Constitution Rule 9) and is accurate enough for a planning heuristic.
_DAYS_PER_MONTH: float = 30.0


def build_reorder_recommendations(
    demand: pl.LazyFrame,
    lead_time: pl.LazyFrame,
    cfg: Settings,
) -> pl.LazyFrame:
    """Compute a per-item reorder point from monthly demand and observed lead time.

    Args:
        demand: Monthly Demand_History from ``reconstruct_demand``
            (``[period, supplier, item, demand_quantity, demand_value]``).
        lead_time: FIFO allocation frame from ``compute_lead_time``; the per-item
            mean of ``lead_time_days`` (over rows that actually received goods) is
            the observed lead time.
        cfg: Run settings supplying ``service_z`` and ``default_lead_time_days``.

    Returns:
        A LazyFrame ``[supplier, item, avg_monthly_demand(Float64),
        demand_std(Float64), lead_time_months(Float64), reorder_point(Float64)]``,
        sorted by (supplier, item).
    """
    demand_stats = demand.group_by(["supplier", "item"]).agg(
        pl.col("demand_quantity").mean().alias("avg_monthly_demand"),
        # Sample std is null for a single month; "no observed variation" -> 0.
        pl.col("demand_quantity").std(ddof=1).fill_null(0.0).alias("demand_std"),
    )

    lt_stats = (
        lead_time.filter(pl.col("grn_date").is_not_null())
        .group_by(["supplier", "item"])
        .agg(pl.col("lead_time_days").mean().alias("_lt_days"))
    )

    default_months = cfg.default_lead_time_days / _DAYS_PER_MONTH

    return (
        demand_stats.join(lt_stats, on=["supplier", "item"], how="left")
        .with_columns(
            # No observed lead time -> configured fallback (README §10).
            pl.when(pl.col("_lt_days").is_not_null())
            .then(pl.col("_lt_days") / _DAYS_PER_MONTH)
            .otherwise(default_months)
            .alias("lead_time_months")
        )
        .with_columns(
            (
                pl.col("avg_monthly_demand") * pl.col("lead_time_months")
                + cfg.service_z
                * pl.col("demand_std")
                * pl.col("lead_time_months").sqrt()
            ).alias("reorder_point")
        )
        .select(
            [
                "supplier",
                "item",
                "avg_monthly_demand",
                "demand_std",
                "lead_time_months",
                "reorder_point",
            ]
        )
        .sort(["supplier", "item"])
    )
