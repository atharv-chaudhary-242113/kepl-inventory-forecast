"""Unit tests for semantic header-row detection."""

from opstools.inventory_forecast.ingestion import (
    detect_header_row,
    normalize_token,
)

_EXPECTED = ["Date", "Particulars", "Item Details", "Qty."]


def test_normalize_token_strips_case_and_whitespace():
    assert normalize_token(" Item Details ") == "itemdetails"
    assert normalize_token("ITEMDETAILS") == "itemdetails"
    assert normalize_token(None) == ""


def test_normalize_token_preserves_punctuation():
    # "Qty." must not collapse onto "Qty"; the dot is meaningful for matching.
    assert normalize_token("Qty.") == "qty."
    assert normalize_token("Qty.") != normalize_token("Qty")


def test_header_found_after_metadata_rows():
    grid = [
        ["KEPL Pvt Ltd", "", "", ""],
        ["Purchase Order Voucher", "", "", ""],
        ["", "", "", ""],
        ["Date", "Particulars", "Item Details", "Qty."],
        ["2025-01-01", "ABC", "Wire", "10"],
    ]
    assert detect_header_row(grid, _EXPECTED) == 3


def test_no_matching_header_returns_none():
    grid = [["foo", "bar"], ["1", "2"]]
    assert detect_header_row(grid, _EXPECTED) is None


def test_empty_scan_returns_none():
    assert detect_header_row([], _EXPECTED) is None


def test_empty_expected_columns_returns_none():
    grid = [["Date", "Particulars", "Item Details", "Qty."]]
    assert detect_header_row(grid, []) is None


def test_detection_is_case_and_space_insensitive():
    grid = [[" DATE ", "particulars", "ITEM DETAILS", "qty."]]
    assert detect_header_row(grid, _EXPECTED) == 0


def test_ties_resolve_to_first_row():
    # Two rows each match exactly one expected column; the topmost wins.
    grid = [
        ["Date", "junk"],
        ["other", "Qty."],
    ]
    assert detect_header_row(grid, _EXPECTED) == 0


def test_real_header_beats_stray_metadata_match():
    # A metadata cell coincidentally equals one column name, but the genuine
    # header matches several, so the header row (index 1) must win.
    grid = [
        ["Date", "report generated on monday"],
        ["Date", "Particulars", "Item Details", "Qty."],
        ["2025-01-01", "ABC", "Wire", "10"],
    ]
    assert detect_header_row(grid, _EXPECTED) == 1
