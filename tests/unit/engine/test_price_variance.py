"""Tests for ``build_price_variance`` (engine/price_variance.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.engine import build_price_variance

_OUTPUT_COLUMNS = [
    "supplier",
    "item",
    "line_count",
    "min_price",
    "max_price",
    "mean_price",
    "price_range",
    "price_stddev",
]


def test_aggregates_min_max_mean_range_per_item(ledger) -> None:
    """Min/max/mean and range come straight from the PV lines."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0),  # price = 10
            (date(2025, 2, 1), "P2", "Acme", "Wire", 1.0, 20.0),  # price = 20
            (date(2025, 3, 1), "P3", "Acme", "Wire", 1.0, 30.0),  # price = 30
        ]
    )
    out = build_price_variance(pv).collect()

    row = out.row(0, named=True)
    assert row["line_count"] == 3
    assert row["min_price"] == Decimal("10.0000")
    assert row["max_price"] == Decimal("30.0000")
    assert row["mean_price"] == Decimal("20.0000")
    assert row["price_range"] == Decimal("20.0000")


def test_price_columns_stay_decimal(ledger) -> None:
    """Money summaries are exact Decimal (no float currency)."""
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0)])
    out = build_price_variance(pv).collect()

    for col in ("min_price", "max_price", "mean_price", "price_range"):
        assert out.schema[col] == pl.Decimal(precision=38, scale=4)


def test_single_line_has_zero_stddev(ledger) -> None:
    """Sample std (ddof=1) is undefined for n=1; reported as 0.0."""
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0)])
    out = build_price_variance(pv).collect()

    assert out.row(0, named=True)["price_stddev"] == 0.0
    assert out.row(0, named=True)["price_range"] == Decimal("0.0000")


def test_stddev_is_positive_when_prices_differ(ledger) -> None:
    """A genuine price spread shows up as non-zero stddev."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 2, 1), "P2", "Acme", "Wire", 1.0, 30.0),
        ]
    )
    out = build_price_variance(pv).collect()
    assert out.row(0, named=True)["price_stddev"] > 0.0


def test_groups_supplier_and_item_independently(ledger) -> None:
    """The same item under two suppliers stays two rows."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 1, 1), "P2", "Globex", "Wire", 1.0, 20.0),
        ]
    )
    out = build_price_variance(pv).collect()
    assert out.height == 2
    assert set(out["supplier"].to_list()) == {"Acme", "Globex"}


def test_price_variance_output_column_order_matches_contract(ledger) -> None:
    out = build_price_variance(ledger([])).collect()
    assert out.columns == _OUTPUT_COLUMNS


def test_price_variance_sorted_by_supplier_item(ledger) -> None:
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Zeta", "Wire", 1.0, 10.0),
            (date(2025, 1, 1), "P2", "Alpha", "Bolt", 1.0, 10.0),
        ]
    )
    out = build_price_variance(pv).collect()
    assert out.select(["supplier", "item"]).rows() == [
        ("Alpha", "Bolt"),
        ("Zeta", "Wire"),
    ]
