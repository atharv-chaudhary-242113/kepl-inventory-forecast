"""Unit tests for the canonicalization expression builders."""

import polars as pl

from opstools.inventory_forecast.ingestion import (
    blank_to_null_expr,
    forward_fill_supplier_expr,
    normalize_supplier_expr,
)


def test_blank_to_null_trims_and_nulls_empties():
    df = pl.DataFrame({"item": [" Wire ", "", "   ", "Pipe"]})
    out = df.with_columns(blank_to_null_expr("item"))["item"].to_list()
    assert out == ["Wire", None, None, "Pipe"]


def test_forward_fill_inherits_previous_supplier():
    # forward_fill fills nulls only, so blanks must already be null.
    df = pl.DataFrame({"supplier": ["ABC", None, None, "XYZ", None]})
    out = df.with_columns(forward_fill_supplier_expr())["supplier"].to_list()
    assert out == ["ABC", "ABC", "ABC", "XYZ", "XYZ"]


def test_forward_fill_accepts_custom_column_name():
    df = pl.DataFrame({"vendor": ["ABC", None, "XYZ"]})
    out = df.with_columns(forward_fill_supplier_expr("vendor"))["vendor"].to_list()
    assert out == ["ABC", "ABC", "XYZ"]


def test_normalize_supplier_strips_branch_suffix():
    df = pl.DataFrame(
        {"supplier": ["ABC Electricals (Noida)", "ABC Electricals (Delhi)", "XYZ"]}
    )
    out = df.with_columns(normalize_supplier_expr())["supplier"].to_list()
    assert out == ["ABC Electricals", "ABC Electricals", "XYZ"]


def test_normalize_supplier_accepts_custom_column_name():
    df = pl.DataFrame({"vendor": [" ABC (Noida) ", "XYZ"]})
    out = df.with_columns(normalize_supplier_expr("vendor"))["vendor"].to_list()
    assert out == ["ABC", "XYZ"]


def test_normalize_supplier_collapses_branches_to_one_identity():
    # The whole point of normalization: different branches become one supplier.
    df = pl.DataFrame({"supplier": ["ABC (Noida)", "ABC (Delhi)", "ABC (Ghaziabad)"]})
    out = df.with_columns(normalize_supplier_expr())["supplier"].unique().to_list()
    assert out == ["ABC"]
