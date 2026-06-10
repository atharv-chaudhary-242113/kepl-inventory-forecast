"""Tests for ``reconstruct_demand`` (engine/demand.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.engine import reconstruct_demand


def test_pools_grn_and_pv_into_one_series(ledger, closing) -> None:
    """GRN and PV movement lines both contribute to the same demand series."""
    grn = ledger([(date(2025, 1, 5), "G1", "Acme", "Wire", 10.0, 100.0)])
    pv = ledger([(date(2025, 1, 20), "P1", "Acme", "Wire", 4.0, 48.0)])

    out = reconstruct_demand(grn, pv, closing([])).collect()

    # Same supplier+item+month -> one period row pooling both ledgers.
    assert out.height == 1
    row = out.row(0, named=True)
    assert row["period"] == date(2025, 1, 1)
    assert row["demand_quantity"] == 14.0
    assert row["demand_value"] == Decimal("148.0000")


def test_truncates_dates_to_month_start(ledger, closing) -> None:
    """Transactions in the same calendar month collapse to one month-start row."""
    grn = ledger(
        [
            (date(2025, 3, 2), "G1", "Acme", "Bolt", 5.0, 50.0),
            (date(2025, 3, 28), "G2", "Acme", "Bolt", 7.0, 70.0),
        ]
    )
    out = reconstruct_demand(grn, ledger([]), closing([])).collect()

    assert out.height == 1
    assert out.row(0, named=True)["period"] == date(2025, 3, 1)
    assert out.row(0, named=True)["demand_quantity"] == 12.0


def test_separate_months_stay_distinct(ledger, closing) -> None:
    """Different months for one item produce one row each, sorted ascending."""
    grn = ledger(
        [
            (date(2025, 2, 10), "G1", "Acme", "Wire", 3.0, 30.0),
            (date(2025, 1, 10), "G2", "Acme", "Wire", 8.0, 80.0),
        ]
    )
    out = reconstruct_demand(grn, ledger([]), closing([])).collect()

    assert out["period"].to_list() == [date(2025, 1, 1), date(2025, 2, 1)]
    assert out["demand_quantity"].to_list() == [8.0, 3.0]


def test_null_dated_rows_are_dropped(ledger, closing) -> None:
    """A movement with no date cannot sit on the time axis and is excluded."""
    grn = ledger(
        [
            (None, "G1", "Acme", "Wire", 99.0, 990.0),
            (date(2025, 1, 4), "G2", "Acme", "Wire", 2.0, 20.0),
        ]
    )
    out = reconstruct_demand(grn, ledger([]), closing([])).collect()

    assert out.height == 1
    assert out.row(0, named=True)["demand_quantity"] == 2.0


def test_demand_value_dtype_is_decimal(ledger, closing) -> None:
    """Value accumulation must stay Decimal-exact (THREAT_MODEL.md)."""
    grn = ledger([(date(2025, 1, 1), "G1", "Acme", "Wire", 1.0, 10.0)])
    out = reconstruct_demand(grn, ledger([]), closing([])).collect()

    assert out.schema["demand_value"] == pl.Decimal(precision=38, scale=4)


def test_output_column_order_matches_contract(ledger, closing) -> None:
    """Schema must equal the Demand_History sheet column order."""
    grn = ledger([(date(2025, 1, 1), "G1", "Acme", "Wire", 1.0, 10.0)])
    out = reconstruct_demand(grn, ledger([]), closing([])).collect()

    assert out.columns == [
        "period",
        "supplier",
        "item",
        "demand_quantity",
        "demand_value",
    ]
