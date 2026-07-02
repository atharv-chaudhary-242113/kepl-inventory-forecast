"""Column mapping and record validation (the ingestion contract enforcement).

This module turns a header-aligned, all-string table into the canonical,
typed, validated frame promised by API_CONTRACT.md. It owns three jobs:

* the ERP-name -> canonical-name mapping per source kind,
* fuzzy column resolution that raises `MissingColumnError` on a missing required
  column,
* casting + record validation that raises `DataValidationError` (naming the
  file, column, and offending value) on any value that breaks a domain
  constraint.

Validation here *raises* rather than silently dropping rows: bad input must fail
loudly with an actionable error, never silently with a wrong number
(Constitution Rule 7).
"""

from collections.abc import Mapping

import polars as pl

from opstools.inventory_forecast.domain import (
    MissingColumnError,
    SourceKind,
)
from opstools.inventory_forecast.ingestion import (
    blank_to_null_expr,
    forward_fill_supplier_expr,
    normalize_supplier_expr,
    normalize_token,
)

# Money is held as Polars `Decimal` from the ingestion boundary onward so that
# every downstream sum/aggregation accumulates in fixed-point, never float
# (THREAT_MODEL.md "Floating-Point Errors"). Scale 4 gives headroom for unit
# prices finer than paise while still being exact under addition.
MONEY_SCALE: int = 4

# ERP header -> canonical column name. The procurement ledgers (POV/GRN/PV) share
# one schema; closing stock is a reduced snapshot with neither supplier nor
# voucher (INPUT_SCHEMA.md "Closing Stock"), so it gets its own mapping.
_LEDGER_MAPPING: dict[str, str] = {
    "Date": "date",
    "Vch/Bill No": "voucher",
    "Particulars": "supplier",
    "Item Details": "item",
    "Qty.": "qty",
    "Unit": "unit",
    "Price": "price",
    "Amount": "amount",
}
_CLOSING_MAPPING: dict[str, str] = {
    "Item Details": "item",
    "Qty.": "qty",
    "Price": "price",
    "Amount": "amount",
}
_LEDGER_KINDS: frozenset[SourceKind] = frozenset(
    {SourceKind.POV, SourceKind.GRN, SourceKind.PV}
)

# Date formats tried in order. The first handles Excel date cells, which
# fastexcel renders as "YYYY-MM-DD HH:MM:SS" when read as text; the rest cover
# ISO and the common Indian ERP text formats. `pl.coalesce` keeps the first that
# parses, so order is precedence (most-specific first).
_DATETIME_FORMAT: str = "%Y-%m-%d %H:%M:%S"
_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%m/%d/%Y",
)


def is_ledger(kind: SourceKind) -> bool:
    """True for POV/GRN/PV (which carry date, voucher, supplier, unit)."""
    return kind in _LEDGER_KINDS


def column_mapping(kind: SourceKind) -> Mapping[str, str]:
    """ERP-header -> canonical-name mapping for the given source kind."""
    return _LEDGER_MAPPING if is_ledger(kind) else _CLOSING_MAPPING


def required_erp_columns(kind: SourceKind) -> list[str]:
    """ERP column names that must be present for this kind (the mapping keys)."""
    return list(column_mapping(kind).keys())


def canonical_columns(kind: SourceKind) -> list[str]:
    """Canonical output column order for this kind (the mapping values)."""
    return list(column_mapping(kind).values())


def map_to_canonical(
    table: pl.DataFrame,
    kind: SourceKind,
    source_label: str,
) -> pl.DataFrame:
    """Resolve ERP headers to canonical names and select only required columns.

    Matching is case- and whitespace-insensitive (INPUT_SCHEMA.md "Header
    Matching"); extra/unused columns are tolerated and dropped.

    Raises:
        MissingColumnError: a required column could not be located in `table`.
    """
    # Map each *present* column by its normalized form so we can find "qty." for
    # an expected "Qty." regardless of case/spacing.
    present: dict[str, str] = {normalize_token(c): c for c in table.columns}

    rename: dict[str, str] = {}
    missing: list[str] = []
    for erp_name, canonical in column_mapping(kind).items():
        actual = present.get(normalize_token(erp_name))
        if actual is None:
            missing.append(erp_name)
        else:
            rename[actual] = canonical

    if missing:
        msg = f"{source_label}: missing required column(s): {', '.join(missing)}"
        raise MissingColumnError(msg)

    return table.rename(rename).select(canonical_columns(kind))


def _parse_date_expr(column_name: str) -> pl.Expr:
    """Expression parsing a text date column into a Polars `Date`.

    Tries the Excel datetime form first, then each ISO/Indian format, keeping the
    first that parses (`strict=False` yields null on a miss, `coalesce` picks the
    winner). A value that matches no format becomes null and is caught by
    validation as an unparseable date.
    """
    col = pl.col(column_name)
    candidates: list[pl.Expr] = [
        col.str.to_datetime(_DATETIME_FORMAT, strict=False).dt.date(),
    ]
    candidates.extend(col.str.to_date(fmt, strict=False) for fmt in _DATE_FORMATS)
    return pl.coalesce(candidates).alias(column_name)


def _first_offending(df: pl.DataFrame, mask: pl.Expr, column_name: str) -> str:
    """Return a string sample of the first value matching `mask`, for messages."""
    sample = df.filter(mask).select(column_name)
    if sample.height == 0:
        return ""
    return str(sample.row(0)[0])


def finalize_records(
    canonical: pl.DataFrame,
    kind: SourceKind,
    source_label: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Apply canonicalization, cast to the typed schema, and extract exceptions."""
    ledger = is_ledger(kind)
    columns = canonical_columns(kind)

    # 1. Trim every text cell and turn blanks into true nulls
    lf = canonical.lazy().with_columns(blank_to_null_expr(c) for c in columns)

    # 2. Remove separator rows
    if ledger:
        lf = lf.filter(~(pl.col("supplier").is_null() & pl.col("item").is_null()))
    else:
        lf = lf.filter(pl.col("item").is_not_null())

    # 3. Forward-fill the hierarchical supplier
    if ledger:
        lf = lf.with_columns(forward_fill_supplier_expr())
        lf = lf.with_columns(normalize_supplier_expr())

    # 4. Cast into typed temporaries for validation comparison
    typed_exprs: list[pl.Expr] = [
        pl.col("qty").cast(pl.Float64, strict=False).alias("__qty"),
        pl.col("price")
        .cast(pl.Decimal(scale=MONEY_SCALE), strict=False)
        .alias("__price"),
        pl.col("amount")
        .cast(pl.Decimal(scale=MONEY_SCALE), strict=False)
        .alias("__amount"),
    ]
    if ledger:
        typed_exprs.append(_parse_date_expr("date").alias("__date"))
    df = lf.with_columns(typed_exprs).collect()

    # Segregate clean data from bad data
    valid_df, exceptions_df = _validate(df, ledger, source_label)

    # 5. Emit the final typed frame from the clean data
    final_exprs: list[pl.Expr] = []
    for name in columns:
        if name == "qty":
            final_exprs.append(pl.col("__qty").alias("qty"))
        elif name == "price":
            final_exprs.append(pl.col("__price").alias("price"))
        elif name == "amount":
            final_exprs.append(pl.col("__amount").alias("amount"))
        elif name == "date":
            final_exprs.append(pl.col("__date").alias("date"))
        else:
            final_exprs.append(pl.col(name))

    return valid_df.select(final_exprs), exceptions_df


def _validate(
    df: pl.DataFrame, ledger: bool, source_label: str
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Filter out invalid records into an exceptions DataFrame instead of crashing."""
    exceptions = []

    # Assign temporary row numbers to track failing rows precisely
    df = df.with_row_index("__row_number")
    bad_indices = set()

    def add_exceptions(
        mask: pl.Expr, reason_template: str, col_name: str, display_name: str
    ) -> None:
        bad_rows = df.filter(mask)
        for row in bad_rows.iter_rows(named=True):
            idx = row["__row_number"]
            if idx not in bad_indices:
                bad_indices.add(idx)
                # Strip internal temporaries for a clean JSON-like record dump
                clean_row = {k: v for k, v in row.items() if not k.startswith("__")}
                exceptions.append(
                    {
                        "File Name": source_label,
                        "Row Number": idx + 2,  # +2 accounts for 0-index and header row
                        "Reason": reason_template.format(col=display_name),
                        "Offending Value": str(row.get(col_name, "")),
                        "Full Record": str(clean_row),
                    }
                )

    # Rule: Empty item
    add_exceptions(pl.col("item").is_null(), "Empty '{col}'", "item", "Item Details")

    # Rule: Empty supplier
    if ledger:
        add_exceptions(
            pl.col("supplier").is_null(),
            "Empty '{col}' (No supplier to inherit)",
            "supplier",
            "Particulars",
        )

    # Rule: Numeric parsing and negative amounts
    for canonical_name, typed_name in (
        ("Qty.", "__qty"),
        ("Price", "__price"),
        ("Amount", "__amount"),
    ):
        source_col = {"__qty": "qty", "__price": "price", "__amount": "amount"}[
            typed_name
        ]

        # Unparseable strings
        add_exceptions(
            pl.col(typed_name).is_null() & pl.col(source_col).is_not_null(),
            "Non-numeric value in '{col}'",
            source_col,
            canonical_name,
        )

        # Negative financials (Qty omitted intentionally per business rule)
        if typed_name in ("__price", "__amount"):
            add_exceptions(
                pl.col(typed_name) < 0,
                "Negative value in '{col}'",
                typed_name,
                canonical_name,
            )

    # Rule: Unparseable dates
    if ledger:
        add_exceptions(
            pl.col("__date").is_null() & pl.col("date").is_not_null(),
            "Unparseable date in '{col}'",
            "date",
            "Date",
        )

    # Extract valid rows and construct the exceptions frame
    valid_df = df.filter(~pl.col("__row_number").is_in(list(bad_indices))).drop(
        "__row_number"
    )

    exc_schema = {
        "File Name": pl.Utf8,
        "Row Number": pl.Int64,
        "Reason": pl.Utf8,
        "Offending Value": pl.Utf8,
        "Full Record": pl.Utf8,
    }

    exc_df = (
        pl.DataFrame(exceptions, schema=exc_schema)
        if exceptions
        else pl.DataFrame(schema=exc_schema)
    )
    return valid_df, exc_df
