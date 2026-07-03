"""Inventory classification: ABC (by value) and Syntetos-Boylan (by demand shape).

Two independent classifiers, both pure over Polars LazyFrames (ARCHITECTURE.md
sec 4.3):

* ``build_abc_classification`` ranks items by cumulative procurement value into
  A/B/C bands (DOMAIN_RULES.md "ABC Classification"); the cut-points are
  configurable via ``Settings`` (README sec 10).
* ``classify_sbc`` computes the Average Demand Interval (ADI) and squared
  coefficient of variation (CV2) of each item's monthly demand and routes it to
  smooth / erratic / intermittent / lumpy (DOMAIN_RULES.md "Demand
  Classification"). These classes drive the Phase-3 forecast routing.
"""

from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.domain import AbcClass, SbcClass

# Syntetos-Boylan thresholds (DOMAIN_RULES.md "Demand Classification").
ADI_THRESHOLD: float = 1.32
CV2_THRESHOLD: float = 0.49

MIN_HISTORY_FOR_SBC: int = 6
MIN_HISTORY_FOR_FORECAST: int = 2

# SBC demand is classified over the *monthly* grid that Demand_History uses.
_MONTHLY: str = "1mo"


# noinspection GrazieInspection
def build_abc_classification(pv: pl.LazyFrame, cfg: Settings) -> pl.LazyFrame:
    """Classify each (supplier, item) into an ABC band by cumulative PV value.

    Args:
        pv: Canonical PV ledger — the authoritative procurement value source
            (DOMAIN_RULES.md). ABC must use PV value, never POV/GRN.
        cfg: Run settings supplying the A/B band cut-points (defaults 0.80/0.95).

    Returns:
        A LazyFrame
        ``[
            supplier,
            item,
            annual_value(Decimal),
            quantityt_bought(Float64),
            revenue_percentage(Float64),
            cumulative_revenue_percentage(Float64),
            quantity_percentage(Float64),
            cumulative_quantity_percentage(Float64),
            abc_class(Utf8)
        ]``

        The frame is sorted by annual procurement value in descending order and
        represents the complete ABC business dataset consumed by the workbook,
        dashboards, and downstream Business Intelligence components.
    """
    annual = pv.group_by(["supplier", "item"]).agg(
        pl.col("amount").sum().alias("annual_value"),
        pl.col("qty").sum().alias("quantityt_bought"),
    )

    # Sort descending so the cumulative curve climbs from the highest-value item;
    # the band an item lands in is decided by where its *cumulative* share sits.
    ranked = annual.sort("annual_value", descending=True)

    return (
        ranked.with_columns(
            (pl.col("annual_value") / pl.col("annual_value").sum())
            .cast(pl.Float64)
            .alias("revenue_percentage"),
            (pl.col("quantityt_bought") / pl.col("quantityt_bought").sum())
            .cast(pl.Float64)
            .alias("quantity_percentage"),
            (pl.col("annual_value").cum_sum() / pl.col("annual_value").sum()).alias(
                "_cum_revenue"
            ),
            (
                pl.col("quantityt_bought").cum_sum() / pl.col("quantityt_bought").sum()
            ).alias("_cum_quantity"),
        )
        .with_columns(
            pl.when(pl.col("_cum_revenue") <= pl.lit(Decimal(str(cfg.abc_a_threshold))))
            .then(pl.lit(AbcClass.A.value))
            .when(pl.col("_cum_revenue") <= pl.lit(Decimal(str(cfg.abc_b_threshold))))
            .then(pl.lit(AbcClass.B.value))
            .otherwise(pl.lit(AbcClass.C.value))
            .alias("abc_class"),
            pl.col("_cum_revenue")
            .cast(pl.Float64)
            .alias("cumulative_revenue_percentage"),
            pl.col("_cum_quantity")
            .cast(pl.Float64)
            .alias("cumulative_quantity_percentage"),
        )
        .select(
            [
                "supplier",
                "item",
                "annual_value",
                "quantityt_bought",
                "revenue_percentage",
                "cumulative_revenue_percentage",
                "quantity_percentage",
                "cumulative_quantity_percentage",
                "abc_class",
            ]
        )
    )


def classify_sbc(demand: pl.LazyFrame) -> pl.LazyFrame:
    """Syntetos-Boylan classification of each item's monthly demand series.

    Args:
        demand: The monthly Demand_History frame from ``reconstruct_demand``
            (``[period, supplier, item, demand_quantity, demand_value]``). It is
            *sparse* (a row only where demand occurred); this function densifies
            it to a regular monthly grid first so ADI counts the zero-demand
            months correctly.

    Returns:
        A LazyFrame ``[supplier, item, adi(Float64), cv_squared(Float64),
        demand_class(Utf8)]`` — the SBC_Classification sheet contract
        (WORKBOOK_SCHEMA.md). ``demand_class`` is the lowercase canonical enum
        value; the workbook writer title-cases it for display.
    """
    dense = _densify_to_monthly_grid(demand)

    metrics = dense.group_by(["supplier", "item"]).agg(
        # ADI = total observed months / months with non-zero demand.
        pl.len().cast(pl.Float64).alias("_total_periods"),
        (pl.col("demand_quantity") > 0).sum().cast(pl.Float64).alias("_active_periods"),
        pl.col("demand_quantity")
        .filter(pl.col("demand_quantity") > 0)
        .len()
        .cast(pl.Int64)
        .alias("_observation_count"),
        # CV2 is taken over the *non-zero* demands only (it measures size
        # variability, independent of how often demand occurs).
        pl.col("demand_quantity")
        .filter(pl.col("demand_quantity") > 0)
        .std(ddof=1)
        .alias("_nz_std"),
        pl.col("demand_quantity")
        .filter(pl.col("demand_quantity") > 0)
        .mean()
        .alias("_nz_mean"),
    )

    return (
        metrics.with_columns(
            (pl.col("_total_periods") / pl.col("_active_periods")).alias("adi"),
            # Sample std (ddof=1) is null for a single observation; treat "no
            # observed size variation" as CV2 = 0 so such an item routes by ADI.
            (pl.col("_nz_std") / pl.col("_nz_mean"))
            .pow(2)
            .fill_null(0.0)
            .alias("cv_squared"),
        )
        .with_columns(_demand_class_expr())
        .select(["supplier", "item", "adi", "cv_squared", "demand_class"])
    )


def _densify_to_monthly_grid(demand: pl.LazyFrame) -> pl.LazyFrame:
    """Expand the sparse demand series to a contiguous monthly grid per item.

    ADI is only meaningful over a complete calendar: a month with no receipt is a
    real zero-demand observation, not a missing one. For each item we build the
    month-start range spanning its first to last observed demand and left-join the
    actual demand back, filling the gaps with zero.
    """
    grid = (
        demand.group_by(["supplier", "item"])
        .agg(
            pl.col("period").min().alias("_start"),
            pl.col("period").max().alias("_end"),
        )
        .with_columns(
            pl.date_ranges(pl.col("_start"), pl.col("_end"), interval=_MONTHLY).alias(
                "period"
            )
        )
        .explode("period")
        .select(["supplier", "item", "period"])
    )
    return grid.join(
        demand, on=["supplier", "item", "period"], how="left"
    ).with_columns(pl.col("demand_quantity").fill_null(0.0))


def _demand_class_expr() -> pl.Expr:
    """Demand classification with history gating."""
    observations = pl.col("_observation_count")
    adi = pl.col("adi")
    cv2 = pl.col("cv_squared")

    return (
        pl.when(observations < MIN_HISTORY_FOR_FORECAST)
        .then(pl.lit(SbcClass.NEW_ITEM.value))
        .when(observations < MIN_HISTORY_FOR_SBC)
        .then(pl.lit(SbcClass.SPARSE.value))
        .when((adi < ADI_THRESHOLD) & (cv2 < CV2_THRESHOLD))
        .then(pl.lit(SbcClass.SMOOTH.value))
        .when((adi < ADI_THRESHOLD) & (cv2 >= CV2_THRESHOLD))
        .then(pl.lit(SbcClass.ERRATIC.value))
        .when((adi >= ADI_THRESHOLD) & (cv2 < CV2_THRESHOLD))
        .then(pl.lit(SbcClass.INTERMITTENT.value))
        .otherwise(pl.lit(SbcClass.LUMPY.value))
        .alias("demand_class")
    )
