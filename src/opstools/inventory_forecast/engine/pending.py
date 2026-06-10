"""Pending-delivery detection from FIFO-matched orders.

DOMAIN_RULES.md ("Pending Deliveries"): a delivery is pending when, for a matched
procurement relationship, ordered quantity exceeds delivered quantity. This
module rolls the per-allocation lead-time frame back up to one row per order line
and keeps the orders that remain short. Pure over Polars LazyFrames.
"""

import polars as pl


def build_pending_deliveries(matched: pl.LazyFrame) -> pl.LazyFrame:
    """Surface order lines whose ordered quantity still exceeds what was received.

    Args:
        matched: The FIFO allocation frame from ``compute_lead_time`` — possibly
            many rows per order (one per receipt), plus a null-receipt row for
            orders that received nothing. ``order_id`` identifies the order line.

    Returns:
        A LazyFrame ``[supplier, item, voucher_number, ordered_qty,
        delivered_qty, pending_qty, order_date, age_days]`` — the
        Pending_Deliveries sheet contract (WORKBOOK_SCHEMA.md). One row per still-
        open order line. ``delivered_qty`` is the total received against that
        order (summed across all its receipts); ``pending_qty`` is the shortfall.
    """
    per_order = (
        matched.group_by("order_id")
        .agg(
            pl.col("supplier").first(),
            pl.col("item").first(),
            pl.col("voucher_number").first(),
            pl.col("pov_date").first().alias("order_date"),
            pl.col("ordered_qty").first(),
            # Sum every receipt allocated to this order; an order that received
            # nothing has a single 0.0 allocation row and sums to 0.
            pl.col("delivered_qty").sum().alias("delivered_qty"),
        )
        .with_columns(
            (pl.col("ordered_qty") - pl.col("delivered_qty")).alias("pending_qty")
        )
        .filter(pl.col("pending_qty") > 0)
    )

    return (
        per_order.with_columns(
            # Age relative to the most recent order in the dataset, not a wall
            # clock: business logic must stay deterministic (Constitution Rule 9),
            # so the latest order date stands in for "today".
            (pl.col("order_date").max() - pl.col("order_date"))
            .dt.total_days()
            .alias("age_days")
        )
        .select(
            [
                "supplier",
                "item",
                "voucher_number",
                "ordered_qty",
                "delivered_qty",
                "pending_qty",
                "order_date",
                "age_days",
            ]
        )
        .sort(["supplier", "item", "order_date", "voucher_number"])
    )
