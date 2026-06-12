"""Tests for ``reconstruct_demand`` (engine/demand.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.engine import reconstruct_demand


def test_same_month_pov_rows_are_aggregated(ledger) -> None:
    """Same supplier+item+month collapses into one demand-history row."""
    pov = ledger(
        [
            (date(2025, 1, 5), "P1", "Acme", "Wire", 10.0, 100.0),
            (date(2025, 1, 20), "P2", "Acme", "Wire", 4.0, 48.0),
        ]
    )

    out = reconstruct_demand(pov).collect()

    assert out.height == 1

    row = out.row(0, named=True)

    assert row["period"] == date(2025, 1, 1)
    assert row["supplier"] == "Acme"
    assert row["item"] == "Wire"
    assert row["demand_quantity"] == 14.0
    assert row["demand_value"] == Decimal("148.0000")


def test_truncates_dates_to_month_start(ledger) -> None:
    """Transactions in the same month truncate to one month-start period."""
    pov = ledger(
        [
            (date(2025, 3, 2), "P1", "Acme", "Bolt", 5.0, 50.0),
            (date(2025, 3, 28), "P2", "Acme", "Bolt", 7.0, 70.0),
        ]
    )

    out = reconstruct_demand(pov).collect()

    assert out.height == 1

    row = out.row(0, named=True)

    assert row["period"] == date(2025, 3, 1)
    assert row["demand_quantity"] == 12.0
    assert row["demand_value"] == Decimal("120.0000")


def test_separate_months_stay_distinct(ledger) -> None:
    """Different months must remain separate demand periods."""
    pov = ledger(
        [
            (date(2025, 2, 10), "P1", "Acme", "Wire", 3.0, 30.0),
            (date(2025, 1, 10), "P2", "Acme", "Wire", 8.0, 80.0),
        ]
    )

    out = reconstruct_demand(pov).collect()

    assert out["period"].to_list() == [
        date(2025, 1, 1),
        date(2025, 2, 1),
    ]

    assert out["demand_quantity"].to_list() == [
        8.0,
        3.0,
    ]


def test_different_suppliers_remain_distinct(ledger) -> None:
    """Supplier is part of the grouping key and must not be merged."""
    pov = ledger(
        [
            (date(2025, 1, 10), "P1", "Acme", "Wire", 8.0, 80.0),
            (date(2025, 1, 12), "P2", "Omega", "Wire", 3.0, 30.0),
        ]
    )

    out = reconstruct_demand(pov).collect()

    assert out.height == 2

    assert set(out["supplier"].to_list()) == {
        "Acme",
        "Omega",
    }


def test_different_items_remain_distinct(ledger) -> None:
    """Item is part of the grouping key and must not be merged."""
    pov = ledger(
        [
            (date(2025, 1, 10), "P1", "Acme", "Wire", 8.0, 80.0),
            (date(2025, 1, 12), "P2", "Acme", "Bolt", 3.0, 30.0),
        ]
    )

    out = reconstruct_demand(pov).collect()

    assert out.height == 2

    assert set(out["item"].to_list()) == {
        "Wire",
        "Bolt",
    }


def test_null_dated_rows_are_dropped(ledger) -> None:
    """Rows without dates cannot participate in a forecasting time series."""
    pov = ledger(
        [
            (None, "P1", "Acme", "Wire", 99.0, 990.0),
            (date(2025, 1, 4), "P2", "Acme", "Wire", 2.0, 20.0),
        ]
    )

    out = reconstruct_demand(pov).collect()

    assert out.height == 1

    row = out.row(0, named=True)

    assert row["demand_quantity"] == 2.0
    assert row["demand_value"] == Decimal("20.0000")


def test_demand_value_dtype_is_decimal(ledger) -> None:
    """Demand value accumulation must remain Decimal-exact."""
    pov = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0),
        ]
    )

    out = reconstruct_demand(pov).collect()

    assert out.schema["demand_value"] == pl.Decimal(
        precision=38,
        scale=4,
    )


def test_output_column_order_matches_contract(ledger) -> None:
    """Output schema must match the Demand_History workbook contract."""
    pov = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0),
        ]
    )

    out = reconstruct_demand(pov).collect()

    assert out.columns == [
        "period",
        "supplier",
        "item",
        "demand_quantity",
        "demand_value",
    ]
