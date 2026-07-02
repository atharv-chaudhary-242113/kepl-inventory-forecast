"""Tests for ``build_inventory_health`` (engine/inventory_health.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.domain import InventoryStatus
from opstools.inventory_forecast.engine import (
    build_inventory_health,
    build_inventory_valuation,
    reconstruct_demand,
)

_SNAP = date(2025, 6, 30)

_OUTPUT_COLUMNS = [
    "item",
    "quantity",
    "avg_monthly_demand",
    "months_of_cover",
    "status",
    "excess_inventory_value",
]


def _demand_lf(rows: list[tuple[str, str, date, float]]) -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "period": [r[2] for r in rows],
            "supplier": [r[0] for r in rows],
            "item": [r[1] for r in rows],
            "demand_quantity": [r[3] for r in rows],
            "demand_value": [Decimal(str(r[3])) for r in rows],
        },
        schema={
            "period": pl.Date,
            "supplier": pl.Utf8,
            "item": pl.Utf8,
            "demand_quantity": pl.Float64,
            "demand_value": pl.Decimal(scale=4),
        },
    )


# pyrefly: ignore [implicit-any-parameter]
def test_dead_stock_when_stock_held_but_no_demand(ledger, closing) -> None:
    """Stock on hand with zero demand -> dead_stock."""
    stock = closing([("Wire", 50.0, 10.0)])
    pv = ledger([])
    demand = _demand_lf([])

    val = build_inventory_valuation(stock, pv, _SNAP)
    out = build_inventory_health(val, demand).collect()
    row = out.row(0, named=True)
    assert row["status"] == InventoryStatus.DEAD_STOCK.value
    assert row["months_of_cover"] is None


# pyrefly: ignore [implicit-any-parameter]
def test_low_stock_when_cover_below_threshold(ledger, closing) -> None:
    """Cover < 1 month -> low_stock."""
    stock = closing([("Wire", 5.0, 10.0)])  # 5 units on hand
    pv = ledger([])
    # 50/month demand -> 0.1 months of cover.
    demand = _demand_lf(
        [
            ("Acme", "Wire", date(2025, 1, 1), 50.0),
            ("Acme", "Wire", date(2025, 2, 1), 50.0),
        ]
    )
    val = build_inventory_valuation(stock, pv, _SNAP)
    out = build_inventory_health(val, demand).collect()
    row = out.row(0, named=True)
    assert row["status"] == InventoryStatus.LOW_STOCK.value
    assert row["months_of_cover"] == 0.1


# pyrefly: ignore [implicit-any-parameter]
def test_overstocked_when_cover_above_threshold(ledger, closing) -> None:
    """Cover > 12 months -> overstocked + non-zero excess value."""
    stock = closing([("Wire", 1300.0, 10.0)])
    pv = ledger([])
    demand = _demand_lf(
        [
            ("Acme", "Wire", date(2025, 1, 1), 100.0),
            ("Acme", "Wire", date(2025, 2, 1), 100.0),
        ]
    )
    val = build_inventory_valuation(stock, pv, _SNAP)
    out = build_inventory_health(val, demand).collect()
    row = out.row(0, named=True)
    assert row["status"] == InventoryStatus.OVERSTOCKED.value
    assert row["months_of_cover"] == 13.0
    # Excess = 1300 - 3*100 = 1000 units @ 10 each = 10_000.
    assert row["excess_inventory_value"] == Decimal("10000.0000")


# pyrefly: ignore [implicit-any-parameter]
def test_healthy_when_cover_in_normal_range(ledger, closing) -> None:
    """1 <= cover <= 12 months -> healthy."""
    stock = closing([("Wire", 300.0, 10.0)])  # 3 months
    pv = ledger([])
    demand = _demand_lf(
        [
            ("Acme", "Wire", date(2025, 1, 1), 100.0),
            ("Acme", "Wire", date(2025, 2, 1), 100.0),
        ]
    )
    val = build_inventory_valuation(stock, pv, _SNAP)
    out = build_inventory_health(val, demand).collect()
    row = out.row(0, named=True)
    assert row["status"] == InventoryStatus.HEALTHY.value


# pyrefly: ignore [implicit-any-parameter]
def test_excess_value_is_decimal_and_never_negative(ledger, closing) -> None:
    """Excess at/below target -> 0; arithmetic stays Decimal."""
    stock = closing([("Wire", 100.0, 10.0)])  # 1 month cover, below target
    pv = ledger([])
    demand = _demand_lf(
        [
            ("Acme", "Wire", date(2025, 1, 1), 100.0),
            ("Acme", "Wire", date(2025, 2, 1), 100.0),
        ]
    )
    val = build_inventory_valuation(stock, pv, _SNAP)
    out = build_inventory_health(val, demand).collect()
    assert out.schema["excess_inventory_value"] == pl.Decimal(precision=38, scale=4)
    assert out.row(0, named=True)["excess_inventory_value"] == Decimal("0.0000")


# pyrefly: ignore [implicit-any-parameter]
def test_avg_demand_pools_across_suppliers(ledger, closing) -> None:
    """Item-wide demand sums each month across suppliers before averaging."""
    stock = closing([("Wire", 100.0, 1.0)])
    pv = ledger([])
    # Two suppliers contribute 50 each per month -> 100/month total.
    demand = _demand_lf(
        [
            ("Acme", "Wire", date(2025, 1, 1), 50.0),
            ("Globex", "Wire", date(2025, 1, 1), 50.0),
            ("Acme", "Wire", date(2025, 2, 1), 50.0),
            ("Globex", "Wire", date(2025, 2, 1), 50.0),
        ]
    )
    val = build_inventory_valuation(stock, pv, _SNAP)
    out = build_inventory_health(val, demand).collect()
    row = out.row(0, named=True)
    assert row["avg_monthly_demand"] == 100.0
    assert row["months_of_cover"] == 1.0


# pyrefly: ignore [implicit-any-parameter]
def test_health_output_column_order_matches_contract(ledger, closing) -> None:
    val = build_inventory_valuation(closing([]), ledger([]), _SNAP)
    out = build_inventory_health(val, reconstruct_demand(ledger([]))).collect()
    assert out.columns == _OUTPUT_COLUMNS
