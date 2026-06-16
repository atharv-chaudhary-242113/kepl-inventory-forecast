"""Workbook schema contract.

Owns the workbook format definition used by writer.py and reader.py.

This module is the single source of truth for:

- Workbook schema version
- Worksheet names
- Required worksheet columns
- Metadata validation
- Workbook compatibility checks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from packaging.version import InvalidVersion, Version

from opstools.inventory_forecast.domain.enums import (
    WorksheetName,
)
from opstools.inventory_forecast.domain.errors import (
    WorkbookVersionError,
    WorksheetSchemaError,
)
from opstools.inventory_forecast.domain.models import WorkbookMeta

WORKBOOK_SCHEMA_VERSION: Final[Version] = Version("1.0.0")
SUPPORTED_MAJOR_VERSION: Final[int] = 1

WORKBOOK_SHEET_ORDER: Final[tuple[WorksheetName, ...]] = (
    WorksheetName.METADATA,
    WorksheetName.DEMAND_HISTORY,
    WorksheetName.FORECASTS,
    WorksheetName.SUPPLIER_ANALYSIS,
    WorksheetName.SUPPLIER_PARTNERSHIPS,
    WorksheetName.LEAD_TIME_ANALYSIS,
    WorksheetName.PENDING_DELIVERIES,
    WorksheetName.FINANCIAL_SUMMARY,
    WorksheetName.ABC_CLASSIFICATION,
    WorksheetName.SBC_CLASSIFICATION,
    WorksheetName.INVENTORY_VALUATION,
    WorksheetName.DASHBOARD_CACHE,
)


@dataclass(frozen=True, slots=True)
class WorksheetSchema:
    """Worksheet schema."""

    name: WorksheetName
    required_columns: tuple[str, ...]


WORKSHEETS: Final[dict[WorksheetName, WorksheetSchema]] = {
    WorksheetName.METADATA: WorksheetSchema(
        name=WorksheetName.METADATA,
        required_columns=(
            "schema_version",
            "application_version",
            "generated_at",
            "source_hash",
            "output_hash",
            "forecast_horizon",
            "total_suppliers",
            "total_items",
            "total_records",
            "processing_time_seconds",
        ),
    ),
    WorksheetName.DEMAND_HISTORY: WorksheetSchema(
        name=WorksheetName.DEMAND_HISTORY,
        required_columns=(
            "period",
            "supplier",
            "item",
            "demand_quantity",
            "demand_value",
        ),
    ),
    WorksheetName.FORECASTS: WorksheetSchema(
        name=WorksheetName.FORECASTS,
        required_columns=(
            "supplier",
            "item",
            "forecast_period",
            "forecast_quantity",
            "forecast_value",
            "trend_component",
            "seasonal_component",
            "model_used",
            "confidence_score",
        ),
    ),
    WorksheetName.SUPPLIER_ANALYSIS: WorksheetSchema(
        name=WorksheetName.SUPPLIER_ANALYSIS,
        required_columns=(
            "supplier",
            "total_spend",
            "total_orders",
            "total_deliveries",
            "average_lead_time",
            "lead_time_stddev",
            "pending_deliveries",
            "reliability_score",
            "risk_score",
        ),
    ),
    WorksheetName.SUPPLIER_PARTNERSHIPS: WorksheetSchema(
        name=WorksheetName.SUPPLIER_PARTNERSHIPS,
        required_columns=(
            "supplier_a",
            "supplier_b",
            "matching_events",
            "confidence_score",
            "status",
        ),
    ),
    WorksheetName.LEAD_TIME_ANALYSIS: WorksheetSchema(
        name=WorksheetName.LEAD_TIME_ANALYSIS,
        required_columns=(
            "supplier",
            "item",
            "pov_date",
            "grn_date",
            "ordered_qty",
            "delivered_qty",
            "lead_time_days",
        ),
    ),
    WorksheetName.PENDING_DELIVERIES: WorksheetSchema(
        name=WorksheetName.PENDING_DELIVERIES,
        required_columns=(
            "supplier",
            "item",
            "voucher_number",
            "ordered_qty",
            "delivered_qty",
            "pending_qty",
            "order_date",
            "age_days",
        ),
    ),
    WorksheetName.FINANCIAL_SUMMARY: WorksheetSchema(
        name=WorksheetName.FINANCIAL_SUMMARY,
        required_columns=(
            "supplier",
            "item",
            "quantity",
            "unit_cost",
            "freight_cost",
            "total_cost",
            "total_spend",
        ),
    ),
    WorksheetName.ABC_CLASSIFICATION: WorksheetSchema(
        name=WorksheetName.ABC_CLASSIFICATION,
        required_columns=(
            "supplier",
            "item",
            "annual_value",
            "cumulative_percentage",
            "abc_class",
        ),
    ),
    WorksheetName.SBC_CLASSIFICATION: WorksheetSchema(
        name=WorksheetName.SBC_CLASSIFICATION,
        required_columns=(
            "supplier",
            "item",
            "adi",
            "cv_squared",
            "demand_class",
        ),
    ),
    WorksheetName.INVENTORY_VALUATION: WorksheetSchema(
        name=WorksheetName.INVENTORY_VALUATION,
        required_columns=(
            "item",
            "quantity",
            "unit_cost",
            "inventory_value",
            "snapshot_date",
        ),
    ),
    WorksheetName.DASHBOARD_CACHE: WorksheetSchema(
        name=WorksheetName.DASHBOARD_CACHE,
        required_columns=(),
    ),
}


def validate_workbook_version(version: str) -> None:
    """Validate workbook schema compatibility."""
    try:
        parsed = Version(version)
    except InvalidVersion as exc:
        raise WorkbookVersionError(
            f"Invalid workbook schema version: {version!r}"
        ) from exc

    if parsed.major != SUPPORTED_MAJOR_VERSION:
        raise WorkbookVersionError(
            f"Incompatible workbook schema version "
            f"{version!r}. "
            f"Supported major version is "
            f"{SUPPORTED_MAJOR_VERSION}"
        )


def validate_metadata(meta: WorkbookMeta) -> None:
    """Validate metadata contract."""
    validate_workbook_version(meta.schema_version)

    if meta.forecast_horizon <= 0:
        raise WorksheetSchemaError("forecast_horizon must be greater than zero.")

    if meta.total_suppliers < 0:
        raise WorksheetSchemaError("total_suppliers cannot be negative.")

    if meta.total_items < 0:
        raise WorksheetSchemaError("total_items cannot be negative.")

    if meta.total_records < 0:
        raise WorksheetSchemaError("total_records cannot be negative.")

    if meta.processing_time_seconds < 0:
        raise WorksheetSchemaError("processing_time_seconds cannot be negative.")


def validate_sheet_columns(
    sheet_name: WorksheetName,
    columns: set[str],
) -> None:
    """Validate required worksheet columns."""
    if sheet_name not in WORKSHEETS:
        raise WorksheetSchemaError(f"Unknown worksheet: {sheet_name!r}.")

    required = set(WORKSHEETS[sheet_name].required_columns)

    missing = required - columns
    unexpected = columns - required

    if missing or unexpected:
        parts: list[str] = []

        if missing:
            parts.append("missing columns: " + ", ".join(sorted(missing)))

        if unexpected:
            parts.append("unexpected columns: " + ", ".join(sorted(unexpected)))

        raise WorksheetSchemaError(
            f"Worksheet {sheet_name!r} " + "; ".join(parts) + "."
        )


def required_sheet_names() -> tuple[WorksheetName, ...]:
    """Return workbook sheet order."""
    return WORKBOOK_SHEET_ORDER


def get_sheet_schema(
    sheet_name: WorksheetName,
) -> WorksheetSchema:
    """Return worksheet schema."""
    try:
        return WORKSHEETS[sheet_name]
    except KeyError as exc:
        raise WorksheetSchemaError(f"Unknown worksheet: {sheet_name!r}") from exc


def is_known_sheet(
    sheet_name: str | WorksheetName,
) -> bool:
    """Return True if worksheet is known."""
    return sheet_name in WORKSHEETS
