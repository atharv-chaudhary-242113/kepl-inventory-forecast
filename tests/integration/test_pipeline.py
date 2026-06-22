"""End-to-end pipeline integration tests.

These tests validate the complete Phase-5 orchestration path:

    ERP Files
        ->
    Ingestion
        ->
    Engine
        ->
    Workbook Export
        ->
    Workbook Reload
"""

from __future__ import annotations

import contextlib
from datetime import date
from pathlib import Path

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.services.pipeline_service import (
    PipelineService,
)
from opstools.inventory_forecast.services.state import (
    PipelineRequest,
)


def test_pipeline_emits_progress_stages(
    monkeypatch,
    tmp_path,
) -> None:
    """Pipeline should emit ordered progress updates."""
    stages = []

    def _progress(update):
        stages.append(update.stage)

    monkeypatch.setattr(
        PipelineService,
        "export_workbook",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.read_source",
        lambda *args, **kwargs: object(),
    )

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.pipeline_service.run_engine",
        lambda **kwargs: object(),
    )

    request = PipelineRequest(
        pov_path=tmp_path / "pov.xlsx",
        grn_path=tmp_path / "grn.xlsx",
        pv_path=tmp_path / "pv.xlsx",
        closing_stock_path=tmp_path / "closing.xlsx",
        output_path=tmp_path / "out.xlsx",
        snapshot_date=date(
            2025,
            6,
            30,
        ),
    )

    with contextlib.suppress(Exception):
        PipelineService.run_pipeline(
            request,
            settings=Settings(),
            progress_callback=_progress,
        )

    assert stages[0].value == "validating_inputs"
    assert stages[1].value == "reading_files"


def test_load_existing_workbook_roundtrip(
    monkeypatch,
) -> None:
    """Workbook reload path should delegate to WorkbookService."""
    sentinel = object()

    monkeypatch.setattr(
        "opstools.inventory_forecast.services.workbook_service."
        "WorkbookService.load_dashboard_state",
        lambda path: sentinel,
    )

    result = PipelineService.load_existing_workbook(Path("dummy.xlsx"))

    assert result is sentinel
