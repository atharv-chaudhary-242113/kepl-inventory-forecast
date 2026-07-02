"""Workbook ingestion and reading.

Provides strict read access to the generated Business Intelligence
workbook. Dashboards and secondary reporting tools must use this
module to read pre-computed data, enforcing the "single source of truth"
architecture.

By forcing dashboards to read from the workbook (via this module) rather
than directly from the engine, we guarantee that managers see exactly
what is in the Excel file, with zero duplicate computation.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from opstools.inventory_forecast.domain.enums import WorksheetName
from opstools.inventory_forecast.domain.errors import (
    WorkbookVersionError,
    WorksheetSchemaError,
)
from opstools.inventory_forecast.workbook.schema import (
    get_sheet_schema,
    validate_sheet_columns,
    validate_workbook_version,
)


def read_worksheet(path: Path, sheet_name: WorksheetName) -> pl.DataFrame:
    """Read and validate a specific worksheet from the BI workbook.

    Args:
        path: Path to the generated Excel workbook.
        sheet_name: The target worksheet to read.

    Returns:
        A Polars DataFrame containing the worksheet data.

    Raises:
        FileNotFoundError: If the workbook does not exist.
        WorksheetSchemaError: If the worksheet is missing or malformed.
    """
    if not path.exists():
        raise FileNotFoundError(f"Workbook not found at {path}")

    try:
        # Calamine engine provides high-performance, memory-safe Excel parsing
        df = pl.read_excel(
            source=path,
            sheet_name=sheet_name.value,
            engine="calamine",
        )
    except Exception as exc:
        raise WorksheetSchemaError(
            f"Failed to read worksheet {sheet_name.value!r} from {path}. "
            f"The sheet may be missing or the file may be corrupted."
        ) from exc

    # Enforce schema contract immediately upon read
    _validate_read_schema(sheet_name, df)

    return df


def _validate_read_schema(sheet_name: WorksheetName, df: pl.DataFrame) -> None:
    """Validate DataFrame against the strict worksheet schema."""
    if sheet_name == WorksheetName.DASHBOARD_CACHE:
        # Dashboard cache is structurally fluid; skip strict column validation
        return

    validate_sheet_columns(sheet_name, set(df.columns))

    # Ensure required columns maintain correct basic types
    schema = get_sheet_schema(sheet_name)

    # We do not strictly cast here to avoid data destruction, but we verify presence.
    # Typecasting is pushed to the explicit read functions
    # if specific metrics are needed.
    missing_cols = set(schema.required_columns) - set(df.columns)
    if missing_cols:
        raise WorksheetSchemaError(
            f"Worksheet {sheet_name.value!r} missing required columns: {missing_cols}"
        )


def verify_workbook_compatibility(path: Path) -> None:
    """Verify that the workbook is compatible with the current application version.

    Reads the Metadata sheet and checks the schema_version against the
    system's supported major version.
    """
    try:
        meta_df = read_worksheet(path, WorksheetName.METADATA)
    except Exception as exc:
        raise WorkbookVersionError(
            "Could not read Metadata sheet to verify version."
        ) from exc

    if "schema_version" not in meta_df.columns:
        raise WorkbookVersionError("Metadata sheet is missing 'schema_version' column.")

    if meta_df.height == 0:
        raise WorkbookVersionError("Metadata sheet is empty.")

    version_str = meta_df.get_column("schema_version").item(0)
    if not isinstance(version_str, str):
        version_str = str(version_str)

    validate_workbook_version(version_str)


# ======================================================================================
# Business Intelligence Dashboard Accessors
# ======================================================================================


def read_dashboard_data(path: Path) -> pl.DataFrame:
    """Read pre-computed dashboard visualization metrics.

    This is the primary data source for Plotly charting.
    """
    return read_worksheet(path, WorksheetName.DASHBOARD_DATA)


def read_executive_summary(path: Path) -> pl.DataFrame:
    """Read high-level executive KPIs."""
    return read_worksheet(path, WorksheetName.EXECUTIVE_SUMMARY)


def read_procurement_insights(path: Path) -> pl.DataFrame:
    """Read actionable alerts and insights for procurement managers."""
    return read_worksheet(path, WorksheetName.PROCUREMENT_INSIGHTS)


def read_inventory_health(path: Path) -> pl.DataFrame:
    """Read the current inventory health status for all items."""
    return read_worksheet(path, WorksheetName.INVENTORY_HEALTH)


def read_supplier_risks(path: Path) -> pl.DataFrame:
    """Read supplier risk profiles and dependency warnings."""
    return read_worksheet(path, WorksheetName.SUPPLIER_RISK)


def read_forecasts(path: Path) -> pl.DataFrame:
    """Read the generated demand forecasts.

    Note: Under the BI platform architecture, forecasting is a secondary
    analytical layer. Dashboards should prioritize health and risk metrics.
    """
    return read_worksheet(path, WorksheetName.FORECASTS)
