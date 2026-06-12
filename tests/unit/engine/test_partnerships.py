"""Tests for ``detect_partnerships`` (engine/partnerships.py)."""

from datetime import date

from opstools.inventory_forecast.config.settings import Settings
from opstools.inventory_forecast.engine import detect_partnerships

_OUTPUT_COLUMNS = [
    "supplier_a",
    "supplier_b",
    "matching_events",
    "confidence_score",
    "status",
]


def _co_supply_rows(
    a: str, b: str, item: str, months: list[int]
) -> list[tuple[date | None, str, str, str, float, float]]:
    """Build POV rows where two suppliers co-supply `item` in the given months."""
    rows = []
    for m in months:
        rows.append((date(2025, m, 1), f"V{a}{m}", a, item, 1.0, 10.0))
        rows.append((date(2025, m, 1), f"V{b}{m}", b, item, 1.0, 10.0))
    return rows


def test_pair_meeting_threshold_is_flagged(ledger) -> None:
    """3 co-supply months -> one pair, status 'suspected'."""
    pov = ledger(_co_supply_rows("Acme", "Globex", "Wire", [1, 2, 3]))
    out = detect_partnerships(pov, Settings()).collect()

    assert out.height == 1
    row = out.row(0, named=True)
    assert (row["supplier_a"], row["supplier_b"]) == ("Acme", "Globex")
    assert row["matching_events"] == 3
    assert row["status"] == "suspected"


def test_below_threshold_pair_is_not_flagged(ledger) -> None:
    """2 co-supply months falls under the >=3 threshold."""
    pov = ledger(_co_supply_rows("Acme", "Globex", "Wire", [1, 2]))
    out = detect_partnerships(pov, Settings()).collect()

    assert out.height == 0


def test_no_mirror_duplicates(ledger) -> None:
    """(A, B) and (B, A) collapse to a single canonical row."""
    pov = ledger(_co_supply_rows("Beta", "Alpha", "Wire", [1, 2, 3]))
    out = detect_partnerships(pov, Settings()).collect()

    assert out.height == 1
    row = out.row(0, named=True)
    # Canonical ordering: alphabetically smaller name in supplier_a.
    assert row["supplier_a"] == "Alpha"
    assert row["supplier_b"] == "Beta"


def test_self_pair_excluded(ledger) -> None:
    """A supplier transacting an item multiple months does not pair with itself."""
    pov = ledger(
        [
            (date(2025, 1, 1), "V1", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 2, 1), "V2", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 3, 1), "V3", "Acme", "Wire", 1.0, 10.0),
        ]
    )
    out = detect_partnerships(pov, Settings()).collect()
    assert out.height == 0


def test_within_month_duplicates_do_not_inflate_count(ledger) -> None:
    """Two POV rows in the same month for one (supplier, item) count once."""
    pov = ledger(
        [
            # Acme + Globex co-supply Wire in only ONE month, twice each.
            (date(2025, 1, 1), "V1", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 1, 15), "V2", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 1, 5), "V3", "Globex", "Wire", 1.0, 10.0),
            (date(2025, 1, 20), "V4", "Globex", "Wire", 1.0, 10.0),
        ]
    )
    out = detect_partnerships(pov, Settings()).collect()
    # Only one (item, month) co-occurrence -> below threshold.
    assert out.height == 0


def test_null_dated_rows_excluded(ledger) -> None:
    """Rows with no date cannot be placed on the monthly axis."""
    rows = _co_supply_rows("Acme", "Globex", "Wire", [1, 2])
    rows.append((None, "Vx", "Acme", "Wire", 1.0, 10.0))
    rows.append((None, "Vy", "Globex", "Wire", 1.0, 10.0))
    pov = ledger(rows)
    out = detect_partnerships(pov, Settings()).collect()

    assert out.height == 0  # the two null-dated co-supplies don't count


def test_confidence_score_is_derived_not_hardcoded(ledger) -> None:
    """Confidence grows monotonically with the event count, bounded in (0, 1)."""
    low = ledger(_co_supply_rows("Acme", "Globex", "Wire", [1, 2, 3]))
    high = ledger(_co_supply_rows("Acme", "Globex", "Wire", list(range(1, 13))))

    c_low = detect_partnerships(low, Settings()).collect().row(0, named=True)
    c_high = detect_partnerships(high, Settings()).collect().row(0, named=True)

    assert 0.0 < c_low["confidence_score"] < 1.0
    assert 0.0 < c_high["confidence_score"] < 1.0
    assert c_high["confidence_score"] > c_low["confidence_score"]
    # 3 events -> 1 - 1/4 = 0.75 exactly.
    assert abs(c_low["confidence_score"] - 0.75) < 1e-9


def test_co_supply_must_share_item_not_just_month(ledger) -> None:
    """Two suppliers active in the same months but different items do not pair."""
    pov = ledger(
        [
            (date(2025, 1, 1), "V1", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 2, 1), "V2", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 3, 1), "V3", "Acme", "Wire", 1.0, 10.0),
            (date(2025, 1, 1), "V4", "Globex", "Bolt", 1.0, 10.0),
            (date(2025, 2, 1), "V5", "Globex", "Bolt", 1.0, 10.0),
            (date(2025, 3, 1), "V6", "Globex", "Bolt", 1.0, 10.0),
        ]
    )
    out = detect_partnerships(pov, Settings()).collect()
    assert out.height == 0


def test_partnership_output_column_order_matches_contract(ledger) -> None:
    """Schema must equal the Supplier_Partnerships sheet column order."""
    out = detect_partnerships(ledger([]), Settings()).collect()
    assert out.columns == _OUTPUT_COLUMNS


def test_empty_pov_returns_empty_contract(ledger) -> None:
    out = detect_partnerships(ledger([]), Settings()).collect()
    assert out.height == 0
    assert out.columns == _OUTPUT_COLUMNS
