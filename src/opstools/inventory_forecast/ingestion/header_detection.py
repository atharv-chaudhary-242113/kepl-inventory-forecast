"""Semantic header-row detection (INPUT_SCHEMA.md "Header Detection").

ERP exports prepend company banners, report titles, date ranges, and blank
formatting rows before the real tabular header, and the header position varies
between reports. We therefore never assume row 0 is the header: we scan the top
of the sheet and pick the row whose cells best match the expected column names,
comparing case- and whitespace-insensitively (INPUT_SCHEMA.md "Header Matching").
"""

from collections.abc import Sequence

# We only scan the top of the sheet for the header. A real header sits within the
# first handful of rows (banner + title + date-range + a blank or two); bounding
# the scan keeps detection O(SCAN_LIMIT * cols) instead of O(rows * cols) and
# stops a data row that happens to echo a column name from being chosen.
SCAN_LIMIT: int = 50


def normalize_token(value: str | None) -> str:
    """Canonicalize a cell/column token for comparison.

    Lower-cases and strips *all* internal whitespace so "Item Details",
    "item details", and " ITEMDETAILS " all collapse to "itemdetails".
    Punctuation is preserved, so "Qty." stays distinct from "Qty".
    """
    if value is None:
        return ""
    return "".join(value.lower().split())


def detect_header_row(
    rows: Sequence[Sequence[str | None]],
    expected_columns: Sequence[str],
) -> int | None:
    """Return the index of the most likely header row, or None if none matches.

    A row's score is the count of its cells whose normalized value exactly equals
    a normalized expected column name. The highest-scoring row wins; ties resolve
    to the first (topmost) row, since the genuine header precedes the data. A row
    must match at least one expected column to qualify — a sheet with no such row
    has no detectable header.
    """
    expected = {normalize_token(name) for name in expected_columns}

    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(rows):
        score = sum(1 for cell in row if normalize_token(cell) in expected)
        # Strictly-greater keeps the first row on ties (the header beats any later
        # data row that coincidentally repeats a column label).
        if score > best_score:
            best_index = index
            best_score = score

    return best_index
