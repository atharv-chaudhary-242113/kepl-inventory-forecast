"""Primary application service.

This is the public entry point consumed by the UI.

The UI should not import engine, workbook, or ingestion
modules directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from opstools.inventory_forecast.domain import (
    WorkbookMeta,
    WorksheetName,
)
from opstools.inventory_forecast.engine import (
    EngineOutput,
)
from opstools.inventory_forecast.services import (
    DashboardState,
    PipelineProgress,
    PipelineStage,
)
from opstools.inventory_forecast.services.workbook_service import (
    WorkbookService,
)
from opstools.inventory_forecast.workbook.cache import (
    DashboardCache,
    build_dashboard_cache,
)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Result of a completed pipeline run."""

    engine_output: EngineOutput

    metadata: WorkbookMeta

    cache: DashboardCache


class PipelineService:
    """Application orchestration façade."""

    @staticmethod
    def emit_progress(
        callback: Callable[[PipelineProgress], None]
        | None,
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
            reorder_recommendations=(
                output.reorder_recommendations
            ),
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
        cache = PipelineService.build_cache(
            engine_output
        )

        WorkbookService.save_workbook(
            output_path=output_path,
            metadata=metadata,
            cache=cache,
            datasets={
                WorksheetName.DEMAND_HISTORY:
                    engine_output.demand_history,
                WorksheetName.FORECASTS:
                    engine_output.forecasts,
                WorksheetName.SUPPLIER_ANALYSIS:
                    engine_output.supplier_analysis,
                WorksheetName.SUPPLIER_PARTNERSHIPS:
                    engine_output.supplier_partnerships,
                WorksheetName.LEAD_TIME_ANALYSIS:
                    engine_output.lead_time_analysis,
                WorksheetName.PENDING_DELIVERIES:
                    engine_output.pending_deliveries,
                WorksheetName.FINANCIAL_SUMMARY:
                    engine_output.financial_summary,
                WorksheetName.ABC_CLASSIFICATION:
                    engine_output.abc_classification,
                WorksheetName.SBC_CLASSIFICATION:
                    engine_output.sbc_classification,
                WorksheetName.INVENTORY_VALUATION:
                    engine_output.inventory_valuation,
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
