"""Application state models.

Phase-5 service layer state contracts.

The UI should consume DashboardState rather than interacting
with workbook.cache directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from opstools.inventory_forecast.domain import WorkbookMeta
from opstools.inventory_forecast.workbook.cache import DashboardCache


@dataclass(frozen=True, slots=True)
class DashboardState:
    """Fully materialized dashboard state."""
    metadata: WorkbookMeta
    cache: DashboardCache

    def contains_dataset(
        self,
        name: str,
    ) -> bool:
        """Check if a dataset is in cache."""
        return self.cache.contains(name)

    @property
    def dataset_names(
        self,
    ) -> tuple[str, ...]:
        """Get the names of all datasets in cache."""
        return self.cache.names


def build_dashboard_state(
    metadata: WorkbookMeta,
    cache: DashboardCache,
) -> DashboardState:
    """Construct validated dashboard state."""
    return DashboardState(
        metadata=metadata,
        cache=cache,
    )


class PipelineStage(StrEnum):
    """Execution stages emitted by the Phase-5 pipeline service.

    These values form the stable progress contract consumed by
    the UI layer. Stages represent high-level workflow transitions
    rather than implementation details, allowing the underlying
    pipeline to evolve without breaking progress reporting.
    """

    VALIDATING_INPUTS = "validating_inputs"
    READING_FILES = "reading_files"
    RUNNING_ENGINE = "running_engine"
    BUILDING_CACHE = "building_cache"
    WRITING_WORKBOOK = "writing_workbook"
    LOADING_WORKBOOK = "loading_workbook"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class PipelineProgress:
    """Immutable snapshot of pipeline execution progress.

    Instances are emitted through the progress callback during
    long-running operations. The UI should treat each instance
    as a complete state update rather than accumulating deltas.
    """

    stage: PipelineStage
    """Current high-level pipeline stage."""

    percent_complete: int
    """Progress percentage in the range [0, 100]."""

    message: str
    """Human-readable status message suitable for display."""


@dataclass(frozen=True, slots=True)
class PipelineRequest:
    """Input contract for a complete inventory forecast run.

    Encapsulates all file-system inputs and runtime parameters
    required to execute the ingestion, engine, workbook, and
    dashboard-cache pipeline.
    """

    pov_path: Path
    """Path to the Purchase Order Voucher export."""

    grn_path: Path
    """Path to the Goods Received Note export."""

    pv_path: Path
    """Path to the Purchase Voucher export."""

    closing_stock_path: Path
    """Path to the Closing Stock export."""

    output_path: Path
    """Destination workbook path."""

    snapshot_date: date
    """Explicit valuation date used by engine calculations."""
