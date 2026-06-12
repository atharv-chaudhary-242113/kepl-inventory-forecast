"""Price-variance analytics per (supplier, item).

Surfaces how much the unit price paid for an item swings across PV lines — a
sourcing-consistency and audit signal. Money summaries (min/max/mean/range) stay
Decimal-exact (THREAT_MODEL.md "Floating-Point Errors"); the *dispersion* metric
(price_stddev) is a statistic, not accumulated currency, so it is computed in
Float64. Pure over Polars LazyFrames.
"""

import polars as pl

# Decimal money scale (ingestion/schema.py MONEY_SCALE).
_MONEY: pl.datatypes.DataTypeClass | pl.Decimal = pl.Decimal(scale=4)


def build_price_variance(pv: pl.LazyFrame) -> pl.LazyFrame:
    """Summarize unit-price dispersion per (supplier, item) from the PV ledger.

    Args:
        pv: Canonical PV ledger — the authoritative price source (DOMAIN_RULES.md).
            ``price`` is the per-line unit price.

    Returns:
        A LazyFrame ``[supplier, item, line_count(Int64), min_price(Decimal),
        max_price(Decimal), mean_price(Decimal), price_range(Decimal),
        price_stddev(Float64)]``, sorted by (supplier, item).
    """
    return (
        pv.group_by(["supplier", "item"])
        .agg(
            pl.len().alias("line_count"),
            pl.col("price").min().alias("min_price"),
            pl.col("price").max().alias("max_price"),
            # Mean kept exact as Decimal sum / Decimal count (Polars has no Decimal
            # .mean()); cast the count into Decimal space so the result stays Decimal.
            pl.col("price").sum().alias("_price_sum"),
            # Dispersion is a statistic, not money to accumulate -> Float64 is fine.
            pl.col("price").cast(pl.Float64).std(ddof=1).alias("price_stddev"),
        )
        .with_columns(
            (pl.col("_price_sum") / pl.col("line_count").cast(_MONEY)).alias(
                "mean_price"
            ),
            (pl.col("max_price") - pl.col("min_price")).alias("price_range"),
            # A single line has undefined sample std; report 0 dispersion.
            pl.col("price_stddev").fill_null(0.0),
        )
        .select(
            [
                "supplier",
                "item",
                pl.col("line_count").cast(pl.Int64),
                "min_price",
                "max_price",
                "mean_price",
                "price_range",
                "price_stddev",
            ]
        )
        .sort(["supplier", "item"])
    )
