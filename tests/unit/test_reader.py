"""End-to-end tests for read_source across .xlsx and .csv sources."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from opstools.inventory_forecast.domain.enums import SourceKind
from opstools.inventory_forecast.domain.errors import (
    SchemaError,
    SecurityError,
    ValidationError,
)
from opstools.inventory_forecast.ingestion import read_source

LEDGER_HEADER = [
    "Date",
    "Vch/Bill No",
    "Particulars",
    "Item Details",
    "Qty.",
    "Unit",
    "Price",
    "Amount",
]


def test_reads_ledger_xlsx_with_all_erp_quirks(make_excel):
    path = make_excel(
        "pov.xlsx",
        LEDGER_HEADER,
        [
            (
                date(2025, 1, 5),
                "PO001",
                "ABC Electricals (Noida)",
                "Copper Wire",
                10,
                "Nos",
                100.25,
                1002.50,
            ),
            (None, "PO002", None, "Copper Wire 4mm", 5, "Nos", 50.10, 250.50),
            (
                date(2025, 1, 20),
                "PO003",
                "XYZ Traders (Delhi)",
                "PVC Tape",
                3,
                "Box",
                20.0,
                60.0,
            ),
            ("Grand Total", None, None, None, None, None, None, 1313.0),  # footer
        ],
    )
    df = read_source(path, SourceKind.POV).collect()

    assert df.columns == [
        "date",
        "voucher",
        "supplier",
        "item",
        "qty",
        "unit",
        "price",
        "amount",
    ]
    assert df.schema["date"] == pl.Date
    assert df.schema["price"] == pl.Decimal(scale=4)
    assert df.height == 3  # banner + footer separator dropped
    # forward-fill across the second row, branch suffix stripped on both.
    assert df["supplier"].to_list() == [
        "ABC Electricals",
        "ABC Electricals",
        "XYZ Traders",
    ]
    assert df["date"][0] == date(2025, 1, 5)
    assert df["voucher"].to_list() == ["PO001", "PO002", "PO003"]


def test_reads_closing_stock_csv(make_csv):
    path = make_csv(
        "stock.csv",
        "KEPL Pvt Ltd\n"
        "Closing Stock,,,\n"
        "Item Details,Qty.,Price,Amount,Cat No.\n"
        "Copper Wire,100,2.50,250.00,C1\n"
        "PVC Tape,4,1.0,4.0,C3\n",
    )
    df = read_source(path, SourceKind.CLOSING_STOCK).collect()
    assert df.columns == ["item", "qty", "price", "amount"]
    assert df.height == 2
    assert df["amount"].sum() == 254  # 250 + 4, Decimal


def test_reads_ledger_csv_with_metadata_rows(make_csv):
    path = make_csv(
        "pv.csv",
        "KEPL Pvt Ltd\n"
        "Date,Vch/Bill No,Particulars,Item Details,Qty.,Unit,Price,Amount\n"
        "2025-02-10,V1,ABC (Noida),Wire,5,Nos,10,50\n",
    )
    df = read_source(path, SourceKind.PV).collect()
    assert df.height == 1
    assert df["supplier"][0] == "ABC"
    assert df["date"][0] == date(2025, 2, 10)


def test_determinism_same_input_same_output(make_csv):
    text = (
        "Date,Vch/Bill No,Particulars,Item Details,Qty.,Unit,Price,Amount\n"
        "2025-01-01,V1,ABC,Wire,1,Nos,1,1\n"
    )
    first = read_source(make_csv("a.csv", text), SourceKind.GRN).collect()
    second = read_source(make_csv("b.csv", text), SourceKind.GRN).collect()
    assert first.equals(second)


def test_unc_path_is_security_error():
    with pytest.raises(SecurityError):
        read_source(Path("//server/share/pov.xlsx"), SourceKind.POV)


def test_bad_extension_is_security_error(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("x")
    with pytest.raises(SecurityError):
        read_source(target, SourceKind.POV)


def test_missing_required_column_is_schema_error(make_csv):
    path = make_csv("bad.csv", "Date,Particulars,Item Details\n2025-01-01,ABC,Wire\n")
    with pytest.raises(SchemaError):
        read_source(path, SourceKind.PV).collect()


def test_no_header_is_schema_error(make_csv):
    path = make_csv("nohdr.csv", "foo,bar\n1,2\n")
    with pytest.raises(SchemaError):
        read_source(path, SourceKind.POV).collect()


def test_negative_value_is_validation_error(make_csv):
    path = make_csv(
        "neg.csv",
        "Date,Vch/Bill No,Particulars,Item Details,Qty.,Unit,Price,Amount\n"
        "2025-01-01,V1,ABC,Wire,-5,Nos,10,50\n",
    )
    with pytest.raises(ValidationError):
        read_source(path, SourceKind.POV).collect()


def test_missing_file_is_validation_error(tmp_path):
    with pytest.raises(ValidationError):
        read_source(tmp_path / "ghost.csv", SourceKind.POV)
