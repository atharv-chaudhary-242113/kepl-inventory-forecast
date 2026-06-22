"""Tests for workbook service façade."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl

from opstools.inventory_forecast.domain import (
    WorkbookMeta,
    WorksheetName,
)
from opstools.inventory_forecast.services.workbook_service import (
    WorkbookService,
)
from opstools.inventory_forecast.workbook.cache import (
    DashboardCache,
)


def test_save_workbook_delegates_to_writer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """save_workbook should delegate to write_workbook."""
    captured: dict[str, object] = {}

    def _write_workbook(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.workbook_service.write_workbook",
        _write_workbook,
    )

    metadata = WorkbookMeta(
        schema_version="1.0.0",
        application_version="0.1.0",
        generated_at=datetime.now(UTC),
        forecast_horizon=12,
        total_suppliers=1,
        total_items=1,
        total_records=1,
        processing_time_seconds=1.0,
    )

    cache = DashboardCache(
        datasets=(),
    )

    datasets = {
        WorksheetName.DEMAND_HISTORY: pl.DataFrame({"value": [1]}),
    }

    output_path = tmp_path / "forecast.xlsx"

    WorkbookService.save_workbook(
        output_path=output_path,
        metadata=metadata,
        cache=cache,
        datasets=datasets,
    )

    assert captured["output_path"] == output_path
    assert captured["meta"] is metadata
    assert captured["cache"] is cache
    assert captured["datasets"] is datasets


def test_validate_workbook_delegates_to_validator(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """validate_workbook should delegate to workbook validation."""
    validator = MagicMock()

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.workbook_service."
        "validate_workbook_completeness",
        validator,
    )

    workbook = tmp_path / "forecast.xlsx"

    WorkbookService.validate_workbook(
        workbook,
    )

    validator.assert_called_once_with(
        workbook,
    )


def test_load_dashboard_state_validates_before_loading(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """load_dashboard_state should validate before materialization."""
    call_order: list[str] = []

    def _validate(path: Path) -> None:
        call_order.append("validate")

    def _reader(path: Path):
        call_order.append("reader")
        return "metadata", "cache"

    def _builder(metadata, cache):
        call_order.append("builder")
        return {
            "metadata": metadata,
            "cache": cache,
        }

    monkeypatch.setattr(
        WorkbookService,
        "validate_workbook",
        _validate,
    )

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.workbook_service."
        "reader_load_dashboard_state",
        _reader,
    )

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.workbook_service.build_dashboard_state",
        _builder,
    )

    workbook = tmp_path / "forecast.xlsx"

    result = WorkbookService.load_dashboard_state(
        workbook,
    )

    assert call_order == [
        "validate",
        "reader",
        "builder",
    ]

    assert result == {
        "metadata": "metadata",
        "cache": "cache",
    }
