"""Workbook generation, reading, and schema enforcement.

This package manages the single-source-of-truth Excel workbook that powers
the Business Intelligence platform. It enforces schema contracts and prevents
duplicate computation by ensuring dashboards read directly from pre-computed
outputs.
"""

from .reader import (
    read_dashboard_data,
    read_executive_summary,
    read_forecasts,
    read_inventory_health,
    read_procurement_insights,
    read_supplier_risks,
    read_worksheet,
    verify_workbook_compatibility,
)
from .schema import (
    WORKBOOK_SCHEMA_VERSION,
    WorksheetName,
    validate_metadata,
)
from .writer import write_workbook

__all__ = [
    "WORKBOOK_SCHEMA_VERSION",
    "WorksheetName",
    "read_dashboard_data",
    "read_executive_summary",
    "read_forecasts",
    "read_inventory_health",
    "read_procurement_insights",
    "read_supplier_risks",
    "read_worksheet",
    "validate_metadata",
    "verify_workbook_compatibility",
    "write_workbook",
]
