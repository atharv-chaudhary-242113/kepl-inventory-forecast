"""Pure Polars expression builders for the canonicalization sequence.

These implement steps 3-5 of INPUT_SCHEMA.md "Canonicalization Order"
(remove separators -> forward-fill grouped columns -> normalize supplier). They
are pure expression/transform builders with no I/O, so they unit-test headless
and compose into the ingestion pipeline (reader.py).
"""

import polars as pl

# Matches an ERP branch suffix: optional surrounding whitespace around a
# parenthetical group, e.g. " (Noida)". `[^)]*` (not `.*`) cannot backtrack
# catastrophically and stops at the first ')', which is exactly the single
# trailing branch tag we strip (DOMAIN_RULES.md "Supplier Normalization").
_BRANCH_SUFFIX_PATTERN: str = r"\s*\([^)]*\)\s*"


def blank_to_null_expr(column_name: str) -> pl.Expr:
    """Trim a string column and convert blank/whitespace-only cells to null.

    ERP cells arrive as "" or " " for empties; collapsing them to a true null is
    what lets `forward_fill` see them as gaps and lets emptiness checks be a
    single `is_null`. The surviving values are also stripped of stray padding.
    """
    trimmed = pl.col(column_name).str.strip_chars()
    return (
        pl.when(trimmed.str.len_chars() == 0)
        .then(None)
        .otherwise(trimmed)
        .alias(column_name)
    )


def forward_fill_supplier_expr(column_name: str = "supplier") -> pl.Expr:
    """Forward-fill the (null-normalized) supplier column.

    INPUT_SCHEMA.md "Forward-Fill Rule": an item row with an empty supplier
    inherits the most recent non-empty supplier printed above it. Relies on
    blanks already being null (see `blank_to_null_expr`), because `forward_fill`
    fills nulls, not empty strings.
    """
    return pl.col(column_name).forward_fill().alias(column_name)


def normalize_supplier_expr(column_name: str = "supplier") -> pl.Expr:
    """Strip parenthetical branch suffixes to a canonical supplier identifier.

    "ABC Electricals (Noida)" -> "ABC Electricals" (DOMAIN_RULES.md). Runs after
    forward-fill (INPUT_SCHEMA.md order) and re-trims, since removing a leading
    "(...)" can leave edge whitespace.
    """
    return (
        pl.col(column_name)
        .str.replace_all(_BRANCH_SUFFIX_PATTERN, "")
        .str.strip_chars()
        .alias(column_name)
    )
