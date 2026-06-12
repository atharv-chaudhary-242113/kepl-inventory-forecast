"""Tests for ``compute_lead_time`` (engine/lead_time.py) — FIFO matching."""

from datetime import date

from opstools.inventory_forecast.engine import compute_lead_time


def test_one_to_one_match_yields_simple_lead_time(ledger) -> None:
    """A single order met by a single receipt gives one allocation row."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger([(date(2025, 1, 11), "G1", "Acme", "Wire", 10.0, 100.0)])

    out = compute_lead_time(pov, grn).collect()

    assert out.height == 1
    row = out.row(0, named=True)
    assert row["ordered_qty"] == 10.0
    assert row["delivered_qty"] == 10.0
    assert row["lead_time_days"] == 10


def test_one_order_split_across_two_receipts(ledger) -> None:
    """A partially-delivered order produces one row per receipt (FIFO)."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger(
        [
            (date(2025, 1, 10), "G1", "Acme", "Wire", 4.0, 40.0),
            (date(2025, 1, 20), "G2", "Acme", "Wire", 6.0, 60.0),
        ]
    )
    out = compute_lead_time(pov, grn).sort("grn_date").collect()

    assert out.height == 2
    assert out["delivered_qty"].to_list() == [4.0, 6.0]
    assert out["lead_time_days"].to_list() == [9, 19]


def test_one_receipt_covers_two_orders_fifo(ledger) -> None:
    """A single receipt fills the oldest order first, then the next."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 3.0, 30.0),
            (date(2025, 1, 5), "O2", "Acme", "Wire", 4.0, 40.0),
        ]
    )
    grn = ledger([(date(2025, 1, 15), "G1", "Acme", "Wire", 7.0, 70.0)])

    out = compute_lead_time(pov, grn).sort("pov_date").collect()

    # Oldest order (O1) consumes the first 3 units, O2 the next 4.
    assert out.height == 2
    assert out["ordered_qty"].to_list() == [3.0, 4.0]
    assert out["delivered_qty"].to_list() == [3.0, 4.0]
    assert out["lead_time_days"].to_list() == [14, 10]


def test_unmatched_order_survives_with_null_receipt(ledger) -> None:
    """An order with no receipt stays in the frame, fully undelivered."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0)])
    grn = ledger([])

    out = compute_lead_time(pov, grn).collect()

    assert out.height == 1
    row = out.row(0, named=True)
    assert row["delivered_qty"] == 0.0
    assert row["grn_date"] is None
    assert row["lead_time_days"] is None


def test_partial_fill_leaves_remainder_undelivered(ledger) -> None:
    """When a receipt under-fills an order, only the received units are matched."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0)])
    grn = ledger([(date(2025, 1, 8), "G1", "Acme", "Wire", 4.0, 40.0)])

    out = compute_lead_time(pov, grn).collect()

    assert out.height == 1
    assert out.row(0, named=True)["delivered_qty"] == 4.0
    assert out.row(0, named=True)["ordered_qty"] == 10.0


def test_matching_is_isolated_per_supplier_item(ledger) -> None:
    """Orders and receipts never cross (supplier, item) boundaries."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 1, 1), "O2", "Globex", "Wire", 5.0, 50.0),
        ]
    )
    grn = ledger([(date(2025, 1, 10), "G1", "Acme", "Wire", 5.0, 50.0)])

    out = compute_lead_time(pov, grn).collect()
    by_supplier = {r["supplier"]: r for r in out.iter_rows(named=True)}

    assert by_supplier["Acme"]["delivered_qty"] == 5.0
    assert by_supplier["Globex"]["delivered_qty"] == 0.0


def test_voucher_number_is_carried_through(ledger) -> None:
    """The order's voucher survives for Pending_Deliveries linkage."""
    pov = ledger([(date(2025, 1, 1), "PO-42", "Acme", "Wire", 5.0, 50.0)])
    grn = ledger([(date(2025, 1, 6), "G1", "Acme", "Wire", 5.0, 50.0)])

    out = compute_lead_time(pov, grn).collect()

    assert out.row(0, named=True)["voucher_number"] == "PO-42"


def test_null_dated_order_excluded_from_matching(ledger) -> None:
    """An order with no date cannot be placed on the FIFO axis."""
    pov = ledger(
        [
            (None, "O1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 1, 1), "O2", "Acme", "Wire", 3.0, 30.0),
        ]
    )
    grn = ledger([(date(2025, 1, 9), "G1", "Acme", "Wire", 3.0, 30.0)])

    out = compute_lead_time(pov, grn).collect()

    assert out.height == 1
    assert out.row(0, named=True)["voucher_number"] == "O2"


def test_null_dated_receipt_excluded_from_matching(ledger) -> None:
    """A receipt with no date cannot fulfill an order on the FIFO axis."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0)])
    grn = ledger(
        [
            (None, "G1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 1, 9), "G2", "Acme", "Wire", 5.0, 50.0),
        ]
    )

    out = compute_lead_time(pov, grn).collect()

    assert out.height == 1
    assert out.row(0, named=True)["grn_date"] == date(2025, 1, 9)


def test_lead_time_output_column_order_matches_contract(ledger) -> None:
    """The FIFO allocation frame keeps its documented column order."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0)])
    grn = ledger([])

    out = compute_lead_time(pov, grn).collect()

    assert out.columns == [
        "order_id",
        "supplier",
        "item",
        "voucher_number",
        "pov_date",
        "grn_date",
        "ordered_qty",
        "delivered_qty",
        "lead_time_days",
    ]
