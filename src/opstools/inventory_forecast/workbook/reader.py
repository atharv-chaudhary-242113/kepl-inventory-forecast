"""Workbook reader and persistence boundary.

This module handles workbook ingestion, schema validation,
and dashboard cache reconstruction. It closes the I/O
persistence loop started by writer.py.

No analytic or forecasting computation occurs here. It only
returns immutable models and dataframes.
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl
from pydantic import ValidationError
from python_calamine import CalamineWorkbook

from opstools.inventory_forecast.domain.enums import WorksheetName
from opstools.inventory_forecast.domain.errors import (
    WorkbookError,
    WorksheetMetaDataError,
    WorksheetSchemaError,
)
from opstools.inventory_forecast.domain.models import WorkbookMeta
from opstools.inventory_forecast.workbook import schema
from opstools.inventory_forecast.workbook.cache import (
    DashboardCache,
)
from opstools.inventory_forecast.workbook.cache import (
    from_dataframe as cache_from_dataframe,
)

logger = logging.getLogger(__name__)


def load_dashboard_state(
    path: Path,
) -> tuple[WorkbookMeta, DashboardCache]:
    """Load the minimal workbook state required by the dashboard.

    This avoids loading heavy analytical worksheets and allows
    the UI to start without recomputation.
    """
    logger.info(
        "Loading dashboard state from %s",
        path,
    )

    _validate_workbook_path(path)
    _validate_workbook_completeness(path)

    metadata = read_metadata(path)
    cache = read_cache(path)

    return metadata, cache


def read_metadata(
    path: Path,
) -> WorkbookMeta:
    """Read and validate workbook metadata."""
    logger.debug(
        "Reading metadata from %s",
        path,
    )

    dataframe = read_worksheet(
        path,
        WorksheetName.METADATA,
    )

    if dataframe.is_empty():
        raise WorksheetMetaDataError(
            "Metadata worksheet is empty."
        )

    if dataframe.height != 1:
        raise WorksheetMetaDataError(
            "Metadata worksheet must contain exactly one row."
        )

    record = dataframe.row(
        0,
        named=True,
    )

    try:
        metadata = WorkbookMeta(
            **record
        )
    except ValidationError as exc:
        raise WorksheetMetaDataError(
            f"Metadata validation failed: {exc}"
        ) from exc

    try:
        schema.validate_metadata(
            metadata
        )
    except Exception as exc:
        raise WorksheetMetaDataError(
            f"Metadata schema validation failed: {exc}"
        ) from exc

    logger.debug(
        "Workbook schema version: %s",
        metadata.schema_version,
    )

    return metadata


def read_cache(
    path: Path,
) -> DashboardCache:
    """Read and reconstruct dashboard cache state."""
    dataframe = read_worksheet(
        path,
        WorksheetName.DASHBOARD_CACHE,
    )

    try:
        return cache_from_dataframe(
            dataframe
        )
    except ValueError as exc:
        raise WorksheetSchemaError(
            f"Failed to reconstruct dashboard cache: {exc}"
        ) from exc


def read_worksheet(
    path: Path,
    sheet_name: WorksheetName,
) -> pl.DataFrame:
    """Read a worksheet and enforce schema constraints."""
    _validate_workbook_path(path)

    logger.debug(
        "Reading worksheet %s from %s",
        sheet_name.value,
        path,
    )

    try:
        dataframe = pl.read_excel(
            path,
            sheet_name=sheet_name.value,
            engine="calamine",
        )
    except Exception as exc:
        raise WorkbookError(
            f"Failed to read worksheet "
            f"{sheet_name.value}: {exc}"
        ) from exc

    try:
        schema.validate_sheet_columns(
            sheet_name,
            set(dataframe.columns),
        )
    except Exception as exc:
        raise WorksheetSchemaError(
            f"Worksheet {sheet_name.value} "
            f"failed schema validation: {exc}"
        ) from exc

    logger.debug(
        "Loaded worksheet %s "
        "(rows=%s, cols=%s)",
        sheet_name.value,
        dataframe.height,
        dataframe.width,
    )

    return dataframe


def _validate_workbook_path(
    path: Path,
) -> None:
    """Validate workbook path before any I/O."""
    if not path.exists():
        raise WorkbookError(
            f"Workbook does not exist: {path}"
        )

    if not path.is_file():
        raise WorkbookError(
            f"Workbook path is not a file: {path}"
        )

    if path.suffix.lower() != ".xlsx":
        raise WorkbookError(
            f"Expected .xlsx workbook, got: {path.name}"
        )


def _validate_workbook_completeness(
    path: Path,
) -> None:
    """Validate that all required worksheets are physically
    present before attempting workbook reconstruction.
    """  # noqa: D205
    try:
        workbook = CalamineWorkbook.from_path(
            str(path)
        )
    except Exception as exc:
        raise WorkbookError(
            f"Failed to inspect workbook: {exc}"
        ) from exc

    available_sheets = set(
        workbook.sheet_names
    )

    expected_sheets = {
        sheet.value
        for sheet in schema.required_sheet_names()
    }

    missing_sheets = (
        expected_sheets
        - available_sheets
    )

    if missing_sheets:
        raise WorkbookError(
            "Workbook is missing required worksheets: "
            + ", ".join(
                sorted(missing_sheets)
            )
        )

    logger.debug(
        "Workbook completeness validation passed."
    )
