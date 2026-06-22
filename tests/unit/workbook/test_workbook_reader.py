from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import polars as pl
import pytest
from pytz import UTC

from opstools.inventory_forecast.domain import (
    WorkbookError,
    WorksheetMetaDataError,
    WorksheetName,
    WorksheetSchemaError,
)

# noinspection PyProtectedMember
from opstools.inventory_forecast.workbook.reader import (
    validate_workbook_completeness,
    _validate_workbook_path,
    load_dashboard_state,
    read_cache,
    read_metadata,
    read_worksheet,
)
from opstools.inventory_forecast.workbook.schema import required_sheet_names


def test_validate_workbook_path_missing() -> None:
    with pytest.raises(
        WorkbookError
    ):
        _validate_workbook_path(
            Path("missing.xlsx")
        )


def test_validate_workbook_path_wrong_extension(
    tmp_path: Path,
) -> None:
    file = tmp_path / "test.txt"
    file.write_text("x")

    with pytest.raises(
        WorkbookError
    ):
        _validate_workbook_path(file)


@patch(
    "opstools.inventory_forecast.workbook.reader.read_worksheet"
)
def test_read_metadata_empty(
    mock_read: Mock,
) -> None:
    mock_read.return_value = pl.DataFrame()

    with pytest.raises(
        WorksheetMetaDataError
    ):
        read_metadata(
            Path("dummy.xlsx")
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.read_worksheet"
)
def test_read_metadata_multiple_rows(
    mock_read: Mock,
) -> None:
    mock_read.return_value = pl.DataFrame(
        {
            "schema_version": [
                "1.0.0",
                "1.0.0",
            ]
        }
    )

    with pytest.raises(
        WorksheetMetaDataError
    ):
        read_metadata(
            Path("dummy.xlsx")
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.read_worksheet"
)
def test_read_cache_wraps_value_error(
    mock_read: Mock,
) -> None:
    mock_read.return_value = pl.DataFrame(
        {"x": [1]}
    )

    with pytest.raises(
        WorksheetSchemaError
    ):
        read_cache(
            Path("dummy.xlsx")
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.CalamineWorkbook"
)
def test_validate_workbook_completeness_detects_missing_sheet(
    mock_workbook: Mock,
    tmp_path: Path,
) -> None:
    workbook = Mock()
    workbook.sheet_names = ["Metadata"]

    mock_workbook.from_path.return_value = workbook

    with pytest.raises(
        WorkbookError,
        match="missing required worksheets",
    ):
        validate_workbook_completeness(
            tmp_path / "file.xlsx"
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.pl.read_excel"
)
def test_read_worksheet_wraps_excel_errors(
    mock_read_excel: Mock,
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "test.xlsx"
    workbook.touch()

    mock_read_excel.side_effect = RuntimeError(
        "boom"
    )

    with pytest.raises(
        WorkbookError,
        match="Failed to read worksheet",
    ):
        read_worksheet(
            workbook,
            WorksheetName.METADATA,
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.schema.validate_sheet_columns"
)
@patch(
    "opstools.inventory_forecast.workbook.reader.pl.read_excel"
)
def test_read_worksheet_wraps_schema_errors(
    mock_read_excel: Mock,
    mock_validate: Mock,
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "test.xlsx"
    workbook.touch()

    mock_read_excel.return_value = pl.DataFrame(
        {"x": [1]}
    )

    mock_validate.side_effect = ValueError(
        "bad schema"
    )

    with pytest.raises(
        WorksheetSchemaError,
        match="failed schema validation",
    ):
        read_worksheet(
            workbook,
            WorksheetName.METADATA,
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.CalamineWorkbook"
)
def test_validate_workbook_completeness_wraps_open_failure(
    mock_calamine: Mock,
    tmp_path: Path,
) -> None:
    mock_calamine.from_path.side_effect = OSError(
        "corrupt"
    )

    with pytest.raises(
        WorkbookError,
        match="Failed to inspect workbook",
    ):
        validate_workbook_completeness(
            tmp_path / "bad.xlsx"
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.read_cache"
)
@patch(
    "opstools.inventory_forecast.workbook.reader.read_metadata"
)
@patch(
    "opstools.inventory_forecast.workbook.reader._validate_workbook_completeness"
)
@patch(
    "opstools.inventory_forecast.workbook.reader._validate_workbook_path"
)
def test_load_dashboard_state(
    mock_read_metadata,
    mock_read_cache,
) -> None:
    metadata = Mock()
    cache = Mock()

    mock_read_metadata.return_value = metadata
    mock_read_cache.return_value = cache

    result = load_dashboard_state(
        Path("dummy.xlsx")
    )

    assert result == (
        metadata,
        cache,
    )


@patch(
    "opstools.inventory_forecast.workbook.reader.read_worksheet"
)
def test_read_metadata_wraps_validation_error(
    mock_read: Mock,
) -> None:
    mock_read.return_value = pl.DataFrame(
        {
            "schema_version": ["1.0.0"],
        }
    )

    with pytest.raises(
        WorksheetMetaDataError,
        match="Metadata validation failed",
    ):
        read_metadata(
            Path("dummy.xlsx")
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.schema.validate_metadata"
)
@patch(
    "opstools.inventory_forecast.workbook.reader.read_worksheet"
)
def test_read_metadata_wraps_schema_validation_error(
    mock_read: Mock,
    mock_validate: Mock,
) -> None:
    mock_read.return_value = pl.DataFrame(
        {
            "schema_version": ["1.0.0"],
            "application_version": ["0.1.0"],
            "generated_at": [datetime.now(UTC)],
            "source_hash": ["a"],
            "output_hash": ["b"],
            "forecast_horizon": [30],
            "total_suppliers": [1],
            "total_items": [1],
            "total_records": [1],
            "processing_time_seconds": [1.0],
        }
    )

    mock_validate.side_effect = ValueError(
        "bad metadata"
    )

    with pytest.raises(
        WorksheetMetaDataError,
        match="Metadata schema validation failed",
    ):
        read_metadata(
            Path("dummy.xlsx")
        )


@patch(
    "opstools.inventory_forecast.workbook.reader.CalamineWorkbook"
)
def test_validate_workbook_completeness_success(
    mock_calamine: Mock,
    tmp_path: Path,
) -> None:
    workbook = Mock()

    workbook.sheet_names = [
        sheet.value
        for sheet in required_sheet_names()
    ]

    mock_calamine.from_path.return_value = workbook

    validate_workbook_completeness(
        tmp_path / "test.xlsx"
    )


@patch(
    "opstools.inventory_forecast.workbook.reader.logger"
)
@patch(
    "opstools.inventory_forecast.workbook.reader.CalamineWorkbook"
)
def test_validate_workbook_completeness_logs_success(
    mock_calamine: Mock,
    mock_logger: Mock,
    tmp_path: Path,
) -> None:
    workbook = Mock()

    workbook.sheet_names = [
        sheet.value
        for sheet in required_sheet_names()
    ]

    mock_calamine.from_path.return_value = workbook

    validate_workbook_completeness(
        tmp_path / "test.xlsx"
    )

    mock_logger.debug.assert_called_once()

