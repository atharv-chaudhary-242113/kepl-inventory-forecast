"""Tests for ``build_inventory_valuation`` (engine/valuation.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.engine import build_inventory_valuation

_SNAP = date(2025, 3, 31)


def test_values_stock_at_pv_unit_cost(ledger, closing) -> None:
    """Items priced by PV use the value-weighted PV unit cost."""
    stock = closing([("Wire", 10.0, 99.0)])  # closing price is fallback only
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 4.0, 40.0),
            (date(2025, 2, 1), "P2", "Acme", "Wire", 6.0, 66.0),
        ]
    )
    out = build_inventory_valuation(stock, pv, _SNAP).collect()

    row = out.row(0, named=True)
    # PV unit cost 106/10 = 10.6, not the closing 99.
    assert row["unit_cost"] == Decimal("10.6000")
    assert row["inventory_value"] == Decimal("106.0000")


def test_falls_back_to_closing_price_when_pv_absent(ledger, closing) -> None:
    """An item PV never priced is valued at its closing-stock price."""
    stock = closing([("Bolt", 5.0, 9.9)])
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0)])

    out = build_inventory_valuation(stock, pv, _SNAP).collect()

    row = out.row(0, named=True)
    assert row["unit_cost"] == Decimal("9.9000")
    assert row["inventory_value"] == Decimal("49.5000")


def test_snapshot_date_is_stamped_explicitly(ledger, closing) -> None:
    """The passed snapshot_date lands on every row as a Date, not from data."""
    stock = closing([("Wire", 1.0, 5.0), ("Bolt", 2.0, 3.0)])
    pv = ledger([])

    out = build_inventory_valuation(stock, pv, _SNAP).collect()

    assert out.schema["snapshot_date"] == pl.Date
    assert out["snapshot_date"].to_list() == [_SNAP, _SNAP]


def test_inventory_value_dtype_is_decimal(ledger, closing) -> None:
    """Valuation arithmetic stays Decimal-exact (no float currency)."""
    stock = closing([("Wire", 3.0, 2.5)])
    pv = ledger([])

    out = build_inventory_valuation(stock, pv, _SNAP).collect()

    assert out.schema["inventory_value"] == pl.Decimal(precision=38, scale=4)
    assert out.row(0, named=True)["inventory_value"] == Decimal("7.5000")


def test_zero_quantity_pv_group_does_not_price_item(ledger, closing) -> None:
    """A PV group with zero qty cannot define a unit cost; closing price wins."""
    stock = closing([("Wire", 4.0, 8.0)])
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 0.0, 0.0)])

    out = build_inventory_valuation(stock, pv, _SNAP).collect()

    assert out.row(0, named=True)["unit_cost"] == Decimal("8.0000")


def test_valuation_output_column_order_matches_contract(ledger, closing) -> None:
    """Schema must equal the Inventory_Valuation sheet column order."""
    stock = closing([("Wire", 1.0, 1.0)])
    pv = ledger([])

    out = build_inventory_valuation(stock, pv, _SNAP).collect()

    assert out.columns == [
        "item",
        "quantity",
        "unit_cost",
        "inventory_value",
        "snapshot_date",
    ]
