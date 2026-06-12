"""FIFO lead-time matching between purchase orders (POV) and receipts (GRN).

DOMAIN_RULES.md ("Lead-Time Rules") mandates chronological FIFO matching of
orders to receipts per (supplier, item): the oldest unmatched order is filled
first, and partial deliveries are valid in both directions (one order filled by
many receipts, one receipt covering many orders).

A naive equi-join cannot express FIFO — it produces a Cartesian product that
inflates every downstream metric. Instead, we match on *cumulative quantity
intervals*: lay each item's orders end-to-end on a unit axis ``[A_{i-1}, A_i)``
and its receipts on the same axis ``[B_{j-1}, B_j]``; the k-th ordered unit is
fulfilled by the k-th received unit, so order i and receipt j are matched on the
*overlap* of their intervals, and the overlap length is the allocated quantity.
This is a fully vectorized Polars formulation of FIFO (PERFORMANCE_BUDGET.md sec 4
asks us to keep this stage out of a Python row loop). Pure over LazyFrames.
"""

import polars as pl


def compute_lead_time(pov: pl.LazyFrame, grn: pl.LazyFrame) -> pl.LazyFrame:
    """FIFO-match orders to receipts per (supplier, item), oldest order first.

    Args:
        pov: Canonical POV ledger (orders). Carries ``voucher`` for downstream
            Pending_Deliveries linkage. Dates are already Polars ``Date`` from
            ingestion; rows with a null date cannot be placed chronologically and
            are excluded from matching.
        grn: Canonical GRN ledger (receipts).

    Returns:
        A LazyFrame with one row per (order, receipt) allocation, plus one row for
        any order that received nothing (``grn_date``/``lead_time_days`` null,
        ``delivered_qty`` 0). Schema: ``[order_id, supplier, item, voucher_number,
        pov_date, grn_date, ordered_qty, delivered_qty, lead_time_days]``. This is
        a superset of the Lead_Time_Analysis sheet (which drops ``order_id`` and
        ``voucher_number``); ``order_id`` is an internal per-order-line key that
        ``build_pending_deliveries`` aggregates on, and ``delivered_qty`` is the
        quantity *this* receipt allocated to the order. ``lead_time_days`` is
        ``grn_date - pov_date`` in whole days.
    """
    orders = _order_intervals(pov)
    deliveries = _delivery_intervals(grn)

    # Join within each (supplier, item) group, then keep only pairs whose unit
    # intervals overlap. The overlap length IS the FIFO-allocated quantity.
    allocations = (
        orders.join(deliveries, on=["supplier", "item"], how="inner")
        .with_columns(
            (
                pl.min_horizontal("cum_after_o", "cum_after_d")
                - pl.max_horizontal("cum_before_o", "cum_before_d")
            ).alias("delivered_qty")
        )
        .filter(pl.col("delivered_qty") > 0)
        .with_columns(
            (pl.col("grn_date") - pl.col("pov_date"))
            .dt.total_days()
            .alias("lead_time_days")
        )
        .select(["order_id", "grn_date", "delivered_qty", "lead_time_days"])
    )

    # Left-join allocations back onto every order so orders that received nothing
    # still surface (with a null receipt) — they are fully pending downstream.
    return (
        orders.join(allocations, on="order_id", how="left")
        .with_columns(pl.col("delivered_qty").fill_null(0.0))
        .select(
            [
                "order_id",
                "supplier",
                "item",
                "voucher_number",
                "pov_date",
                "grn_date",
                "ordered_qty",
                "delivered_qty",
                "lead_time_days",
            ]
        )
        .sort(["supplier", "item", "pov_date", "order_id", "grn_date"])
    )


def _order_intervals(pov: pl.LazyFrame) -> pl.LazyFrame:
    """Lay each item's orders on a cumulative unit axis, oldest first.

    ``order_id`` is the original row index: it both uniquely identifies an order
    line (so two identical orders stay distinct) and breaks date ties
    deterministically, which reproducibility demands (Constitution Rule 9). The
    ``cum_sum().over`` runs after the sort, so the cumulative axis follows
    chronological FIFO order.
    """
    return (
        pov.with_row_index("order_id")
        .filter(pl.col("date").is_not_null())
        .sort(["supplier", "item", "date", "order_id"])
        .with_columns(
            pl.col("qty").cum_sum().over(["supplier", "item"]).alias("cum_after_o")
        )
        .with_columns((pl.col("cum_after_o") - pl.col("qty")).alias("cum_before_o"))
        .select(
            [
                "order_id",
                "supplier",
                "item",
                pl.col("voucher").alias("voucher_number"),
                pl.col("date").alias("pov_date"),
                pl.col("qty").alias("ordered_qty"),
                "cum_before_o",
                "cum_after_o",
            ]
        )
    )


def _delivery_intervals(grn: pl.LazyFrame) -> pl.LazyFrame:
    """Lay each item's receipts on the same cumulative unit axis, oldest first."""
    return (
        grn.with_row_index("delivery_id")
        .filter(pl.col("date").is_not_null())
        .sort(["supplier", "item", "date", "delivery_id"])
        .with_columns(
            pl.col("qty").cum_sum().over(["supplier", "item"]).alias("cum_after_d")
        )
        .with_columns((pl.col("cum_after_d") - pl.col("qty")).alias("cum_before_d"))
        .select(
            [
                "supplier",
                "item",
                pl.col("date").alias("grn_date"),
                "cum_before_d",
                "cum_after_d",
            ]
        )
    )
