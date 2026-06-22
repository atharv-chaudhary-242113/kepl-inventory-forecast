from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

from opstools.inventory_forecast.domain import WorkbookMeta, WorksheetName
from opstools.inventory_forecast.workbook.cache import (
    DashboardCache,
)
from opstools.inventory_forecast.workbook.reader import read_metadata
from opstools.inventory_forecast.workbook.writer import (
    _metadata_dataframe,
    _resolve_dataframe,
    _validate_dataset_mapping,
    write_workbook,
)


@pytest.fixture
def metadata() -> WorkbookMeta:
    return WorkbookMeta(
        schema_version="1.0.0",
        application_version="0.1.0",
        generated_at=datetime.now(
            UTC
        ),
        source_hash="a",
        output_hash="b",
        forecast_horizon=30,
        total_suppliers=1,
        total_items=1,
        total_records=1,
        processing_time_seconds=1.0,
    )


def build_dataset_mapping() -> dict:
    from opstools.inventory_forecast.workbook import schema

    datasets = {}

    for sheet in schema.required_sheet_names():
        if sheet in {
            WorksheetName.METADATA,
            WorksheetName.DASHBOARD_CACHE,
        }:
            continue

        columns = (
            schema.get_sheet_schema(sheet)
            .required_columns
        )

        datasets[sheet] = pl.DataFrame(
            {
                column: [None]
                for column in columns
            }
        )

    return datasets


def test_validate_dataset_mapping_success() -> None:
    _validate_dataset_mapping(
        build_dataset_mapping()
    )


def test_validate_dataset_mapping_missing_dataset() -> None:
    datasets = build_dataset_mapping()

    datasets.pop(
        WorksheetName.FORECASTS
    )

    with pytest.raises(
        ValueError,
        match="Missing required datasets",
    ):
        _validate_dataset_mapping(
            datasets
        )


def test_validate_dataset_mapping_unexpected_dataset() -> None:
    datasets = build_dataset_mapping()

    datasets[
        WorksheetName.METADATA
    ] = pl.DataFrame()

    with pytest.raises(
        ValueError,
        match="Unexpected datasets",
    ):
        _validate_dataset_mapping(
            datasets
        )


def test_resolve_dataframe_metadata(
    metadata: WorkbookMeta,
) -> None:
    result = _resolve_dataframe(
        sheet_name=WorksheetName.METADATA,
        meta=metadata,
        cache=DashboardCache(datasets=()),
        datasets={},
    )

    assert result.height == 1


def test_resolve_dataframe_collects_lazyframe(
    metadata: WorkbookMeta,
) -> None:
    lazy = pl.DataFrame(
        {"x": [1]}
    ).lazy()

    result = _resolve_dataframe(
        sheet_name=WorksheetName.FORECASTS,
        meta=metadata,
        cache=DashboardCache(datasets=()),
        datasets={
            WorksheetName.FORECASTS: lazy
        },
    )

    assert isinstance(
        result,
        pl.DataFrame,
    )


def test_metadata_dataframe_removes_timezone(
    metadata: WorkbookMeta,
) -> None:
    dataframe = _metadata_dataframe(
        metadata
    )

    assert (
        dataframe.schema["generated_at"]
        .time_zone
        is None
    )


def test_write_workbook_creates_xlsx(
    tmp_path: Path,
    metadata: WorkbookMeta,
) -> None:
    output = tmp_path / "output.xlsx"

    write_workbook(
        output_path=output,
        meta=metadata,
        cache=DashboardCache(
            datasets=()
        ),
        datasets=build_dataset_mapping(),
    )

    assert output.exists()


def test_write_workbook_removes_temp_file(
    tmp_path: Path,
    metadata: WorkbookMeta,
) -> None:
    output = tmp_path / "output.xlsx"

    write_workbook(
        output_path=output,
        meta=metadata,
        cache=DashboardCache(
            datasets=()
        ),
        datasets=build_dataset_mapping(),
    )

    temp = tmp_path / "output.tmp.xlsx"

    assert not temp.exists()


def test_workbook_round_trip(
    tmp_path: Path,
    metadata: WorkbookMeta,
) -> None:
    output = tmp_path / "roundtrip.xlsx"

    write_workbook(
        output_path=output,
        meta=metadata,
        cache=DashboardCache(
            datasets=()
        ),
        datasets=build_dataset_mapping(),
    )

    loaded = read_metadata(
        output
    )

    assert (
        loaded.schema_version
        == metadata.schema_version
    )


@patch(
    "opstools.inventory_forecast.workbook.writer._resolve_dataframe"
)
def test_write_workbook_cleans_temp_file_on_failure(
    mock_resolve,
    tmp_path,
    metadata,
) -> None:
    mock_resolve.side_effect = RuntimeError(
        "boom"
    )

    output = tmp_path / "out.xlsx"

    with pytest.raises(RuntimeError):
        write_workbook(
            output_path=output,
            meta=metadata,
            cache=DashboardCache(
                datasets=()
            ),
            datasets=build_dataset_mapping(),
        )

    temp_file = (
        tmp_path / "out.tmp.xlsx"
    )

    assert not temp_file.exists()


@patch(
    "pathlib.Path.unlink"
)
@patch(
    "opstools.inventory_forecast.workbook.writer._resolve_dataframe"
)
def test_write_workbook_ignores_temp_cleanup_failure(
    mock_resolve,
    mock_unlink,
    tmp_path: Path,
    metadata: WorkbookMeta,
) -> None:
    mock_resolve.side_effect = RuntimeError(
        "boom"
    )

    mock_unlink.side_effect = OSError(
        "cannot delete"
    )

    output = tmp_path / "out.xlsx"

    with pytest.raises(RuntimeError):
        write_workbook(
            output_path=output,
            meta=metadata,
            cache=DashboardCache(
                datasets=()
            ),
            datasets=build_dataset_mapping(),
        )

