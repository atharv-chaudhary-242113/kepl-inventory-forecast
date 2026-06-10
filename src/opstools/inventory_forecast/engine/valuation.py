"""Inventory valuation against a snapshot date.

DOMAIN_RULES.md makes PV the authoritative price source, and API_CONTRACT.md
requires ``snapshot_date`` to be passed *explicitly* — never read from a
row-level Date column (Constitution Rule 9: no wall-clock in business logic).
This module values the closing-stock snapshot at the PV-derived unit cost,
falling back to the snapshot's own price where PV has never seen the item. All
currency stays in Polars ``Decimal``. Pure over Polars LazyFrames.
"""

from datetime import date

import polars as pl

# Decimal scale matching the ingestion money contract (ingestion/schema.py
# MONEY_SCALE). Quantity is cast into Decimal space before multiplying so the
# valuation stays Decimal (a Decimal * Float would silently downcast to Float).
_MONEY: pl.datatypes.DataTypeClass | pl.Decimal = pl.Decimal(scale=4)


def build_inventory_valuation(
    closing: pl.LazyFrame,
    pv: pl.LazyFrame,
    snapshot_date: date,
) -> pl.LazyFrame:
    """Value the closing-stock snapshot at PV-derived unit costs.

    Args:
        closing: Canonical closing-stock snapshot ``[item, qty, price, amount]``.
            ``price`` is the snapshot's own valuation price, used only as a
            fallback when PV has no record of the item.
        pv: Canonical PV ledger — the authoritative price source (DOMAIN_RULES.md
            "Inventory valuation"). The per-item unit cost is the value-weighted
            average ``sum(amount) / sum(qty)`` across all PV lines for the item.
        snapshot_date: The valuation date, stamped onto every row. Passed
            explicitly (API_CONTRACT.md) so valuation never depends on a
            row-level date or the wall clock.

    Returns:
        A LazyFrame ``[item, quantity(Float64), unit_cost(Decimal),
        inventory_value(Decimal), snapshot_date(Date)]`` — the
        Inventory_Valuation sheet contract (WORKBOOK_SCHEMA.md). One row per
        closing-stock item; ``inventory_value`` is ``quantity * unit_cost``.
    """
    pv_unit_cost = (
        pv.group_by("item")
        .agg(
            pl.col("amount").sum().alias("_pv_amount"),
            pl.col("qty").sum().alias("_pv_qty"),
        )
        # A zero-quantity PV group cannot yield a unit cost; drop it so the item
        # falls through to the closing-stock price rather than dividing by zero.
        .filter(pl.col("_pv_qty") > 0)
        .select(
            "item",
            # Decimal / Decimal -> Decimal (cast qty into Decimal space first),
            # keeping the authoritative unit cost exact.
            (pl.col("_pv_amount") / pl.col("_pv_qty").cast(_MONEY)).alias(
                "pv_unit_cost"
            ),
        )
    )

    return (
        closing.join(pv_unit_cost, on="item", how="left")
        .with_columns(
            # PV is the source of truth; the closing-stock price is the fallback
            # for items PV has never priced (coalesce keeps the first non-null).
            pl.coalesce([pl.col("pv_unit_cost"), pl.col("price")]).alias("unit_cost")
        )
        .with_columns(
            (pl.col("qty").cast(_MONEY) * pl.col("unit_cost")).alias("inventory_value"),
            # Stamp the explicit snapshot date as a Date literal on every row.
            pl.lit(snapshot_date).alias("snapshot_date"),
        )
        .select(
            pl.col("item"),
            pl.col("qty").alias("quantity"),
            pl.col("unit_cost"),
            pl.col("inventory_value"),
            pl.col("snapshot_date"),
        )
        .sort("item")
    )
