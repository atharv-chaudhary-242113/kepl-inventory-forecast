"""Categorizes demand into Smooth, Erratic, Intermittent, or, Lumpy."""

import polars as pl
from polars import LazyFrame


def classify_demand_patterns(
    demand_df: LazyFrame, item_col: str = "item_id", qty_col: str = "quantity"
) -> LazyFrame:
    """Categorizes demand and operates strictly lazily."""
    # 1. Calculate base metrics: Total periods, Non-zero periods,
    # and Non-zero Mean/StdDev
    metrics = demand_df.group_by(item_col).agg(
        [
            pl.count(qty_col).alias("total_periods"),
            pl.col(qty_col)
            .filter(pl.col(qty_col) > 0)
            .count()
            .alias("non_zero_periods"),
            pl.col(qty_col).filter(pl.col(qty_col) > 0).mean().alias("mean_nz_demand"),
            pl.col(qty_col).filter(pl.col(qty_col) > 0).std().alias("std_nz_demand"),
        ]
    )

    # 2. Compute ADI and CV2 safely (handling division by zero)
    calculated = metrics.with_columns(
        [
            (pl.col("total_periods") / pl.col("non_zero_periods"))
            .fill_nan(0.0)
            .alias("adi"),
            ((pl.col("std_nz_demand") / pl.col("mean_nz_demand")) ** 2)
            .fill_nan(0.0)
            .alias("cv2"),
        ]
    )

    # 3. Apply the Syntetos-Boylan routing logic
    # Thresholds: ADI = 1.32, CV2 = 0.49
    return calculated.with_columns(
        pl.when((pl.col("adi") < 1.32) & (pl.col("cv2") < 0.49))
        .then(pl.lit("Smooth"))
        .when((pl.col("adi") < 1.32) & (pl.col("cv2") >= 0.49))
        .then(pl.lit("Erratic"))
        .when((pl.col("adi") >= 1.32) & (pl.col("cv2") < 0.49))
        .then(pl.lit("Intermittent"))
        .otherwise(pl.lit("Lumpy"))
        .alias("demand_class")
    )
