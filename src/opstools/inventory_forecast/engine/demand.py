"""Demand reconstruction from procurement lifecycle events.

DOMAIN_RULES.md ("Demand Reconstruction") states the system never receives a
direct sales ledger, so historical demand must be *inferred* from receipts (GRN),
purchases (PV), and stock snapshots. This module produces the chronological,
monthly per-item demand series the forecasting and classification layers consume.

The exact reconstruction methodology is an explicit "Pending Business Decision",
so this is the sanctioned architectural baseline: pool the GRN and PV movement
lines, bucket them to month-start, and sum quantity and value per item-month.
The function is pure over Polars LazyFrames (ARCHITECTURE.md sec 4.3).
"""

import polars as pl

# WORKBOOK_SCHEMA.md fixes Demand_History granularity to *monthly*; we truncate
# each transaction date to the first of its month so receipts within one month
# collapse into a single demand period.
_MONTHLY: str = "1mo"


def reconstruct_demand(
    grn: pl.LazyFrame,
    pv: pl.LazyFrame,
    closing: pl.LazyFrame,
) -> pl.LazyFrame:
    """Reconstruct a monthly per-item demand series from receipts and purchases.

    Args:
        grn: Canonical GRN ledger (receipts) — the physical movement signal.
        pv: Canonical PV ledger (purchases) — the authoritative value signal.
        closing: Canonical closing-stock snapshot. Accepted as part of the
            documented contract but not yet consumed: the snapshot-delta
            methodology is a Pending Business Decision (DOMAIN_RULES.md), so the
            baseline reconstructs demand from movement lines alone. Wiring it in
            must not change this signature.

    Returns:
        A LazyFrame with schema ``[period(Date, month-start), supplier(Utf8),
        item(Utf8), demand_quantity(Float64), demand_value(Decimal)]`` — the
        Demand_History sheet contract (WORKBOOK_SCHEMA.md). One row per
        (supplier, item, month) with quantity and value summed within the month.
        ``demand_value`` stays Decimal so the accumulation is exact
        (THREAT_MODEL.md "Floating-Point Errors").
    """
    # `closing` is intentionally unused in the baseline methodology; see the
    # docstring. Referencing the contract parameter keeps the public signature
    # stable for when snapshot deltas are wired in.
    del closing

    merged = pl.concat(
        [_project_demand(grn), _project_demand(pv)],
        how="vertical",
    )
    return (
        merged.group_by(["supplier", "item", "period"])
        .agg(
            pl.col("demand_quantity").sum(),
            pl.col("demand_value").sum(),
        )
        .sort(["supplier", "item", "period"])
        .select(["period", "supplier", "item", "demand_quantity", "demand_value"])
    )


def _project_demand(ledger: pl.LazyFrame) -> pl.LazyFrame:
    """Project a canonical movement ledger onto the demand contribution shape.

    Rows whose date is null are dropped: a movement with no date cannot sit on a
    chronological axis, so it cannot contribute to a time series. `dt.truncate`
    snaps each date back to its month-start, which is what makes same-month rows
    aggregate into one period upstream.
    """
    return ledger.filter(pl.col("date").is_not_null()).select(
        pl.col("date").dt.truncate(_MONTHLY).alias("period"),
        pl.col("supplier"),
        pl.col("item"),
        pl.col("qty").alias("demand_quantity"),
        pl.col("amount").alias("demand_value"),
    )
