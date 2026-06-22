"""Primary application service.

This is the public entry point consumed by the UI.

The UI should not import engine, workbook, or ingestion
modules directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import (
    PackageNotFoundError,
    version,
)
from pathlib import Path
from time import perf_counter

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.domain import (
    SourceKind,
    WorkbookMeta,
    WorksheetName,
)
from opstools.inventory_forecast.engine import (
    EngineOutput,
)
from opstools.inventory_forecast.engine.orchestrator import (
    run_engine,
)
from opstools.inventory_forecast.ingestion import (
    read_source,
)
from opstools.inventory_forecast.services import (
    DashboardState,
    PipelineProgress,
    PipelineStage,
)
from opstools.inventory_forecast.services.state import (
    PipelineRequest,
)
from opstools.inventory_forecast.services.workbook_service import (
    WorkbookService,
)
from opstools.inventory_forecast.workbook.cache import (
    DashboardCache,
    build_dashboard_cache,
)
from opstools.inventory_forecast.workbook.schema import (
    WORKBOOK_SCHEMA_VERSION,
)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Result of a completed pipeline run."""

    engine_output: EngineOutput

    metadata: WorkbookMeta

    cache: DashboardCache


def build_workbook_metadata(
    *,
    engine_output: EngineOutput,
    settings: Settings,
    processing_time_seconds: float,
) -> WorkbookMeta:
    """Construct workbook metadata for a completed pipeline run.

    The metadata sheet records provenance information and high-level
    execution statistics for reproducibility and workbook validation.

    Statistics are derived from the fully materialized EngineOutput
    returned by the engine orchestrator.

    Args:
        engine_output:
            Materialized engine output.

        settings:
            Runtime settings used during execution.

        processing_time_seconds:
            End-to-end pipeline runtime.

    Returns:
        Validated workbook metadata.
    """
    supplier_count = (
        engine_output.supplier_analysis.get_column("supplier").n_unique()
        if (
            not engine_output.supplier_analysis.is_empty()
            and "supplier" in engine_output.supplier_analysis.columns
        )
        else 0
    )

    item_count = (
        engine_output.demand_history.get_column("item").n_unique()
        if (
            not engine_output.demand_history.is_empty()
            and "item" in engine_output.demand_history.columns
        )
        else 0
    )

    total_records = sum(
        frame.height
        for frame in (
            engine_output.demand_history,
            engine_output.forecasts,
            engine_output.supplier_analysis,
            engine_output.supplier_partnerships,
            engine_output.lead_time_analysis,
            engine_output.pending_deliveries,
            engine_output.financial_summary,
            engine_output.abc_classification,
            engine_output.sbc_classification,
            engine_output.inventory_valuation,
        )
    )

    try:
        application_version = version(
            "opstools.inventory_forecast",
        )
    except PackageNotFoundError:
        application_version = "development"

    return WorkbookMeta(
        schema_version=str(
            WORKBOOK_SCHEMA_VERSION,
        ),
        application_version=application_version,
        generated_at=datetime.now(
            UTC,
        ),
        forecast_horizon=settings.forecast_horizon,
        total_suppliers=supplier_count,
        total_items=item_count,
        total_records=total_records,
        processing_time_seconds=processing_time_seconds,
    )


class PipelineService:
    """Application orchestration façade."""

    @staticmethod
    def emit_progress(
        callback: Callable[[PipelineProgress], None] | None,
        *,
        stage: PipelineStage,
        percent_complete: int,
        message: str,
    ) -> None:
        """Emit a pipeline progress update.

        Centralizes callback dispatch for all pipeline stages so
        progress reporting remains consistent throughout build
        and reuse workflows.

        Args:
            callback:
                Optional progress callback supplied by the UI.
            stage:
                Current pipeline execution stage.
            percent_complete:
                Progress percentage in the range [0, 100].
            message:
                Human-readable status message.
        """
        if callback is None:
            return

        callback(
            PipelineProgress(
                stage=stage,
                percent_complete=percent_complete,
                message=message,
            )
        )

    @staticmethod
    def build_cache(
        output: EngineOutput,
    ) -> DashboardCache:
        """Build the dashboard cache."""
        return build_dashboard_cache(
            supplier_analysis=output.supplier_analysis,
            inventory_health=output.inventory_health,
            fill_rate=output.fill_rate,
            sourcing_risk=output.sourcing_risk,
            reorder_recommendations=output.reorder_recommendations,
            price_variance=output.price_variance,
        )

    @staticmethod
    def export_workbook(
        *,
        output_path: Path,
        metadata: WorkbookMeta,
        engine_output: EngineOutput,
    ) -> PipelineResult:
        """Export the workbook state to the output path."""
        cache = PipelineService.build_cache(engine_output)

        WorkbookService.save_workbook(
            output_path=output_path,
            metadata=metadata,
            cache=cache,
            datasets={
                WorksheetName.DEMAND_HISTORY: engine_output.demand_history,
                WorksheetName.FORECASTS: engine_output.forecasts,
                WorksheetName.SUPPLIER_ANALYSIS: engine_output.supplier_analysis,
                WorksheetName.SUPPLIER_PARTNERSHIPS: engine_output.supplier_partnerships,  # noqa: E501
                WorksheetName.LEAD_TIME_ANALYSIS: engine_output.lead_time_analysis,
                WorksheetName.PENDING_DELIVERIES: engine_output.pending_deliveries,
                WorksheetName.FINANCIAL_SUMMARY: engine_output.financial_summary,
                WorksheetName.ABC_CLASSIFICATION: engine_output.abc_classification,
                WorksheetName.SBC_CLASSIFICATION: engine_output.sbc_classification,
                WorksheetName.INVENTORY_VALUATION: engine_output.inventory_valuation,
            },
        )

        return PipelineResult(
            engine_output=engine_output,
            metadata=metadata,
            cache=cache,
        )

    @staticmethod
    def load_dashboard(
        workbook_path: Path,
    ) -> DashboardState:
        """Load the dashboard state from the workbook."""
        return WorkbookService.load_dashboard_state(
            workbook_path,
        )

    @staticmethod
    def load_existing_workbook(
        workbook_path: Path,
        *,
        progress_callback: Callable[
            [PipelineProgress],
            None,
        ]
        | None = None,
    ) -> DashboardState:
        """Load dashboard state from an existing workbook.

        This method represents the Phase-5 reuse path. No
        ingestion, forecasting, analytics generation, or workbook
        writing is performed. The persisted workbook state is
        validated and materialized directly.

        Args:
            workbook_path:
                Existing workbook path.
            progress_callback:
                Optional callback receiving progress updates.

        Returns:
            Fully materialized dashboard state.
        """
        PipelineService.emit_progress(
            progress_callback,
            stage=PipelineStage.LOADING_WORKBOOK,
            percent_complete=0,
            message="Loading workbook.",
        )

        state = WorkbookService.load_dashboard_state(
            workbook_path,
        )

        PipelineService.emit_progress(
            progress_callback,
            stage=PipelineStage.COMPLETE,
            percent_complete=100,
            message="Workbook loaded successfully.",
        )

        return state

    @staticmethod
    def run_pipeline(
        request: PipelineRequest,
        *,
        settings: Settings,
        progress_callback: Callable[
            [PipelineProgress],
            None,
        ]
        | None = None,
    ) -> PipelineResult:
        """Execute a complete inventory forecast pipeline.

        Pipeline flow:

            Input Files
                ->
            Ingestion
                ->
            Engine DAG
                ->
            Dashboard Cache
                ->
            Workbook Export

        Args:
            request:
                Runtime pipeline request.
            settings:
                Immutable application settings.
            progress_callback:
                Optional UI progress callback.

        Returns:
            Completed pipeline result.
        """
        started_at = perf_counter()

        PipelineService.emit_progress(
            progress_callback,
            stage=PipelineStage.VALIDATING_INPUTS,
            percent_complete=0,
            message="Validating inputs.",
        )

        PipelineService.emit_progress(
            progress_callback,
            stage=PipelineStage.READING_FILES,
            percent_complete=10,
            message="Reading source files.",
        )

        pov = read_source(
            request.pov_path,
            SourceKind.POV,
        )

        grn = read_source(
            request.grn_path,
            SourceKind.GRN,
        )

        pv = read_source(
            request.pv_path,
            SourceKind.PV,
        )

        closing_stock = read_source(
            request.closing_stock_path,
            SourceKind.CLOSING_STOCK,
        )

        PipelineService.emit_progress(
            progress_callback,
            stage=PipelineStage.RUNNING_ENGINE,
            percent_complete=40,
            message="Running forecasting engine.",
        )

        engine_output = run_engine(
            pov=pov,
            grn=grn,
            pv=pv,
            closing=closing_stock,
            cfg=settings,
            snapshot_date=request.snapshot_date,
        )

        PipelineService.emit_progress(
            progress_callback,
            stage=PipelineStage.BUILDING_CACHE,
            percent_complete=80,
            message="Building dashboard cache.",
        )

        elapsed = perf_counter() - started_at

        metadata = build_workbook_metadata(
            engine_output=engine_output,
            settings=settings,
            processing_time_seconds=elapsed,
        )

        PipelineService.emit_progress(
            progress_callback,
            stage=PipelineStage.WRITING_WORKBOOK,
            percent_complete=90,
            message="Writing workbook.",
        )

        result = PipelineService.export_workbook(
            output_path=request.output_path,
            metadata=metadata,
            engine_output=engine_output,
        )

        PipelineService.emit_progress(
            progress_callback,
            stage=PipelineStage.COMPLETE,
            percent_complete=100,
            message="Pipeline completed successfully.",
        )

        return result
