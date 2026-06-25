"""Portfolio analytics.

Provides descriptive analytics before forecasting.

These metrics are intended to answer:

- What does the procurement portfolio look like?
- How many SKUs are forecastable?
- How sparse is demand?
- Which suppliers dominate spend?
"""

from __future__ import annotations

import polars as pl


def build_observation_profile(
    demand: pl.LazyFrame,
) -> pl.LazyFrame:
    """Observation counts by supplier-item."""
    return demand.group_by(
        [
            "supplier",
            "item",
        ]
    ).agg(
        pl.len().alias("observation_count"),
        pl.col("demand_quantity").sum().alias("total_quantity"),
        pl.col("demand_value").sum().alias("total_value"),
        pl.col("period").min().alias("first_purchase"),
        pl.col("period").max().alias("last_purchase"),
    )


def build_supplier_summary(
    demand: pl.LazyFrame,
) -> pl.LazyFrame:
    """Supplier-level procurement summary."""
    return (
        demand.group_by("supplier")
        .agg(
            pl.n_unique("item").alias("sku_count"),
            pl.col("demand_quantity").sum().alias("total_quantity"),
            pl.col("demand_value").sum().alias("total_spend"),
        )
        .sort(
            "total_spend",
            descending=True,
        )
    )


def build_forecast_readiness(
    observation_profile: pl.LazyFrame,
) -> pl.LazyFrame:
    """Forecast readiness assessment."""
    return observation_profile.with_columns(
        pl.when(pl.col("observation_count") < 2)
        .then(pl.lit("Not Ready"))
        .when(pl.col("observation_count") < 6)
        .then(pl.lit("Limited History"))
        .otherwise(pl.lit("Ready"))
        .alias("forecast_readiness")
    )
