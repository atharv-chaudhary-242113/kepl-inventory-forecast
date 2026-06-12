"""Canonical business contracts for normalized ERP datasets.

The ingestion layer transforms raw ERP exports into canonical datasets used by
the analytics engine. These contracts define the minimum schema guarantees that
must hold after normalization and before any business logic executes.

Raw ERP columns:

    Date             -> date
    Particulars      -> supplier
    Item Details     -> item
    Material Centre  -> material_centre
    Qty.             -> qty
    Unit             -> unit
    Price            -> price
    Amount           -> amount
    Notes            -> notes

POV, GRN, and PV share the same normalized structure and therefore inherit the
same contract requirements.

Closing Stock follows a separate contract because it represents inventory
position snapshots rather than procurement transactions.
"""

from typing import Final

# ---------------------------------------------------------------------------
# Canonical transaction schema
# ---------------------------------------------------------------------------

ERP_TRANSACTION_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    "supplier",
    "item",
    "material_centre",
    "qty",
    "unit",
    "price",
    "amount",
    "notes",
)

# ---------------------------------------------------------------------------
# Mandatory columns
# ---------------------------------------------------------------------------

TRANSACTION_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    "supplier",
    "item",
    "qty",
    "price",
    "amount",
)

# ---------------------------------------------------------------------------
# Non-null business invariants
# ---------------------------------------------------------------------------

TRANSACTION_NON_NULL_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    "supplier",
    "item",
    "qty",
    "price",
    "amount",
)

# ---------------------------------------------------------------------------
# Dataset-specific contracts
# ---------------------------------------------------------------------------

POV_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (*TRANSACTION_REQUIRED_COLUMNS,)

GRN_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (*TRANSACTION_REQUIRED_COLUMNS,)

PV_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (*TRANSACTION_REQUIRED_COLUMNS,)

CLOSING_STOCK_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    "item",
    "qty",
)

CLOSING_STOCK_NON_NULL_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    "item",
    "qty",
)
