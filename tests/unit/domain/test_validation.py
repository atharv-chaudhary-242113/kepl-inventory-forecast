"""Tests for domain validation."""

import polars as pl
import pytest

from opstools.inventory_forecast.domain import (
    CLOSING_STOCK_NON_NULL_COLUMNS,
    CLOSING_STOCK_REQUIRED_COLUMNS,
    TRANSACTION_REQUIRED_COLUMNS,
    InventoryForecastError,
    validate_transaction_dataset,
)

# noinspection PyProtectedMember
from opstools.inventory_forecast.domain.validation import (
    _missing_columns,
    _null_columns,
    _raise_if_invalid,
    validate_closing_stock,
)


def test_missing_columns_returns_empty_list_when_schema_complete() -> None:
    frame = pl.LazyFrame(
        {
            "date": [],
            "supplier": [],
            "item": [],
            "qty": [],
            "price": [],
            "amount": [],
        }
    )

    violations = _missing_columns(
        frame=frame,
        dataset_name="POV",
        required_columns=TRANSACTION_REQUIRED_COLUMNS,
    )

    assert violations == []


def test_missing_columns_reports_single_missing_column() -> None:
    frame = pl.LazyFrame({"date": []})

    violations = _missing_columns(
        frame=frame,
        required_columns=("date", "amount"),
        dataset_name="POV",
    )

    assert violations == ["POV: missing required column 'amount'."]


def test_missing_columns_report_multiple_missing_columns() -> None:
    frame = pl.LazyFrame(
        {
            "date": [],
        }
    )

    violations = _missing_columns(
        frame=frame,
        dataset_name="POV",
        required_columns=CLOSING_STOCK_REQUIRED_COLUMNS,
    )

    assert violations == [
        "POV: missing required column 'item'.",
        "POV: missing required column 'qty'.",
    ]


def test_null_columns_returns_empty_when_no_nulls_exist() -> None:
    frame = pl.LazyFrame(
        {
            "date": ["2025-01-01", "2025-01-02"],
            "item": ["wire", "copper"],
            "qty": [12, 52],
        }
    )

    violations = _null_columns(
        frame=frame,
        dataset_name="POV",
        columns=CLOSING_STOCK_NON_NULL_COLUMNS,
    )

    assert violations == []


def test_null_columns_reports_single_missing_column() -> None:
    frame = pl.LazyFrame({"qty": [100.0, None]})

    violations = _null_columns(
        frame=frame,
        dataset_name="POV",
        columns=("qty",),
    )

    assert violations == ["POV: column 'qty' contains 1 null value(s)."]


def test_null_columns_reports_multiple_missing_columns() -> None:
    frame = pl.LazyFrame(
        {
            "date": [None, None],
            "item": [None, "Copper"],
        }
    )

    violations = _null_columns(
        frame=frame,
        dataset_name="POV",
        columns=(
            "date",
            "item",
        ),
    )

    assert violations == [
        "POV: column 'date' contains 2 null value(s).",
        "POV: column 'item' contains 1 null value(s).",
    ]


def test_null_columns_returns_empty_when_no_requested_columns_exist():
    frame = pl.LazyFrame(
        {
            "price": [None, None],
        }
    )

    violations = _null_columns(
        frame=frame,
        dataset_name="POV",
        columns=CLOSING_STOCK_NON_NULL_COLUMNS,
    )

    assert violations == []


def test_raise_if_invalid_returns_when_no_violations_exist() -> None:
    _raise_if_invalid([])


def test_raise_if_invalid_raises_single_combined_exception() -> None:
    with pytest.raises(InventoryForecastError) as exc_info:
        _raise_if_invalid(
            [
                "error one",
                "error two",
            ]
        )

        message = str(exc_info.value)

        assert "Dataset validation failed:" in message
        assert "error one" in message
        assert "error two" in message


def test_validate_transaction_dataset_accepts_valid_dataset() -> None:
    frame = pl.LazyFrame(
        {
            "date": [
                "2026-01-01",
                "2026-01-02",
            ],
            "supplier": [
                "AK electricians",
                "KEPL (J44)",
            ],
            "item": ["Copper wire", "Copper"],
            "qty": [2, 5],
            "price": [4, 3],
            "amount": [8, 15],
        }
    )

    validate_transaction_dataset(frame, "POV")


def test_validate_transaction_dataset_rejects_missing_required_column() -> None:
    frame = pl.LazyFrame(
        {
            "date": ["2025-01-01"],
            "supplier": ["ABC"],
            "item": ["ITEM-1"],
            "qty": [10],
            "price": [5.0],
        }
    )

    with pytest.raises(InventoryForecastError) as exc_info:
        validate_transaction_dataset(frame, "POV")

    assert "missing required column 'amount'" in str(exc_info.value)


def test_validate_transaction_dataset_rejects_null_values() -> None:
    frame = pl.LazyFrame(
        {
            "date": ["2025-01-01"],
            "supplier": [None],
            "item": ["ITEM-1"],
            "qty": [10],
            "price": [5.0],
            "amount": [50.0],
        }
    )

    with pytest.raises(InventoryForecastError) as exc_info:
        validate_transaction_dataset(frame, "POV")

    assert "contains 1 null value(s)" in str(exc_info.value)


def test_validate_closing_stock_accepts_valid_dataset() -> None:
    frame = pl.LazyFrame(
        {
            "date": ["2025-01-01"],
            "item": ["ITEM-1"],
            "qty": [100],
        }
    )

    validate_closing_stock(frame)


def test_validate_closing_stock_rejects_missing_required_column() -> None:
    frame = pl.LazyFrame(
        {
            "date": ["2025-01-01"],
            "item": ["ITEM-1"],
        }
    )

    with pytest.raises(InventoryForecastError) as exc_info:
        validate_closing_stock(frame)

    assert "missing required column 'qty'" in str(exc_info.value)


def test_validate_closing_stock_rejects_null_values() -> None:
    frame = pl.LazyFrame(
        {
            "date": ["2025-01-01"],
            "item": [None],
            "qty": [100],
        }
    )

    with pytest.raises(InventoryForecastError) as exc_info:
        validate_closing_stock(frame)

    assert "contains 1 null value(s)" in str(exc_info.value)
