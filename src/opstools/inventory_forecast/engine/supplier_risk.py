"""Supplier analysis: spend, delivery performance, and composite risk.

Builds the Supplier_Analysis sheet (WORKBOOK_SCHEMA.md) by joining three upstream
engine outputs per supplier: the FIFO lead-time allocations (compute_lead_time),
the pending-delivery lines (build_pending_deliveries), and the PV-sourced
financial summary (build_financial_summary). DOMAIN_RULES.md ("Supplier Risk")
makes risk a *composite* metric whose exact weighting is pending business
validation, so the component weights live as named constants here and both scores
are bounded to [0, 1]. Pure over Polars LazyFrames.
"""

import polars as pl

from opstools.inventory_forecast.config.settings import Settings

# Decimal money scale (ingestion/schema.py MONEY_SCALE). total_spend stays Decimal.
_MONEY: pl.datatypes.DataTypeClass | pl.Decimal = pl.Decimal(scale=4)

# Composite-risk weights (DOMAIN_RULES.md flags the methodology as pending
# validation). They sum to 1.0 so the resulting risk_score is already in [0, 1]:
#   - shortfall    : unmet demand (1 - fill_rate) — the strongest reliability signal
#   - pending      : share of order lines still open
#   - lead-time CV : lead-time volatility (stddev / mean), a delivery-consistency proxy
_W_SHORTFALL: float = 0.5
_W_PENDING: float = 0.3
_W_LEADTIME_CV: float = 0.2


def build_supplier_analysis(
    lead_time: pl.LazyFrame,
    pending: pl.LazyFrame,
    financial: pl.LazyFrame,
    cfg: Settings,
) -> pl.LazyFrame:
    """Aggregate per-supplier spend, delivery stats, and composite risk.

    Args:
        lead_time: FIFO allocation frame from ``compute_lead_time`` (one row per
            order/receipt allocation, plus a null-receipt row per undelivered
            order). ``ordered_qty`` repeats across an order's allocation rows, so
            order-level totals are de-duplicated by ``order_id`` first.
        pending: Pending-delivery lines from ``build_pending_deliveries`` (one row
            per still-open order line).
        financial: Financial summary from ``build_financial_summary``
            (per supplier/item PV spend).
        cfg: Run settings (reserved; the risk weights are module constants for now
            so the signature stays stable when they become configurable).

    Returns:
        A LazyFrame ``[supplier, total_spend(Decimal), total_orders(Int64),
        total_deliveries(Int64), average_lead_time(Float64),
        lead_time_stddev(Float64), pending_deliveries(Int64),
        reliability_score(Float64), risk_score(Float64)]`` — the Supplier_Analysis
        sheet contract (WORKBOOK_SCHEMA.md), sorted by supplier.
    """
    _ = cfg  # reserved for configurable risk weights.

    # Roll allocations up to one row per order line first: ordered_qty is repeated
    # on every allocation row, so summing it raw would multi-count it.
    per_order = lead_time.group_by("order_id").agg(
        pl.col("supplier").first(),
        pl.col("ordered_qty").first(),
        pl.col("delivered_qty").sum().alias("delivered_qty"),
    )
    order_stats = per_order.group_by("supplier").agg(
        pl.len().alias("total_orders"),
        pl.col("ordered_qty").sum().alias("_ordered"),
        pl.col("delivered_qty").sum().alias("_delivered"),
    )

    # Lead-time statistics are per *allocation* (one per receipt), so compute them
    # from the raw frame, counting only rows that carried a real receipt.
    lt_stats = (
        lead_time.filter(pl.col("grn_date").is_not_null())
        .group_by("supplier")
        .agg(
            pl.col("lead_time_days").mean().alias("average_lead_time"),
            pl.col("lead_time_days").std(ddof=1).alias("lead_time_stddev"),
            pl.len().alias("total_deliveries"),
        )
    )

    pending_stats = pending.group_by("supplier").agg(
        pl.len().alias("pending_deliveries")
    )
    spend_stats = financial.group_by("supplier").agg(
        pl.col("total_spend").sum().alias("total_spend")
    )

    # A supplier may appear in any subset of the four sources (e.g. PV spend with
    # no POV), so build the supplier universe by union before left-joining each.
    universe = (
        pl.concat(
            [
                order_stats.select("supplier"),
                lt_stats.select("supplier"),
                pending_stats.select("supplier"),
                spend_stats.select("supplier"),
            ],
            how="vertical",
        )
        .unique()
        .sort("supplier")
    )

    joined = (
        universe.join(order_stats, on="supplier", how="left")
        .join(lt_stats, on="supplier", how="left")
        .join(pending_stats, on="supplier", how="left")
        .join(spend_stats, on="supplier", how="left")
        .with_columns(
            pl.col("total_orders").fill_null(0),
            pl.col("total_deliveries").fill_null(0),
            pl.col("pending_deliveries").fill_null(0),
            pl.col("total_spend").fill_null(pl.lit(0, dtype=_MONEY)),
        )
    )

    return (
        joined.with_columns(
            # fill_rate is delivered / ordered; with no orders it is undefined and
            # treated as a perfect fill (no shortfall *evidence*), not a failure.
            pl.when(pl.col("_ordered") > 0)
            .then(pl.col("_delivered") / pl.col("_ordered"))
            .otherwise(None)
            .alias("_fill_rate"),
            # CV = stddev / mean lead time; a delivery-consistency proxy in [0, 1].
            pl.when(pl.col("average_lead_time") > 0)
            .then(pl.col("lead_time_stddev") / pl.col("average_lead_time"))
            .otherwise(0.0)
            .alias("_lt_cv"),
        )
        .with_columns(
            # Reliability is the fill rate, clipped; missing -> 0 (no delivery proof).
            pl.col("_fill_rate")
            .fill_null(0.0)
            .clip(lower_bound=0.0, upper_bound=1.0)
            .alias("reliability_score"),
            # Risk components, each bounded to [0, 1] before the weighted sum.
            (1.0 - pl.coalesce([pl.col("_fill_rate"), pl.lit(1.0)]))
            .clip(lower_bound=0.0, upper_bound=1.0)
            .alias("_shortfall"),
            pl.when(pl.col("total_orders") > 0)
            .then(pl.col("pending_deliveries") / pl.col("total_orders"))
            .otherwise(0.0)
            .clip(lower_bound=0.0, upper_bound=1.0)
            .alias("_pending_ratio"),
            pl.col("_lt_cv").clip(lower_bound=0.0, upper_bound=1.0).alias("_lt_cv"),
        )
        .with_columns(
            (
                _W_SHORTFALL * pl.col("_shortfall")
                + _W_PENDING * pl.col("_pending_ratio")
                + _W_LEADTIME_CV * pl.col("_lt_cv")
            )
            .clip(lower_bound=0.0, upper_bound=1.0)
            .alias("risk_score")
        )
        .select(
            [
                "supplier",
                "total_spend",
                pl.col("total_orders").cast(pl.Int64),
                pl.col("total_deliveries").cast(pl.Int64),
                "average_lead_time",
                "lead_time_stddev",
                pl.col("pending_deliveries").cast(pl.Int64),
                "reliability_score",
                "risk_score",
            ]
        )
        .sort("supplier")
    )
