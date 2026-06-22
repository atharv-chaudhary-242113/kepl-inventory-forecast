"""Fill-rate (fulfillment) analytics per (supplier, item).

Fill rate is the fraction of ordered quantity actually received, derived from the
FIFO lead-time allocations. ``ordered_qty`` repeats across an order's allocation
rows, so order lines are de-duplicated by ``order_id`` before aggregation. The
fulfillment status uses the FulfillmentStatus enum. Pure over Polars LazyFrames.
"""

import polars as pl

from opstools.inventory_forecast.domain import FulfillmentStatus


def build_fill_rate(lead_time: pl.LazyFrame) -> pl.LazyFrame:
    """Compute per-(supplier, item) fill rate and a fulfillment status.

    Args:
        lead_time: FIFO allocation frame from ``compute_lead_time`` (one row per
            order/receipt allocation, plus a null-receipt row per undelivered
            order). ``delivered_qty`` is the per-allocation quantity; ``ordered_qty``
            is the order-line total repeated across its allocation rows.

    Returns:
        A LazyFrame ``[supplier, item, ordered_qty(Float64), delivered_qty(Float64),
        fill_rate(Float64), fulfillment_status(Utf8)]``, sorted by (supplier, item).
    """
    # De-duplicate to one row per order line first so ordered_qty is not counted
    # once per receipt; delivered_qty sums across this order's receipts.
    per_order = lead_time.group_by("order_id").agg(
        pl.col("supplier").first(),
        pl.col("item").first(),
        pl.col("ordered_qty").first(),
        pl.col("delivered_qty").sum().alias("delivered_qty"),
    )

    return (
        per_order.group_by(["supplier", "item"])
        .agg(
            pl.col("ordered_qty").sum().alias("ordered_qty"),
            pl.col("delivered_qty").sum().alias("delivered_qty"),
        )
        .with_columns(
            pl.when(pl.col("ordered_qty") > 0)
            .then(pl.col("delivered_qty") / pl.col("ordered_qty"))
            .otherwise(0.0)
            .alias("fill_rate")
        )
        .with_columns(_status_expr())
        .select(
            [
                "supplier",
                "item",
                "ordered_qty",
                "delivered_qty",
                "fill_rate",
                "fulfillment_status",
            ]
        )
        .sort(["supplier", "item"])
    )


def _status_expr() -> pl.Expr:
    """Bucket the fill rate into a FulfillmentStatus (DOMAIN_RULES.md pending rules)."""
    rate = pl.col("fill_rate")
    return (
        pl.when(rate <= 0.0)
        .then(pl.lit(FulfillmentStatus.PENDING.value))
        .when(rate < 1.0)
        .then(pl.lit(FulfillmentStatus.PARTIAL.value))
        .otherwise(pl.lit(FulfillmentStatus.COMPLETE.value))
        .alias("fulfillment_status")
    )
