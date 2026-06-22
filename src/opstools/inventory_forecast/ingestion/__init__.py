"""Ingestion layer: untrusted ERP exports -> clean, typed, validated frames.

Re-exports the public entry point so callers write
`from opstools.inventory_forecast.ingestion import read_source`. Depends only on
`domain` and `security` (ARCHITECTURE.md sec 4.2).
"""

from .header_detection import (
    detect_header_row,
    normalize_token,
)
from .normalize import (
    blank_to_null_expr,
    forward_fill_supplier_expr,
    normalize_supplier_expr,
)
from .reader import read_source
from .schema import (
    canonical_columns,
    column_mapping,
    finalize_records,
    is_ledger,
    map_to_canonical,
    required_erp_columns,
)

__all__ = (
    "blank_to_null_expr",
    "canonical_columns",
    "column_mapping",
    "detect_header_row",
    "finalize_records",
    "forward_fill_supplier_expr",
    "is_ledger",
    "map_to_canonical",
    "normalize_supplier_expr",
    "normalize_token",
    "read_source",
    "required_erp_columns",
)
