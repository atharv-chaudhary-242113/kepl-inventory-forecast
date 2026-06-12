"""Tests for ``build_supplier_analysis`` (engine/supplier_risk.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.config.settings import Settings
from opstools.inventory_forecast.engine import (
    build_financial_summary,
    build_pending_deliveries,
    build_supplier_analysis,
    compute_lead_time,
)

_OUTPUT_COLUMNS = [
    "supplier",
    "total_spend",
    "total_orders",
    "total_deliveries",
    "average_lead_time",
    "lead_time_stddev",
    "pending_deliveries",
    "reliability_score",
    "risk_score",
]


def _row_by_supplier(df: pl.DataFrame, supplier: str) -> dict:
    return next(r for r in df.iter_rows(named=True) if r["supplier"] == supplier)


def test_perfect_supplier_has_max_reliability_zero_risk(ledger) -> None:
    """All orders delivered on a consistent lead time -> reliability 1.0, low risk."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 1, 5), "O2", "Acme", "Wire", 5.0, 50.0),
        ]
    )
    grn = ledger(
        [
            (date(2025, 1, 6), "G1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 1, 10), "G2", "Acme", "Wire", 5.0, 50.0),
        ]
    )
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 10.0, 100.0)])
    cfg = Settings()

    lt = compute_lead_time(pov, grn)
    pending = build_pending_deliveries(lt)
    fin = build_financial_summary(pv, cfg)
    out = build_supplier_analysis(lt, pending, fin, cfg).collect()

    row = _row_by_supplier(out, "Acme")
    assert row["reliability_score"] == 1.0
    # Constant lead time -> zero CV; no shortfall, no pending -> risk == 0.
    assert row["risk_score"] == 0.0


def test_completely_failed_supplier_has_high_risk(ledger) -> None:
    """No deliveries at all -> reliability 0, shortfall + pending drive risk up."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger([])
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 10.0, 100.0)])
    cfg = Settings()

    lt = compute_lead_time(pov, grn)
    pending = build_pending_deliveries(lt)
    fin = build_financial_summary(pv, cfg)
    out = build_supplier_analysis(lt, pending, fin, cfg).collect()

    row = _row_by_supplier(out, "Acme")
    assert row["reliability_score"] == 0.0
    # Shortfall (0.5) + pending ratio (0.3) contributions: risk >= 0.8.
    assert row["risk_score"] >= 0.8
    assert row["risk_score"] <= 1.0


def test_total_orders_dedupes_across_allocation_rows(ledger) -> None:
    """An order split across two receipts must still count as one order."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger(
        [
            (date(2025, 1, 5), "G1", "Acme", "Wire", 4.0, 40.0),
            (date(2025, 1, 10), "G2", "Acme", "Wire", 6.0, 60.0),
        ]
    )
    pv = ledger([])
    cfg = Settings()

    lt = compute_lead_time(pov, grn)
    out = build_supplier_analysis(lt, build_pending_deliveries(lt), pv, cfg).collect()

    row = _row_by_supplier(out, "Acme")
    assert row["total_orders"] == 1
    assert row["total_deliveries"] == 2  # two receipts


def test_total_spend_is_decimal(ledger) -> None:
    """Supplier spend stays Decimal-exact."""
    pov = ledger([])
    pv = ledger([(date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 123.45)])
    cfg = Settings()

    lt = compute_lead_time(pov, ledger([]))
    out = build_supplier_analysis(
        lt, build_pending_deliveries(lt), build_financial_summary(pv, cfg), cfg
    ).collect()

    assert out.schema["total_spend"] == pl.Decimal(precision=38, scale=4)
    # Spend includes 18% freight by default.
    row = _row_by_supplier(out, "Acme")
    assert row["total_spend"] == Decimal("145.6710")


def test_lead_time_stddev_is_null_for_single_delivery(ledger) -> None:
    """A single delivery has undefined sample std (ddof=1)."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0)])
    grn = ledger([(date(2025, 1, 6), "G1", "Acme", "Wire", 5.0, 50.0)])
    cfg = Settings()

    lt = compute_lead_time(pov, grn)
    out = build_supplier_analysis(
        lt, build_pending_deliveries(lt), ledger([]), cfg
    ).collect()

    assert out.row(0, named=True)["lead_time_stddev"] is None
    assert out.row(0, named=True)["average_lead_time"] == 5.0


def test_supplier_universe_unions_across_sources(ledger) -> None:
    """A supplier present only in PV still appears (with zero ops counts)."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 1.0, 1.0)])
    grn = ledger([(date(2025, 1, 2), "G1", "Acme", "Wire", 1.0, 1.0)])
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 1.0),
            (date(2025, 1, 1), "P2", "Globex", "Bolt", 1.0, 50.0),
        ]
    )
    cfg = Settings()

    lt = compute_lead_time(pov, grn)
    out = build_supplier_analysis(
        lt, build_pending_deliveries(lt), build_financial_summary(pv, cfg), cfg
    ).collect()

    suppliers = set(out["supplier"].to_list())
    assert suppliers == {"Acme", "Globex"}
    globex = _row_by_supplier(out, "Globex")
    assert globex["total_orders"] == 0
    assert globex["total_deliveries"] == 0
    assert globex["pending_deliveries"] == 0


def test_risk_score_bounded_in_unit_interval(ledger) -> None:
    """risk_score is always in [0, 1] regardless of input shape."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 2, 1), "O2", "Acme", "Wire", 5.0, 50.0),
        ]
    )
    grn = ledger([(date(2025, 1, 5), "G1", "Acme", "Wire", 2.0, 20.0)])
    cfg = Settings()

    lt = compute_lead_time(pov, grn)
    out = build_supplier_analysis(
        lt, build_pending_deliveries(lt), ledger([]), cfg
    ).collect()

    row = _row_by_supplier(out, "Acme")
    assert 0.0 <= row["risk_score"] <= 1.0
    assert 0.0 <= row["reliability_score"] <= 1.0


def test_supplier_output_column_order_matches_contract(ledger) -> None:
    """Schema must equal the Supplier_Analysis sheet column order."""
    lt = compute_lead_time(ledger([]), ledger([]))
    out = build_supplier_analysis(
        lt, build_pending_deliveries(lt), ledger([]), Settings()
    ).collect()

    assert out.columns == _OUTPUT_COLUMNS


def test_supplier_rows_sorted_by_supplier(ledger) -> None:
    """Output is deterministic by supplier name."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Zeta", "Wire", 1.0, 1.0),
            (date(2025, 1, 1), "P2", "Alpha", "Wire", 1.0, 1.0),
        ]
    )
    cfg = Settings()
    lt = compute_lead_time(ledger([]), ledger([]))
    out = build_supplier_analysis(
        lt, build_pending_deliveries(lt), build_financial_summary(pv, cfg), cfg
    ).collect()

    assert out["supplier"].to_list() == ["Alpha", "Zeta"]
