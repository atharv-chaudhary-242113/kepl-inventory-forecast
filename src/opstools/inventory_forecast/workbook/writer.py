"""Workbook writer and persistence boundary.

This module handles workbook materialization and enforces the workbook
schema contract.

No forecasting logic, analytics logic, demand reconstruction, supplier
analysis, or classification logic should exist here.

All inputs must already be computed before reaching this layer.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

import polars as pl
import xlsxwriter

from opstools.inventory_forecast.domain import WorkbookMeta, WorksheetName
from opstools.inventory_forecast.workbook import schema
from opstools.inventory_forecast.workbook.cache import (
    DashboardCache,
)
from opstools.inventory_forecast.workbook.cache import (
    to_dataframe as cache_to_dataframe,
)

logger = logging.getLogger(__name__)


def write_workbook(
    output_path: Path,
    meta: WorkbookMeta,
    cache: DashboardCache,
    datasets: Mapping[
        WorksheetName,
        pl.LazyFrame | pl.DataFrame,
    ],
) -> None:
    """Write a complete workbook atomically.

    Parameters
    ----------
    output_path
        Final workbook destination.

    meta
        Workbook metadata.

    cache
        Dashboard cache data.

    datasets
        Engine outputs keyed by worksheet name.
    """
    _validate_dataset_mapping(datasets)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = output_path.with_name(
        f"{output_path.stem}.tmp.xlsx"
    )

    logger.info(
        "Writing workbook to %s",
        output_path,
    )

    try:
        with xlsxwriter.Workbook(
            temp_path,
        ) as workbook:

            for sheet_name in schema.required_sheet_names():

                logger.debug(
                    "Writing worksheet %s",
                    sheet_name.value,
                )

                dataframe = _resolve_dataframe(
                    sheet_name=sheet_name,
                    meta=meta,
                    cache=cache,
                    datasets=datasets,
                )

                schema.validate_sheet_columns(
                    sheet_name,
                    set(dataframe.columns),
                )

                dataframe.write_excel(
                    workbook=workbook,
                    worksheet=sheet_name.value,
                    table_style="Table Style Light 9",
                )

                # Release the reference before the next
                # potentially expensive LazyFrame collect.
                del dataframe

        temp_path.replace(output_path)

        logger.info(
            "Successfully wrote workbook %s",
            output_path,
        )

    except Exception:
        logger.exception(
            "Failed writing workbook %s",
            output_path,
        )
        raise

    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                logger.warning(
                    "Failed to delete temp file %s",
                    temp_path,
                )


def _validate_dataset_mapping(
    datasets: Mapping[
        WorksheetName,
        pl.LazyFrame | pl.DataFrame,
    ],
) -> None:
    """Validate worksheet coverage before writing."""
    required_sheets = set(
        schema.required_sheet_names()
    )

    special_sheets = {
        WorksheetName.METADATA,
        WorksheetName.DASHBOARD_CACHE,
    }

    expected_datasets = (
        required_sheets - special_sheets
    )

    provided_datasets = set(
        datasets.keys()
    )

    missing = (
        expected_datasets
        - provided_datasets
    )

    if missing:
        raise ValueError(
            "Missing required datasets: "
            + ", ".join(
                sheet.value
                for sheet in sorted(
                    missing,
                    key=lambda x: x.value,
                )
            )
        )

    unexpected = (
        provided_datasets
        - expected_datasets
    )

    if unexpected:
        raise ValueError(
            "Unexpected datasets supplied: "
            + ", ".join(
                sheet.value
                for sheet in sorted(
                    unexpected,
                    key=lambda x: x.value,
                )
            )
        )


def _resolve_dataframe(
    *,
    sheet_name: WorksheetName,
    meta: WorkbookMeta,
    cache: DashboardCache,
    datasets: Mapping[
        WorksheetName,
        pl.LazyFrame | pl.DataFrame,
    ],
) -> pl.DataFrame:
    """Materialize the dataframe associated with a worksheet."""
    if sheet_name == WorksheetName.METADATA:
        return _metadata_dataframe(meta)

    if sheet_name == WorksheetName.DASHBOARD_CACHE:
        return cache_to_dataframe(cache)

    frame = datasets[sheet_name]

    if isinstance(frame, pl.LazyFrame):
        return frame.collect()

    return frame


def _metadata_dataframe(
    meta: WorkbookMeta,
) -> pl.DataFrame:
    """Convert WorkbookMeta into worksheet form.

    Excel does not support timezone-aware datetimes,
    therefore timezone information is stripped before
    workbook persistence.
    """
    dataframe = pl.DataFrame(
        [meta.model_dump()]
    )

    generated_at_dtype = dataframe.schema.get(
        "generated_at"
    )

    if isinstance(
        generated_at_dtype,
        pl.Datetime,
    ):
        dataframe = dataframe.with_columns(
            pl.col("generated_at")
            .dt.replace_time_zone(None)
        )

    return dataframe
