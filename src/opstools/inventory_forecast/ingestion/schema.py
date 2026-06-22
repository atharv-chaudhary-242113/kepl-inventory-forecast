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
    DataValidationError,
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
) -> pl.DataFrame:
    """Apply canonicalization, cast to the typed schema, and validate.

    Input is an all-string frame with canonical column names. Sequence follows
    INPUT_SCHEMA.md "Canonicalization Order": blank-normalize -> drop separator
    rows -> forward-fill + normalize supplier (ledgers only) -> cast -> validate.

    Output frame schema:
        ledger: [date(Date), voucher(Utf8), supplier(Utf8), item(Utf8),
                 qty(Float64), unit(Utf8), price(Decimal), amount(Decimal)]
        closing stock: [item(Utf8), qty(Float64), price(Decimal), amount(Decimal)]

    Raises:
        DataValidationError: an empty item/supplier, an unparseable or negative
            numeric, or an unparseable (non-blank) date.
    """
    ledger = is_ledger(kind)
    columns = canonical_columns(kind)

    # 1. Trim every text cell and turn blanks into true nulls so that emptiness is
    #    a single is_null check and forward-fill sees real gaps.
    lf = canonical.lazy().with_columns(blank_to_null_expr(c) for c in columns)

    # 2. Remove separator rows. INPUT_SCHEMA.md: a row is a formatting separator
    #    only when BOTH grouping fields are empty (ledger) — for closing stock
    #    there is no supplier, so an empty item alone marks the separator.
    if ledger:
        lf = lf.filter(~(pl.col("supplier").is_null() & pl.col("item").is_null()))
    else:
        lf = lf.filter(pl.col("item").is_not_null())

    # 3. Forward-fill the hierarchical supplier, then strip its branch suffix.
    if ledger:
        lf = lf.with_columns(forward_fill_supplier_expr())
        lf = lf.with_columns(normalize_supplier_expr())

    # 4. Cast into typed temporaries (suffixed) so validation can compare the
    #    typed result against the original string to tell "blank" from
    #    "unparseable" (strict=False => a bad value casts to null, not an error).
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

    _validate(df, ledger, source_label)

    # 5. Emit the final typed frame in canonical order, swapping the string
    #    qty/price/amount/date for their validated typed versions.
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
    return df.select(final_exprs)


def _validate(df: pl.DataFrame, ledger: bool, source_label: str) -> None:
    """Raise DataValidationError on the first record-level constraint breach."""
    # Empty item — never valid (INPUT_SCHEMA.md "Validation Rules").
    if df.filter(pl.col("item").is_null()).height > 0:
        msg = f"{source_label}: found a record with an empty 'Item Details'"
        raise DataValidationError(msg)

    # Empty supplier after forward-fill — means rows preceded any supplier header.
    if ledger and df.filter(pl.col("supplier").is_null()).height > 0:
        msg = (
            f"{source_label}: found a record with no supplier; the first data "
            "rows appear before any 'Particulars' value to inherit"
        )
        raise DataValidationError(msg)

    # Numeric columns: unparseable (non-blank but cast to null), then negative.
    for canonical_name, typed_name in (
        ("Qty.", "__qty"),
        ("Price", "__price"),
        ("Amount", "__amount"),
    ):
        source_col = {
            "__qty": "qty",
            "__price": "price",
            "__amount": "amount",
        }[typed_name]
        unparseable = pl.col(typed_name).is_null() & pl.col(source_col).is_not_null()
        if df.filter(unparseable).height > 0:
            example = _first_offending(df, unparseable, source_col)
            msg = (
                f"{source_label}: non-numeric value '{example}' "
                f"in column '{canonical_name}'"
            )
            raise DataValidationError(msg)

        negative = pl.col(typed_name) < 0
        if df.filter(negative).height > 0:
            example = _first_offending(df, negative, typed_name)
            msg = (
                f"{source_label}: negative value '{example}' "
                f"in column '{canonical_name}'"
            )
            raise DataValidationError(msg)

    # Dates (ledgers): a non-blank value that matched no known format is invalid.
    # A genuinely blank date is left null (the canonical schema allows it).
    if ledger:
        bad_date = pl.col("__date").is_null() & pl.col("date").is_not_null()
        if df.filter(bad_date).height > 0:
            example = _first_offending(df, bad_date, "date")
            msg = f"{source_label}: unparseable date '{example}' in column 'Date'"
            raise DataValidationError(msg)
