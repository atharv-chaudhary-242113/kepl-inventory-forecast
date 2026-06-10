"""Shared pytest fixtures for the ingestion test suite.

ERP fixtures are synthesized on disk under each test's ``tmp_path`` rather than
committed as binaries. Generation is fully deterministic, so the same inputs
produce identical files across runs and machines (Constitution Rule 9); the
hashed sample datasets called for by BENCHMARK_PLAN.md belong to the Phase-7
benchmark harness, not these unit tests. The factories below let each test
construct exactly the ERP quirk it exercises (banner rows, hierarchical
suppliers, parenthetical branches, separator rows, ragged CSV lines).
"""

from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

import pytest
import xlsxwriter

# A row is a tuple of cells; a cell is a date, number, string, or None (blank).
Cell = date | int | float | str | None
Row = Sequence[Cell]

# The canonical ERP header shared by POV / GRN / PV exports (INPUT_SCHEMA.md).
LEDGER_HEADER: list[str] = [
    "Date",
    "Vch/Bill No",
    "Particulars",
    "Item Details",
    "Qty.",
    "Unit",
    "Price",
    "Amount",
]
CLOSING_HEADER: list[str] = ["Item Details", "Qty.", "Price", "Amount"]

# A few banner/title/blank rows an ERP prints before the real header. Header
# detection must see past these (INPUT_SCHEMA.md "Header Detection").
_BANNER: list[str] = [
    "KEPL Pvt Ltd",
    "Purchase Order Voucher",
    "01-Apr-2024 to 31-Mar-2025",
]


@pytest.fixture
def make_excel(tmp_path: Path) -> Callable[..., Path]:
    """Return a factory that writes an .xlsx fixture and yields its path."""

    def _factory(
        name: str,
        header: Sequence[str],
        rows: Sequence[Row],
        *,
        banner: bool = True,
    ) -> Path:
        path = tmp_path / name
        workbook = xlsxwriter.Workbook(str(path))
        worksheet = workbook.add_worksheet("Sheet1")
        date_format = workbook.add_format({"num_format": "dd-mm-yyyy"})

        cursor = 0
        if banner:
            for line in _BANNER:
                worksheet.write(cursor, 0, line)
                cursor += 1
            cursor += 1  # a blank formatting row before the header

        for column, title in enumerate(header):
            worksheet.write(cursor, column, title)
        cursor += 1

        for row in rows:
            for column, cell in enumerate(row):
                if cell is None:
                    continue
                if isinstance(cell, date):
                    worksheet.write_datetime(cursor, column, cell, date_format)
                elif isinstance(cell, (int, float)):
                    worksheet.write_number(cursor, column, cell)
                else:
                    worksheet.write(cursor, column, cell)
            cursor += 1

        workbook.close()
        return path

    return _factory


@pytest.fixture
def make_csv(tmp_path: Path) -> Callable[[str, str], Path]:
    """Return a factory that writes raw CSV text and yields its path."""

    def _factory(name: str, text: str) -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    return _factory
