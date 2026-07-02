"""Tests for ``build_financial_summary`` (engine/financials.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.engine import build_financial_summary


# pyrefly: ignore [implicit-any-parameter]
def test_aggregates_spend_per_supplier_item(ledger) -> None:
    """PV lines for one (supplier, item) sum into a single total_cost."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 4.0, 40.0),
            (date(2025, 2, 1), "P2", "Acme", "Wire", 6.0, 66.0),
        ]
    )
    out = build_financial_summary(pv, Settings()).collect()

    assert out.height == 1
    row = out.row(0, named=True)
    assert row["quantity"] == 10.0
    assert row["total_cost"] == Decimal("106.0000")


# pyrefly: ignore [implicit-any-parameter]
def test_unit_cost_is_value_weighted_decimal(ledger) -> None:
    """unit_cost = total_cost / quantity, kept Decimal-exact."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 4.0, 40.0),
            (date(2025, 2, 1), "P2", "Acme", "Wire", 6.0, 66.0),
        ]
    )
    out = build_financial_summary(pv, Settings()).collect()

    assert out.schema["unit_cost"] == pl.Decimal(precision=38, scale=4)
    assert out.row(0, named=True)["unit_cost"] == Decimal("10.6000")


# pyrefly: ignore [implicit-any-parameter]
def test_freight_is_separate_decimal_component(ledger) -> None:
    """freight_cost = total_cost * freight_rate, never floating-point."""
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 100.0)])
    out = build_financial_summary(pv, Settings()).collect()

    row = out.row(0, named=True)
    assert out.schema["freight_cost"] == pl.Decimal(precision=38, scale=4)
    # Default freight_rate is 0.18 -> 100 * 0.18 = 18.0000 exactly.
    assert row["freight_cost"] == Decimal("18.0000")


# pyrefly: ignore [implicit-any-parameter]
def test_total_spend_is_cost_plus_freight(ledger) -> None:
    """Landed cost is the exact Decimal sum of base cost and freight."""
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 100.0)])
    out = build_financial_summary(pv, Settings()).collect()

    row = out.row(0, named=True)
    assert row["total_spend"] == Decimal("118.0000")
    assert out.schema["total_spend"] == pl.Decimal(precision=38, scale=4)


# pyrefly: ignore [implicit-any-parameter]
def test_configured_freight_rate_is_applied(ledger) -> None:
    """A custom freight_rate flows through to freight_cost."""
    cfg = Settings(freight_rate=Decimal("0.05"))
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 200.0)])
    out = build_financial_summary(pv, cfg).collect()

    assert out.row(0, named=True)["freight_cost"] == Decimal("10.0000")


# pyrefly: ignore [implicit-any-parameter]
def test_zero_quantity_group_is_dropped(ledger) -> None:
    """A group with no quantity cannot yield a unit cost and is excluded."""
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 0.0, 0.0)])
    out = build_financial_summary(pv, Settings()).collect()

    assert out.height == 0


# pyrefly: ignore [implicit-any-parameter]
def test_financial_output_column_order_matches_contract(ledger) -> None:
    """Schema must equal the Financial_Summary sheet column order."""
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0)])
    out = build_financial_summary(pv, Settings()).collect()

    assert out.columns == [
        "supplier",
        "item",
        "quantity",
        "unit_cost",
        "freight_cost",
        "total_cost",
        "total_spend",
    ]


# pyrefly: ignore [implicit-any-parameter]
def test_empty_pv_returns_empty_financial_contract(ledger) -> None:
    """No PV rows yields the Financial_Summary contract with zero rows."""
    out = build_financial_summary(ledger([]), Settings()).collect()

    assert out.height == 0
    assert out.columns == [
        "supplier",
        "item",
        "quantity",
        "unit_cost",
        "freight_cost",
        "total_cost",
        "total_spend",
    ]
    assert out.schema["total_spend"] == pl.Decimal(precision=38, scale=4)
