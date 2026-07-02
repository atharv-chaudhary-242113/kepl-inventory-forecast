"""Tests for the Phase-5 application service layer."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from opstools.inventory_forecast.domain.enums import SourceKind
from opstools.inventory_forecast.services.pipeline_service import (
    execute_pipeline,
)
from opstools.inventory_forecast.services.state import (
    PipelineConfig,
    PipelineState,
)


class MockSourceSet:
    """Mock source set to bypass actual file system interactions."""
    def iter_with_kind(self) -> list[tuple[Path, SourceKind]]:
        return []


@pytest.fixture
def dummy_state(tmp_path: Path) -> PipelineState:
    """Provide a clean pipeline state for testing."""
    config = PipelineConfig(
        source_set=MockSourceSet(),  # type: ignore[arg-type]
        output_workbook_path=tmp_path / "output.xlsx",
        forecast_horizon=12,
        application_version="1.0.0",
    )
    return PipelineState(config=config)


def test_execute_pipeline_success_path(
    monkeypatch: pytest.MonkeyPatch,
    dummy_state: PipelineState,
) -> None:
    """Pipeline should orchestrate ingestion, engine, and persistence."""

    def mock_ingest_data(_state: PipelineState) -> dict[SourceKind, pl.DataFrame]:
        return {
            SourceKind.POV: pl.DataFrame({"supplier_id": ["S1", "S2"]}),
            SourceKind.GRN: pl.DataFrame({"val": [1]}),
            SourceKind.PV: pl.DataFrame({"val": [1]}),
            SourceKind.CLOSING_STOCK: pl.DataFrame({"item_id": ["I1", "I2", "I3"]}),
        }

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service._ingest_data",
        mock_ingest_data,
    )

    def mock_run_engine(*args: object, **kwargs: object) -> dict[str, object]:
        return {"summary_data": True}

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.run_analytics_engine",
        mock_run_engine,
    )

    written_meta = None

    def mock_write_workbook(
        path: Path,
        meta: object,
        summary: object,
        **kwargs: object,
    ) -> None:
        nonlocal written_meta
        written_meta = meta

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.write_workbook",
        mock_write_workbook,
    )

    execute_pipeline(dummy_state)

    # State updates
    assert dummy_state.is_ingestion_complete is True
    assert dummy_state.is_engine_complete is True
    assert dummy_state.is_workbook_complete is True
    assert dummy_state.is_successful is True

    # Metric calculations (based on mock dataframe rows and unique IDs)
    assert dummy_state.total_suppliers == 2
    assert dummy_state.total_items == 3
    assert dummy_state.total_records == 7

    assert written_meta is not None


def test_execute_pipeline_handles_missing_columns_for_metrics(
    monkeypatch: pytest.MonkeyPatch,
    dummy_state: PipelineState,
) -> None:
    """Pipeline should default to 0 for missing supplier or item columns."""

    def mock_ingest_data(_state: PipelineState) -> dict[SourceKind, pl.DataFrame]:
        return {
            SourceKind.POV: pl.DataFrame({"other_col": [1]}),
            SourceKind.GRN: pl.DataFrame({"other_col": [1]}),
            SourceKind.PV: pl.DataFrame({"other_col": [1]}),
            SourceKind.CLOSING_STOCK: pl.DataFrame({"other_col": [1]}),
        }

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service._ingest_data",
        mock_ingest_data,
    )

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.run_analytics_engine",
        lambda *args, **kwargs: {},
    )

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.write_workbook",
        lambda *args, **kwargs: None,
    )

    execute_pipeline(dummy_state)

    assert dummy_state.total_suppliers == 0
    assert dummy_state.total_items == 0
    assert dummy_state.total_records == 4


def test_execute_pipeline_records_failures_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
    dummy_state: PipelineState,
) -> None:
    """Pipeline should capture exceptions in state and re-raise them."""
    expected_error = RuntimeError("Engine failure")

    def mock_ingest_data(_state: PipelineState) -> dict[SourceKind, pl.DataFrame]:
        return {
            SourceKind.POV: pl.DataFrame(),
            SourceKind.GRN: pl.DataFrame(),
            SourceKind.PV: pl.DataFrame(),
            SourceKind.CLOSING_STOCK: pl.DataFrame(),
        }

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service._ingest_data",
        mock_ingest_data,
    )

    def mock_run_engine(*args: object, **kwargs: object) -> None:
        raise expected_error

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.run_analytics_engine",
        mock_run_engine,
    )

    with pytest.raises(RuntimeError, match="Engine failure"):
        execute_pipeline(dummy_state)

    assert dummy_state.is_successful is False
    assert dummy_state.error is expected_error
    assert dummy_state.is_ingestion_complete is True
    assert dummy_state.is_engine_complete is False
    assert dummy_state.is_workbook_complete is False
