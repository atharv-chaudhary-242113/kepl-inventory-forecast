"""Tests for ``build_pending_deliveries`` (engine/pending.py)."""

from datetime import date

from opstools.inventory_forecast.engine import (
    build_pending_deliveries,
    compute_lead_time,
)


def test_fully_delivered_order_is_not_pending(ledger) -> None:
    """An order received in full produces no pending row."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger([(date(2025, 1, 10), "G1", "Acme", "Wire", 10.0, 100.0)])

    matched = compute_lead_time(pov, grn)
    out = build_pending_deliveries(matched).collect()

    assert out.height == 0


def test_partially_delivered_order_reports_shortfall(ledger) -> None:
    """A short order surfaces with pending_qty = ordered - delivered."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger([(date(2025, 1, 10), "G1", "Acme", "Wire", 4.0, 40.0)])

    matched = compute_lead_time(pov, grn)
    out = build_pending_deliveries(matched).collect()

    assert out.height == 1
    row = out.row(0, named=True)
    assert row["ordered_qty"] == 10.0
    assert row["delivered_qty"] == 4.0
    assert row["pending_qty"] == 6.0


def test_undelivered_order_is_fully_pending(ledger) -> None:
    """An order with no receipt is pending for its entire quantity."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 7.0, 70.0)])
    grn = ledger([])

    matched = compute_lead_time(pov, grn)
    out = build_pending_deliveries(matched).collect()

    assert out.height == 1
    assert out.row(0, named=True)["pending_qty"] == 7.0
    assert out.row(0, named=True)["delivered_qty"] == 0.0


def test_delivered_qty_sums_across_receipts(ledger) -> None:
    """Multiple receipts against one order roll up to a single pending row."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 20.0, 200.0)])
    grn = ledger(
        [
            (date(2025, 1, 5), "G1", "Acme", "Wire", 4.0, 40.0),
            (date(2025, 1, 9), "G2", "Acme", "Wire", 6.0, 60.0),
        ]
    )
    matched = compute_lead_time(pov, grn)
    out = build_pending_deliveries(matched).collect()

    assert out.height == 1
    row = out.row(0, named=True)
    assert row["delivered_qty"] == 10.0
    assert row["pending_qty"] == 10.0


def test_age_days_measured_from_latest_order_not_wallclock(ledger) -> None:
    """Age is relative to the newest order date, keeping the result deterministic."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 1, 31), "O2", "Acme", "Bolt", 5.0, 50.0),
        ]
    )
    grn = ledger([])

    matched = compute_lead_time(pov, grn)
    out = build_pending_deliveries(matched).sort("item").collect()
    by_item = {r["item"]: r for r in out.iter_rows(named=True)}

    # Latest order is Jan 31; the Jan 1 order is 30 days old, the Jan 31 order 0.
    assert by_item["Wire"]["age_days"] == 30
    assert by_item["Bolt"]["age_days"] == 0


def test_pending_output_column_order_matches_contract(ledger) -> None:
    """Schema must equal the Pending_Deliveries sheet column order."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0)])
    matched = compute_lead_time(pov, ledger([]))
    out = build_pending_deliveries(matched).collect()

    assert out.columns == [
        "supplier",
        "item",
        "voucher_number",
        "ordered_qty",
        "delivered_qty",
        "pending_qty",
        "order_date",
        "age_days",
    ]


def test_pending_rows_are_sorted_by_contract_keys(ledger) -> None:
    """Pending output is deterministic across supplier, item, date, voucher."""
    pov = ledger(
        [
            (date(2025, 1, 2), "O2", "Beta", "Nut", 1.0, 10.0),
            (date(2025, 1, 1), "O1", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 1, 1), "O3", "Acme", "Bolt", 1.0, 10.0),
        ]
    )

    out = build_pending_deliveries(compute_lead_time(pov, ledger([]))).collect()

    assert out.select(["supplier", "item", "voucher_number"]).rows() == [
        ("Acme", "Bolt", "O3"),
        ("Acme", "Wire", "O1"),
        ("Beta", "Nut", "O2"),
    ]
