from __future__ import annotations

from datetime import UTC, datetime

import pytest

from opstools.inventory_forecast.domain import (
    WorkbookMeta,
    WorkbookVersionError,
    WorksheetName,
    WorksheetSchemaError,
)
from opstools.inventory_forecast.workbook.schema import (
    WORKBOOK_SHEET_ORDER,
    get_sheet_schema,
    is_known_sheet,
    required_sheet_names,
    validate_metadata,
    validate_sheet_columns,
    validate_workbook_version,
)


@pytest.fixture
def valid_metadata() -> WorkbookMeta:
    return WorkbookMeta(
        schema_version="1.0.0",
        application_version="0.1.0",
        generated_at=datetime.now(UTC),
        source_hash="source_hash",
        output_hash="output_hash",
        forecast_horizon=12,
        total_suppliers=10,
        total_items=100,
        total_records=1000,
        processing_time_seconds=1.5,
    )


# ======================================================================================
# Version Validation
# ======================================================================================


@pytest.mark.parametrize(
    "version",
    [
        "1.0.0",
        "1.0.1",
        "1.1.0",
        "1.999.999",
    ],
)
def test_validate_workbook_version_accepts_supported_versions(
    version: str,
) -> None:
    validate_workbook_version(version)


@pytest.mark.parametrize(
    "version",
    [
        "2.0.0",
        "3.0.0",
        "999.1.1",
    ],
)
def test_validate_workbook_version_rejects_major_version_change(
    version: str,
) -> None:
    with pytest.raises(WorkbookVersionError):
        validate_workbook_version(version)


def test_validate_workbook_version_rejects_invalid_version() -> None:
    with pytest.raises(WorkbookVersionError):
        validate_workbook_version(
            "not-a-valid-version"
        )


# ======================================================================================
# Metadata validation
# ======================================================================================


def test_validate_metadata_accepts_valid_metadata(
    valid_metadata: WorkbookMeta,
) -> None:
    validate_metadata(valid_metadata)


def test_validate_metadata_rejects_zero_forecast_horizon(
    valid_metadata: WorkbookMeta,
) -> None:
    meta = valid_metadata.model_copy(
        update={
            "forecast_horizon": 0,
        }
    )

    with pytest.raises(WorksheetSchemaError):
        validate_metadata(meta)


def test_validate_metadata_rejects_negative_suppliers(
    valid_metadata: WorkbookMeta,
) -> None:
    meta = valid_metadata.model_copy(
        update={
            "total_suppliers": -1,
        }
    )

    with pytest.raises(WorksheetSchemaError):
        validate_metadata(meta)


def test_validate_metadata_rejects_negative_items(
    valid_metadata: WorkbookMeta,
) -> None:
    meta = valid_metadata.model_copy(
        update={
            "total_items": -1,
        }
    )

    with pytest.raises(WorksheetSchemaError):
        validate_metadata(meta)


def test_validate_metadata_rejects_negative_records(
    valid_metadata: WorkbookMeta,
) -> None:
    meta = valid_metadata.model_copy(
        update={
            "total_records": -1,
        }
    )

    with pytest.raises(WorksheetSchemaError):
        validate_metadata(meta)


def test_validate_metadata_rejects_negative_processing_time_seconds(
    valid_metadata: WorkbookMeta,
) -> None:
    meta = valid_metadata.model_copy(
        update={
            "processing_time_seconds": -1.0,
        }
    )

    with pytest.raises(WorksheetSchemaError):
        validate_metadata(meta)


# ======================================================================================
# Column validation
# ======================================================================================


def test_validate_sheet_columns_accepts_metadata_sheet() -> None:
    validate_sheet_columns(
        WorksheetName.METADATA,
        {
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
        },
    )


def test_validate_sheet_columns_rejects_missing_columns() -> None:
    with pytest.raises(WorksheetSchemaError):
        validate_sheet_columns(
            WorksheetName.METADATA,
            {
                "schema_version",
                "application_version",
                "generated_at",
                "forecast_horizon",
                "processing_time_seconds",
            },
        )


def test_validate_sheet_columns_rejects_unexpected_columns() -> None:
    with pytest.raises(WorksheetSchemaError):
        validate_sheet_columns(
            WorksheetName.METADATA,
            {
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
                "bad_column",
            },
        )


def test_validate_sheet_columns_rejects_missing_and_unexpected_columns() -> None:
    with pytest.raises(WorksheetSchemaError):
        validate_sheet_columns(
            WorksheetName.METADATA,
            {
                "schema_version",
                "bad_column",
            },
        )


def test_validate_sheet_columns_rejects_unknown_sheet() -> None:
    with pytest.raises(WorksheetSchemaError):
        validate_sheet_columns(
            "unknown_sheet",  # type: ignore[arg-type]
            set(),
        )


def test_dashboard_cache_accepts_empty_columns() -> None:
    validate_sheet_columns(
        WorksheetName.DASHBOARD_CACHE,
        set(),
    )


# ======================================================================================
# Sheet helpers
# ======================================================================================


def test_required_sheet_names_matches_contract() -> None:
    assert (
        required_sheet_names()
        == WORKBOOK_SHEET_ORDER
    )


def test_is_known_sheet_returns_true_for_enum() -> None:
    assert is_known_sheet(
        WorksheetName.METADATA
    )


def test_is_known_sheet_returns_false_for_unknown_sheet() -> None:
    assert not is_known_sheet(
        "fake_sheet"
    )


def test_is_known_sheet_returns_false_for_sheet_name_string() -> None:
    assert not is_known_sheet(
        "Metadata"
    )


def test_get_sheet_schema_returns_metadata_schema() -> None:
    worksheet_schema = get_sheet_schema(
        WorksheetName.METADATA,
    )

    assert (
        worksheet_schema.name
        == WorksheetName.METADATA
    )

    assert (
        worksheet_schema.required_columns
        == (
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
        )
    )


def test_get_sheet_schema_rejects_unknown_sheet() -> None:
    with pytest.raises(
        WorksheetSchemaError,
    ):
        get_sheet_schema(
            "fake_sheet",  # type: ignore[arg-type]
        )
