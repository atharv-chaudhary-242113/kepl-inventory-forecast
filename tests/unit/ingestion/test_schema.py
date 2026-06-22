"""Unit tests for column mapping, kind metadata, and record validation."""

import polars as pl
import pytest

from opstools.inventory_forecast.domain import (
    DataValidationError,
    MissingColumnError,
    SourceKind,
)
from opstools.inventory_forecast.ingestion import schema

# noinspection PyProtectedMember
from opstools.inventory_forecast.ingestion.schema import (
    _first_offending,
    _validate,
)


@pytest.mark.parametrize("kind", [SourceKind.POV, SourceKind.GRN, SourceKind.PV])
def test_ledger_kinds_are_ledgers(kind):
    assert schema.is_ledger(kind)
    assert schema.canonical_columns(kind) == [
        "date",
        "voucher",
        "supplier",
        "item",
        "qty",
        "unit",
        "price",
        "amount",
    ]


def test_closing_stock_is_reduced_schema():
    assert not schema.is_ledger(SourceKind.CLOSING_STOCK)
    assert schema.required_erp_columns(SourceKind.CLOSING_STOCK) == [
        "Item Details",
        "Qty.",
        "Price",
        "Amount",
    ]
    assert schema.canonical_columns(SourceKind.CLOSING_STOCK) == [
        "item",
        "qty",
        "price",
        "amount",
    ]


def test_map_to_canonical_is_fuzzy_and_drops_extras():
    table = pl.DataFrame(
        {
            " date ": ["2025-01-01"],
            "VCH/BILL NO": ["V1"],
            "particulars": ["ABC"],
            "item details": ["Wire"],
            "qty.": ["1"],
            "unit": ["Nos"],
            "price": ["1"],
            "amount": ["1"],
            "Ignored Extra": ["x"],
        }
    )
    out = schema.map_to_canonical(table, SourceKind.POV, "pov.xlsx")
    assert out.columns == schema.canonical_columns(SourceKind.POV)


def test_map_to_canonical_closing_stock_uses_reduced_mapping():
    table = pl.DataFrame(
        {
            "Item Details": ["Wire"],
            "Qty.": ["1"],
            "Price": ["2"],
            "Amount": ["2"],
            "Particulars": ["ignored"],
        }
    )
    out = schema.map_to_canonical(table, SourceKind.CLOSING_STOCK, "stock.csv")

    assert out.columns == ["item", "qty", "price", "amount"]


def test_map_to_canonical_missing_column_raises_missing_column_error():
    table = pl.DataFrame({"Date": ["2025-01-01"], "Particulars": ["ABC"]})
    with pytest.raises(MissingColumnError):
        schema.map_to_canonical(table, SourceKind.PV, "pv.csv")


def _ledger_frame(rows: dict[str, list[str | None]]) -> pl.DataFrame:
    # Build an all-string canonical frame (the shape map_to_canonical emits).
    return pl.DataFrame(rows, schema=dict.fromkeys(rows, pl.String))


def test_finalize_ledger_happy_path_types_and_fill():
    df = _ledger_frame(
        {
            "date": ["2025-01-05", None, "2025-01-20"],
            "voucher": ["PO001", "PO002", "PO003"],
            "supplier": ["ABC Electricals (Noida)", None, "XYZ Traders (Delhi)"],
            "item": ["Wire", "Tape", "Pipe"],
            "qty": ["10", "5", "3"],
            "unit": ["Nos", "Nos", "Box"],
            "price": ["100.25", "50.10", "20"],
            "amount": ["1002.50", "250.50", "60"],
        }
    )
    out = schema.finalize_records(df, SourceKind.POV, "pov.xlsx")
    assert out.schema["date"] == pl.Date
    assert out.schema["qty"] == pl.Float64
    assert out.schema["price"] == pl.Decimal(scale=schema.MONEY_SCALE)
    # forward-fill + normalization collapse the branch onto the prior supplier.
    assert out["supplier"].to_list() == [
        "ABC Electricals",
        "ABC Electricals",
        "XYZ Traders",
    ]
    # A blank ledger date is permitted to stay null (canonical schema allows it).
    assert out["date"].to_list()[1] is None


def test_finalize_drops_separator_rows():
    df = _ledger_frame(
        {
            "date": ["2025-01-05", None, None],
            "voucher": ["PO001", None, None],
            "supplier": ["ABC", None, None],  # last row: both supplier & item empty
            "item": ["Wire", "Tape", None],
            "qty": ["10", "5", None],
            "unit": ["Nos", "Nos", None],
            "price": ["1", "1", None],
            "amount": ["1", "1", None],
        }
    )
    out = schema.finalize_records(df, SourceKind.POV, "pov.xlsx")
    assert out.height == 2  # the all-empty separator row is removed


def test_finalize_rejects_negative_quantity():
    df = _ledger_frame(
        {
            "date": ["2025-01-05"],
            "voucher": ["PO1"],
            "supplier": ["ABC"],
            "item": ["Wire"],
            "qty": ["-5"],
            "unit": ["Nos"],
            "price": ["1"],
            "amount": ["1"],
        }
    )
    with pytest.raises(DataValidationError):
        schema.finalize_records(df, SourceKind.POV, "pov.xlsx")


def test_finalize_rejects_unparseable_amount():
    df = _ledger_frame(
        {
            "date": ["2025-01-05"],
            "voucher": ["PO1"],
            "supplier": ["ABC"],
            "item": ["Wire"],
            "qty": ["1"],
            "unit": ["Nos"],
            "price": ["1"],
            "amount": ["not-a-number"],
        }
    )
    with pytest.raises(DataValidationError):
        schema.finalize_records(df, SourceKind.POV, "pov.xlsx")


def test_finalize_rejects_unparseable_date():
    df = _ledger_frame(
        {
            "date": ["32-13-2025"],
            "voucher": ["PO1"],
            "supplier": ["ABC"],
            "item": ["Wire"],
            "qty": ["1"],
            "unit": ["Nos"],
            "price": ["1"],
            "amount": ["1"],
        }
    )
    with pytest.raises(DataValidationError):
        schema.finalize_records(df, SourceKind.GRN, "grn.csv")


def test_finalize_accepts_common_indian_date_format():
    df = _ledger_frame(
        {
            "date": ["05/01/2025"],
            "voucher": ["PO1"],
            "supplier": ["ABC"],
            "item": ["Wire"],
            "qty": ["1"],
            "unit": ["Nos"],
            "price": ["1"],
            "amount": ["1"],
        }
    )
    out = schema.finalize_records(df, SourceKind.GRN, "grn.csv")

    assert out["date"].dt.strftime("%Y-%m-%d").to_list() == ["2025-01-05"]


def test_finalize_rejects_supplier_before_first_header():
    # First row has no supplier and none precedes it -> nothing to forward-fill.
    df = _ledger_frame(
        {
            "date": ["2025-01-05"],
            "voucher": ["PO1"],
            "supplier": [None],
            "item": ["Wire"],
            "qty": ["1"],
            "unit": ["Nos"],
            "price": ["1"],
            "amount": ["1"],
        }
    )
    with pytest.raises(DataValidationError):
        schema.finalize_records(df, SourceKind.POV, "pov.xlsx")


def test_finalize_closing_stock_reduced_schema():
    df = pl.DataFrame(
        {
            "item": ["Wire", "Pipe"],
            "qty": ["10", "5"],
            "price": ["2", "3"],
            "amount": ["20", "15"],
        },
        schema={
            "item": pl.String,
            "qty": pl.String,
            "price": pl.String,
            "amount": pl.String,
        },
    )
    out = schema.finalize_records(df, SourceKind.CLOSING_STOCK, "stock.csv")
    assert out.columns == ["item", "qty", "price", "amount"]
    assert out.schema["amount"] == pl.Decimal(scale=schema.MONEY_SCALE)
    assert out["amount"].sum() == 35  # Decimal accumulation, not float


def test_finalize_closing_stock_drops_empty_item_separator_rows():
    df = pl.DataFrame(
        {
            "item": ["Wire", None],
            "qty": ["10", None],
            "price": ["2", None],
            "amount": ["20", None],
        },
        schema={
            "item": pl.String,
            "qty": pl.String,
            "price": pl.String,
            "amount": pl.String,
        },
    )
    out = schema.finalize_records(df, SourceKind.CLOSING_STOCK, "stock.csv")

    assert out.height == 1
    assert out["item"].to_list() == ["Wire"]


def test_first_offending_returns_empty_string_when_no_rows_match() -> None:
    df = pl.DataFrame(
        {
            "qty": [1, 2, 3],
        }
    )

    result = _first_offending(
        df,
        pl.col("qty") > 100,
        "qty",
    )

    assert result == ""


def test_validate_rejects_null_supplier_in_ledger() -> None:
    df = pl.DataFrame(
        {
            "supplier": [None],
            "item": ["Wire"],
            "__qty": [1.0],
            "__price": [1],
            "__amount": [1],
        }
    )

    with pytest.raises(DataValidationError) as exc_info:
        _validate(
            df=df,
            ledger=True,
            source_label="pov.xlsx",
        )

    assert "found a record with no supplier" in str(exc_info.value)
