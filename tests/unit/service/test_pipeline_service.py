"""Tests for the Phase-5 application service layer."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
from polars.lazyframe.frame import LazyFrame

from opstools.inventory_forecast.config import (
    Settings,
)
from opstools.inventory_forecast.domain import WorkbookMeta
from opstools.inventory_forecast.domain.models import WorkbookMeta
from opstools.inventory_forecast.engine import (
    EngineOutput,
)
from opstools.inventory_forecast.services.pipeline_service import (
    # pyrefly: ignore [missing-module-attribute]
    PipelineResult,
    # pyrefly: ignore [missing-module-attribute]
    PipelineService,
    # pyrefly: ignore [missing-module-attribute]
    build_workbook_metadata,
)
from opstools.inventory_forecast.services.state import (
    # pyrefly: ignore [missing-module-attribute]
    PipelineProgress,
    # pyrefly: ignore [missing-module-attribute]
    PipelineRequest,
    # pyrefly: ignore [missing-module-attribute]
    PipelineStage,
)
from opstools.inventory_forecast.workbook.cache import (
    # pyrefly: ignore [missing-module-attribute]
    DashboardCache,
)


def test_emit_progress_no_callback_is_noop() -> None:
    """emit_progress should safely do nothing when no callback exists."""
    PipelineService.emit_progress(
        None,
        stage=PipelineStage.COMPLETE,
        percent_complete=100,
        message="done",
    )


def test_emit_progress_dispatches_snapshot() -> None:
    """emit_progress forwards a PipelineProgress snapshot."""
    received: list[PipelineProgress] = []

    PipelineService.emit_progress(
        received.append,
        stage=PipelineStage.READING_FILES,
        percent_complete=25,
        message="reading",
    )

    assert len(received) == 1

    progress = received[0]

    assert progress.stage == PipelineStage.READING_FILES
    assert progress.percent_complete == 25
    assert progress.message == "reading"


def test_build_cache_contains_expected_datasets() -> None:
    """Dashboard cache should expose all dashboard datasets."""

    frame = pl.DataFrame({"value": [1]})

    output = EngineOutput(
        demand_history=frame,
        forecasts=frame,
        supplier_analysis=frame,
        supplier_partnerships=frame,
        lead_time_analysis=frame,
        pending_deliveries=frame,
        financial_summary=frame,
        abc_classification=frame,
        sbc_classification=frame,
        inventory_valuation=frame,
        reorder_recommendations=frame,
        price_variance=frame,
        sourcing_risk=frame,
        fill_rate=frame,
        inventory_health=frame,
    )

    cache = PipelineService.build_cache(output)

    assert cache.contains("supplier_analysis")
    assert cache.contains("inventory_health")
    assert cache.contains("fill_rate")
    assert cache.contains("sourcing_risk")
    assert cache.contains("reorder_recommendations")
    assert cache.contains("price_variance")


def test_export_workbook_returns_pipeline_result(
    # pyrefly: ignore [implicit-any-parameter]
    monkeypatch,
    tmp_path: Path,
) -> None:
    """export_workbook should return a populated PipelineResult."""

    frame = pl.DataFrame({"value": [1]})

    output = EngineOutput(
        demand_history=frame,
        forecasts=frame,
        supplier_analysis=frame,
        supplier_partnerships=frame,
        lead_time_analysis=frame,
        pending_deliveries=frame,
        financial_summary=frame,
        abc_classification=frame,
        sbc_classification=frame,
        inventory_valuation=frame,
        reorder_recommendations=frame,
        price_variance=frame,
        sourcing_risk=frame,
        fill_rate=frame,
        inventory_health=frame,
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

    # pyrefly: ignore [implicit-any-parameter]
    def _save_workbook(**kwargs) -> None:
        return None

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.workbook_service."
        "WorkbookService.save_workbook",
        _save_workbook,
    )

    result = PipelineService.export_workbook(
        output_path=tmp_path / "out.xlsx",
        metadata=metadata,
        engine_output=output,
    )

    assert result.engine_output is output
    assert result.metadata is metadata
    assert isinstance(
        result.cache,
        DashboardCache,
    )


def test_build_workbook_metadata_handles_missing_supplier_column() -> None:
    """Supplier count should be zero when supplier column is absent."""

    frame = pl.DataFrame({"value": [1]})

    output = EngineOutput(
        demand_history=frame,
        forecasts=frame,
        supplier_analysis=frame,
        supplier_partnerships=frame,
        lead_time_analysis=frame,
        pending_deliveries=frame,
        financial_summary=frame,
        abc_classification=frame,
        sbc_classification=frame,
        inventory_valuation=frame,
        reorder_recommendations=frame,
        price_variance=frame,
        sourcing_risk=frame,
        fill_rate=frame,
        inventory_health=frame,
    )

    metadata = build_workbook_metadata(
        engine_output=output,
        settings=Settings(),
        processing_time_seconds=1.0,
    )

    assert metadata.total_suppliers == 0


def test_build_workbook_metadata_handles_missing_item_column() -> None:
    """Item count should be zero when item column is absent."""

    demand_history = pl.DataFrame({"value": [1]})

    supplier_analysis = pl.DataFrame({"supplier": ["A"]})

    frame = pl.DataFrame({"value": [1]})

    output = EngineOutput(
        demand_history=demand_history,
        forecasts=frame,
        supplier_analysis=supplier_analysis,
        supplier_partnerships=frame,
        lead_time_analysis=frame,
        pending_deliveries=frame,
        financial_summary=frame,
        abc_classification=frame,
        sbc_classification=frame,
        inventory_valuation=frame,
        reorder_recommendations=frame,
        price_variance=frame,
        sourcing_risk=frame,
        fill_rate=frame,
        inventory_health=frame,
    )

    metadata = build_workbook_metadata(
        engine_output=output,
        settings=Settings(),
        processing_time_seconds=1.0,
    )

    assert metadata.total_items == 0


def test_run_pipeline_success_path(
    # pyrefly: ignore [implicit-any-parameter]
    monkeypatch,
    tmp_path: Path,
) -> None:
    """run_pipeline should execute the complete happy path."""

    frame = pl.DataFrame({"value": [1]})

    engine_output = EngineOutput(
        demand_history=frame,
        forecasts=frame,
        supplier_analysis=frame,
        supplier_partnerships=frame,
        lead_time_analysis=frame,
        pending_deliveries=frame,
        financial_summary=frame,
        abc_classification=frame,
        sbc_classification=frame,
        inventory_valuation=frame,
        reorder_recommendations=frame,
        price_variance=frame,
        sourcing_risk=frame,
        fill_rate=frame,
        inventory_health=frame,
    )

    metadata = WorkbookMeta(
        schema_version="1.0.0",
        application_version="test",
        generated_at=datetime.now(UTC),
        forecast_horizon=12,
        total_suppliers=1,
        total_items=1,
        total_records=10,
        processing_time_seconds=1.0,
    )

    cache = DashboardCache(
        datasets=(),
    )

    result = PipelineResult(
        engine_output=engine_output,
        metadata=metadata,
        cache=cache,
    )

    def _read_source(_path, _kind) -> LazyFrame:
        return frame.lazy()

    def _run_engine(**_kwargs):
        return engine_output

    def _build_metadata(**_kwargs) -> WorkbookMeta:
        return metadata

    def _export_workbook(**_kwargs):
        return result

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.read_source",
        _read_source,
    )

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.run_engine",
        _run_engine,
    )

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.build_workbook_metadata",
        _build_metadata,
    )

    monkeypatch.setattr(
        PipelineService,
        "export_workbook",
        staticmethod(_export_workbook),
    )

    # pyrefly: ignore [implicit-any-type-argument]
    progress_events: list = []

    request = PipelineRequest(
        pov_path=tmp_path / "pov.xlsx",
        grn_path=tmp_path / "grn.xlsx",
        pv_path=tmp_path / "pv.xlsx",
        closing_stock_path=tmp_path / "closing.xlsx",
        output_path=tmp_path / "out.xlsx",
        snapshot_date=date(
            2025,
            1,
            1,
        ),
    )

    actual = PipelineService.run_pipeline(
        request,
        settings=Settings(),
        progress_callback=progress_events.append,
    )

    assert actual is result

    stages = [event.stage.value for event in progress_events]

    assert stages == [
        "validating_inputs",
        "reading_files",
        "running_engine",
        "building_cache",
        "writing_workbook",
        "complete",
    ]
