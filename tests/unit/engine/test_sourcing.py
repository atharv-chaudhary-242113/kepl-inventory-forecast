"""Tests for ``build_sourcing_risk`` (engine/sourcing.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.domain import RiskLevel, SupplierDependencyLevel
from opstools.inventory_forecast.engine import build_sourcing_risk

_OUTPUT_COLUMNS = [
    "item",
    "supplier_count",
    "total_spend",
    "top_supplier_share",
    "dependency_level",
    "risk_level",
]


# pyrefly: ignore [implicit-any-parameter]
def test_single_source_is_critical(ledger) -> None:
    """One supplier -> single_source dependency, critical risk."""
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 100.0)])
    out = build_sourcing_risk(pv).collect()

    row = out.row(0, named=True)
    assert row["supplier_count"] == 1
    assert row["top_supplier_share"] == 1.0
    assert row["dependency_level"] == SupplierDependencyLevel.SINGLE_SOURCE.value
    assert row["risk_level"] == RiskLevel.CRITICAL.value


# pyrefly: ignore [implicit-any-parameter]
def test_concentrated_when_top_supplier_above_80_pct(ledger) -> None:
    """Top share >= 0.80 -> concentrated / high risk."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 900.0),
            (date(2025, 1, 1), "P2", "Globex", "Wire", 1.0, 100.0),
        ]
    )
    out = build_sourcing_risk(pv).collect()
    row = out.row(0, named=True)
    assert row["dependency_level"] == SupplierDependencyLevel.CONCENTRATED.value
    assert row["risk_level"] == RiskLevel.HIGH.value


# pyrefly: ignore [implicit-any-parameter]
def test_moderate_when_top_share_between_50_and_80(ledger) -> None:
    """0.50 <= top share < 0.80 -> moderate / medium risk."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 600.0),
            (date(2025, 1, 1), "P2", "Globex", "Wire", 1.0, 400.0),
        ]
    )
    out = build_sourcing_risk(pv).collect()
    row = out.row(0, named=True)
    assert row["dependency_level"] == SupplierDependencyLevel.MODERATE.value
    assert row["risk_level"] == RiskLevel.MEDIUM.value


# pyrefly: ignore [implicit-any-parameter]
def test_diversified_when_top_share_below_50(ledger) -> None:
    """Top share < 0.50 -> diversified / low risk."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 400.0),
            (date(2025, 1, 1), "P2", "Globex", "Wire", 1.0, 350.0),
            (date(2025, 1, 1), "P3", "Beta", "Wire", 1.0, 250.0),
        ]
    )
    out = build_sourcing_risk(pv).collect()
    row = out.row(0, named=True)
    assert row["dependency_level"] == SupplierDependencyLevel.DIVERSIFIED.value
    assert row["risk_level"] == RiskLevel.LOW.value


# pyrefly: ignore [implicit-any-parameter]
def test_total_spend_decimal_and_share_is_float(ledger) -> None:
    """Spend stays Decimal-exact; share is a presentation Float64."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 900.0),
            (date(2025, 1, 1), "P2", "Globex", "Wire", 1.0, 100.0),
        ]
    )
    out = build_sourcing_risk(pv).collect()
    assert out.schema["total_spend"] == pl.Decimal(precision=38, scale=4)
    assert out.schema["top_supplier_share"] == pl.Float64
    assert out.row(0, named=True)["total_spend"] == Decimal("1000.0000")
    assert abs(out.row(0, named=True)["top_supplier_share"] - 0.9) < 1e-9


# pyrefly: ignore [implicit-any-parameter]
def test_sourcing_output_column_order_matches_contract(ledger) -> None:
    out = build_sourcing_risk(ledger([])).collect()
    assert out.columns == _OUTPUT_COLUMNS


# pyrefly: ignore [implicit-any-parameter]
def test_sourcing_sorted_by_item(ledger) -> None:
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Zeta", 1.0, 1.0),
            (date(2025, 1, 1), "P2", "Acme", "Alpha", 1.0, 1.0),
        ]
    )
    out = build_sourcing_risk(pv).collect()
    assert out["item"].to_list() == ["Alpha", "Zeta"]
