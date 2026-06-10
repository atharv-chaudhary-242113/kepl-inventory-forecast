"""Source-file reader: the public ingestion entry point and trust boundary.

`read_source` is the one function other layers call to turn a raw ERP export
into a clean, typed, validated Polars frame. It is also the trust boundary for
external files (Constitution Rule 7): the very first thing it does is run the
security path/size guards, before any bytes are parsed.

The reader's only format-specific job is to produce a rectangular, all-string
*grid* (positional column names) regardless of source format; everything after
that — header detection, canonical mapping, casting, validation — is shared and
format-agnostic. Reading as text first is deliberate: it lets the same dynamic
header-detection logic run for .xlsx, .xls, and .csv, and keeps us in control of
date/number parsing rather than trusting per-engine type inference.
"""

from pathlib import Path

import polars as pl

from opstools.inventory_forecast.domain.enums import SourceKind
from opstools.inventory_forecast.domain.errors import SchemaError
from opstools.inventory_forecast.ingestion.header_detection import (
    SCAN_LIMIT,
    detect_header_row,
)
from opstools.inventory_forecast.ingestion.schema import (
    finalize_records,
    map_to_canonical,
    required_erp_columns,
)
from opstools.inventory_forecast.security.paths import (
    enforce_file_size_limits,
    validate_local_path,
)

_EXCEL_SUFFIXES: frozenset[str] = frozenset({".xlsx", ".xls", ".xlsm"})


def read_source(path: Path, kind: SourceKind) -> pl.LazyFrame:
    """Read a raw ERP export into a normalized, validated LazyFrame.

    Guarantees on the returned frame: canonical column names and dtypes per the
    domain schema; for ledgers, supplier is forward-filled and parenthetical-
    normalized and date is a Polars `Date`; qty/price/amount are non-negative,
    with price/amount as `Decimal`.

    Validation is performed eagerly at this boundary (the file is read once) and
    the result is returned as a LazyFrame so downstream stages compose lazily.

    Raises:
        SecurityError: the path or file fails a THREAT_MODEL.md path/size guard.
        SchemaError: no header row was found, or a required column is missing.
        ValidationError: a value violates a domain constraint.
    """
    # Trust boundary: validate the untrusted path and bound its size before we
    # ever open it (THREAT_MODEL.md path-traversal/UNC/ZIP-bomb controls).
    validate_local_path(path)
    enforce_file_size_limits(path)

    label = path.name
    expected = required_erp_columns(kind)

    grid = _read_grid(path)

    # Bounded top-of-sheet scan for the header; convert that slice to Python rows
    # (one small materialization, not the whole sheet) so detection can compare
    # cell-by-cell.
    scan_rows = grid.head(SCAN_LIMIT).rows()
    header_index = detect_header_row(scan_rows, expected)
    if header_index is None:
        msg = f"{label}: could not locate a header row matching {expected}"
        raise SchemaError(msg)

    table = _extract_table(grid, header_index)
    canonical = map_to_canonical(table, kind, label)
    validated = finalize_records(canonical, kind, label)
    return validated.lazy()


def _read_grid(path: Path) -> pl.DataFrame:
    """Read any supported source into a rectangular all-string DataFrame.

    Columns are positionally named (column_1, column_2, ...); the real header is
    found later by `detect_header_row`. Reading everything as text means a date
    or number sitting under a textual banner does not corrupt per-column type
    inference, and we keep full control of parsing downstream.
    """
    suffix = path.suffix.lower()
    if suffix in _EXCEL_SUFFIXES:
        return _read_excel_grid(path)
    return _read_csv_grid(path)


def _read_excel_grid(path: Path) -> pl.DataFrame:
    """Read the first worksheet as an all-string, header-less frame.

    `has_header=False` keeps the banner/title rows as data so header detection
    can find the real header wherever it sits; `dtypes="string"` forces every
    cell to text (fastexcel renders Excel date serials as ISO datetime strings
    here, which the date parser then handles). Only the first sheet is read;
    multi-sheet concatenation is a documented future extension (INPUT_SCHEMA.md).
    """
    return pl.read_excel(
        path,
        engine="calamine",
        has_header=False,
        read_options={"dtypes": "string"},
    )


def _read_csv_grid(path: Path) -> pl.DataFrame:
    """Read a CSV into an all-string grid, tolerant of ragged metadata rows.

    A naive `read_csv` would lock the column count to the first line, which for
    an ERP export is a one-cell banner — collapsing the table to a single column.
    We instead parse with Python's `csv` reader (it handles quoting correctly),
    drop fully-blank lines, pad ragged rows to the widest row, and build the
    positional frame ourselves. This runs once per file at ingestion, not in the
    analytics hot path, so the row-wise read is acceptable (CODING_STANDARDS.md).
    """
    import csv

    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows: list[list[str]] = [
            [(cell if cell is not None else "") for cell in record]
            for record in csv.reader(handle)
        ]

    rows = [row for row in rows if any(cell.strip() != "" for cell in row)]
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        # An empty file has no header; surface it the same way a headerless sheet
        # would, via the caller's SchemaError path, by returning an empty frame.
        return pl.DataFrame()

    padded = [row + [""] * (width - len(row)) for row in rows]
    data: dict[str, list[str]] = {
        f"column_{index + 1}": [row[index] for row in padded] for index in range(width)
    }
    return pl.DataFrame(data)


def _extract_table(grid: pl.DataFrame, header_index: int) -> pl.DataFrame:
    """Slice the rows below the header and rename columns to the header's cells.

    Duplicate or empty header cells get unique placeholder names so Polars (which
    requires unique column names) accepts the frame; such columns are not part of
    any expected schema and are dropped during canonical mapping.
    """
    header_cells = grid.row(header_index)
    names: list[str] = []
    seen: set[str] = set()
    for position, cell in enumerate(header_cells):
        name = (cell or "").strip()
        if name == "" or name in seen:
            name = f"__unnamed_{position}"
        seen.add(name)
        names.append(name)

    data = grid.slice(header_index + 1)
    data.columns = names
    return data
