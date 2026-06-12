"""Suspected supplier-partnership detection (review signal only).

DOMAIN_RULES.md ("Supplier Partnership Detection") asks the system to *flag*
supplier pairs whose procurement behaviour co-occurs frequently (observed
frequency >= 3) for human review — and explicitly forbids concluding collusion or
fraud automatically. We approximate co-occurrence by counting the distinct
(item, month) cells in which two suppliers both transact. The Rust review flagged
two defects we avoid here: mirror duplicates (we keep a canonical supplier_a
supplier_b ordering) and a hardcoded confidence (ours is derived from the event
count). Pure over Polars LazyFrames.
"""

import polars as pl

from opstools.inventory_forecast.config.settings import Settings

# DOMAIN_RULES.md threshold: a pair is only surfaced at >= 3 co-occurrence events.
_MIN_FREQUENCY: int = 3
# Monthly grid, matching Demand_History granularity (WORKBOOK_SCHEMA.md).
_MONTHLY: str = "1mo"
# The status label written to the sheet. Deliberately "suspected" — never a
# fraud/collusion conclusion (DOMAIN_RULES.md).
_STATUS: str = "suspected"


def detect_partnerships(pov: pl.LazyFrame, cfg: Settings) -> pl.LazyFrame:
    """Flag supplier pairs that frequently co-supply the same item in the same month.

    Args:
        pov: Canonical POV ledger (the replenishment/demand signal). Null-dated
            rows cannot be placed on the monthly axis and are excluded.
        cfg: Run settings (reserved; the frequency threshold is a domain constant).

    Returns:
        A LazyFrame ``[supplier_a, supplier_b, matching_events(Int64),
        confidence_score(Float64), status(Utf8)]`` — the Supplier_Partnerships
        sheet contract (WORKBOOK_SCHEMA.md). One row per suspected pair, with
        ``supplier_a < supplier_b`` so a pair is never mirror-duplicated.
    """
    _ = cfg  # reserved for a configurable frequency threshold.

    # Distinct (supplier, item, month) cells — duplicates within a month must not
    # inflate the co-occurrence count, so de-duplicate before the self-join.
    events = (
        pov.filter(pl.col("date").is_not_null())
        .select(
            pl.col("supplier"),
            pl.col("date").dt.truncate(_MONTHLY).alias("period"),
            pl.col("item"),
        )
        .unique()
    )

    # Self-join on (item, period): each match is one month in which both suppliers
    # transacted the item. The strict `<` filter keeps a single canonical row per
    # unordered pair (drops self-pairs and the (B, A) mirror in one step).
    return (
        events.join(events, on=["item", "period"], how="inner")
        .filter(pl.col("supplier") < pl.col("supplier_right"))
        .rename({"supplier": "supplier_a", "supplier_right": "supplier_b"})
        .group_by(["supplier_a", "supplier_b"])
        .agg(pl.len().alias("matching_events"))
        .filter(pl.col("matching_events") >= _MIN_FREQUENCY)
        .with_columns(
            # Monotone in the event count, bounded in (0, 1): 3 events -> 0.75,
            # rising toward 1.0 as co-occurrence grows. Not a hardcoded sentinel.
            (1.0 - 1.0 / (1.0 + pl.col("matching_events").cast(pl.Float64))).alias(
                "confidence_score"
            ),
            pl.lit(_STATUS).alias("status"),
        )
        .select(
            [
                "supplier_a",
                "supplier_b",
                pl.col("matching_events").cast(pl.Int64),
                "confidence_score",
                "status",
            ]
        )
        .sort(["supplier_a", "supplier_b"])
    )
