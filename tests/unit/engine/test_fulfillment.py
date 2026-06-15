"""Tests for ``build_fill_rate`` (engine/fulfillment.py)."""

from datetime import date

from opstools.inventory_forecast.domain.enums import FulfillmentStatus
from opstools.inventory_forecast.engine import build_fill_rate, compute_lead_time

_OUTPUT_COLUMNS = [
    "supplier",
    "item",
    "ordered_qty",
    "delivered_qty",
    "fill_rate",
    "fulfillment_status",
]


def test_complete_when_fully_delivered(ledger) -> None:
    """delivered == ordered -> fill_rate 1.0, status complete."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger([(date(2025, 1, 11), "G1", "Acme", "Wire", 10.0, 100.0)])

    out = build_fill_rate(compute_lead_time(pov, grn)).collect()
    row = out.row(0, named=True)
    assert row["fill_rate"] == 1.0
    assert row["fulfillment_status"] == FulfillmentStatus.COMPLETE.value


def test_pending_when_nothing_delivered(ledger) -> None:
    """No receipts -> fill_rate 0.0, status pending."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    out = build_fill_rate(compute_lead_time(pov, ledger([]))).collect()
    row = out.row(0, named=True)
    assert row["fill_rate"] == 0.0
    assert row["fulfillment_status"] == FulfillmentStatus.PENDING.value


def test_partial_when_some_delivered(ledger) -> None:
    """0 < delivered < ordered -> status partial."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger([(date(2025, 1, 11), "G1", "Acme", "Wire", 4.0, 40.0)])

    out = build_fill_rate(compute_lead_time(pov, grn)).collect()
    row = out.row(0, named=True)
    assert row["fill_rate"] == 0.4
    assert row["fulfillment_status"] == FulfillmentStatus.PARTIAL.value


def test_ordered_qty_dedupes_across_receipts(ledger) -> None:
    """An order split across two receipts must not multi-count its ordered_qty."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger(
        [
            (date(2025, 1, 5), "G1", "Acme", "Wire", 4.0, 40.0),
            (date(2025, 1, 10), "G2", "Acme", "Wire", 6.0, 60.0),
        ]
    )
    out = build_fill_rate(compute_lead_time(pov, grn)).collect()
    row = out.row(0, named=True)
    assert row["ordered_qty"] == 10.0
    assert row["delivered_qty"] == 10.0
    assert row["fill_rate"] == 1.0


def test_groups_supplier_item_independently(ledger) -> None:
    """Each (supplier, item) gets its own fill rate."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0),
            (date(2025, 1, 1), "O2", "Globex", "Bolt", 10.0, 100.0),
        ]
    )
    grn = ledger([(date(2025, 1, 5), "G1", "Acme", "Wire", 10.0, 100.0)])
    out = build_fill_rate(compute_lead_time(pov, grn)).collect()

    by_supplier = {r["supplier"]: r for r in out.iter_rows(named=True)}
    assert by_supplier["Acme"]["fill_rate"] == 1.0
    assert by_supplier["Globex"]["fill_rate"] == 0.0


def test_fill_rate_output_column_order_matches_contract(ledger) -> None:
    out = build_fill_rate(compute_lead_time(ledger([]), ledger([]))).collect()
    assert out.columns == _OUTPUT_COLUMNS
