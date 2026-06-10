"""Frame factories for the Phase-2 engine unit tests.

The engine assumes clean, canonical frames (API_CONTRACT.md): ingestion has
already mapped columns, parsed dates to ``Date``, and cast money to ``Decimal``.
These factories build exactly those frames in memory so each engine test states
the canonical input directly, without round-tripping through a file. The dtypes
mirror the ingestion contract precisely — money is ``Decimal(scale=4)`` — so the
tests exercise the same Decimal arithmetic the real pipeline does.
"""

from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal

import polars as pl
import pytest

# Ingestion emits money at this scale (ingestion/schema.py MONEY_SCALE); the
# engine fixtures must match so Decimal joins/sums behave identically.
MONEY = pl.Decimal(scale=4)

# A canonical ledger row: (date, voucher, supplier, item, qty, amount). Unit and
# price are present in the real schema but unused by the Phase-2 engine, so the
# factory fills them with neutral constants to keep call sites readable.
LedgerRow = tuple[date | None, str, str, str, float, float]

_LEDGER_SCHEMA = {
    "date": pl.Date,
    "voucher": pl.Utf8,
    "supplier": pl.Utf8,
    "item": pl.Utf8,
    "qty": pl.Float64,
    "unit": pl.Utf8,
    "price": MONEY,
    "amount": MONEY,
}
_CLOSING_SCHEMA = {
    "item": pl.Utf8,
    "qty": pl.Float64,
    "price": MONEY,
    "amount": MONEY,
}


@pytest.fixture
def ledger() -> Callable[[Sequence[LedgerRow]], pl.LazyFrame]:
    """Return a factory building a canonical POV/GRN/PV ledger LazyFrame.

    Each row is ``(date, voucher, supplier, item, qty, amount)``; price is
    derived as ``amount / qty`` (0 when qty is 0) purely so the column is
    populated — the engine reads ``amount``, not ``price``, for ledgers.
    """

    def _factory(rows: Sequence[LedgerRow]) -> pl.LazyFrame:
        return pl.LazyFrame(
            {
                "date": [r[0] for r in rows],
                "voucher": [r[1] for r in rows],
                "supplier": [r[2] for r in rows],
                "item": [r[3] for r in rows],
                "qty": [r[4] for r in rows],
                "unit": ["nos"] * len(rows),
                "price": [
                    Decimal(str(r[5] / r[4])) if r[4] else Decimal("0") for r in rows
                ],
                "amount": [Decimal(str(r[5])) for r in rows],
            },
            schema=_LEDGER_SCHEMA,
        )

    return _factory


@pytest.fixture
def closing() -> Callable[[Sequence[tuple[str, float, float]]], pl.LazyFrame]:
    """Return a factory building a canonical closing-stock LazyFrame.

    Each row is ``(item, qty, price)``; amount is derived as ``qty * price`` to
    keep the snapshot internally consistent.
    """

    def _factory(rows: Sequence[tuple[str, float, float]]) -> pl.LazyFrame:
        return pl.LazyFrame(
            {
                "item": [r[0] for r in rows],
                "qty": [r[1] for r in rows],
                "price": [Decimal(str(r[2])) for r in rows],
                "amount": [Decimal(str(r[1] * r[2])) for r in rows],
            },
            schema=_CLOSING_SCHEMA,
        )

    return _factory
