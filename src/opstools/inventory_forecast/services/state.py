"""Runtime state management for the analytics pipeline.

Provides strictly-typed state containers that track the configuration
and execution progress of the inventory forecasting engine.
By removing PySide/Observable dependencies, this module ensures
the pipeline can run cleanly in a headless, automated, or CI/CD
environment for the Business Intelligence platform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from opstools.inventory_forecast.domain.models import SourceSet


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Static configuration parameters for a pipeline execution.

    Represents the immutable inputs required to start a run.
    """

    source_set: SourceSet
    output_workbook_path: Path
    forecast_horizon: int
    application_version: str

    def __post_init__(self) -> None:
        """Validate pipeline configuration."""
        if self.forecast_horizon <= 0:
            raise ValueError("forecast_horizon must be greater than zero.")
        if not self.application_version:
            raise ValueError("application_version cannot be empty.")


@dataclass(slots=True)
class PipelineState:
    """Mutable tracker for pipeline execution phases and metrics.

    Collects runtime statistics to feed into the Workbook metadata
    and handles graceful failure tracking without GUI coupling.
    """

    config: PipelineConfig

    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None

    is_ingestion_complete: bool = False
    is_engine_complete: bool = False
    is_workbook_complete: bool = False

    total_suppliers: int = 0
    total_items: int = 0
    total_records: int = 0

    error: Exception | None = None

    @property
    def is_successful(self) -> bool:
        """Determine if all pipeline stages completed without error."""
        return (
            self.is_ingestion_complete
            and self.is_engine_complete
            and self.is_workbook_complete
            and self.error is None
        )

    @property
    def processing_time_seconds(self) -> float:
        """Calculate the elapsed processing time in seconds.

        Returns the duration up to the current moment if still running,
        or the final duration if the pipeline has ended.
        """
        end = self.end_time or datetime.now(UTC)
        return max(0.0, (end - self.start_time).total_seconds())

    def complete_ingestion(self) -> None:
        """Mark the data ingestion and validation phase as complete."""
        self.is_ingestion_complete = True

    def complete_engine(
        self,
        total_suppliers: int,
        total_items: int,
        total_records: int,
    ) -> None:
        """Mark the core analytical engine phase as complete and record metrics.

        Args:
            total_suppliers: Distinct suppliers processed.
            total_items: Distinct SKUs/items processed.
            total_records: Total combined ERP rows processed.
        """
        self.total_suppliers = total_suppliers
        self.total_items = total_items
        self.total_records = total_records
        self.is_engine_complete = True

    def complete_workbook(self) -> None:
        """Mark the workbook persistence phase as complete."""
        self.is_workbook_complete = True
        self.end_time = datetime.now(UTC)

    def fail(self, error: Exception) -> None:
        """Record a terminal pipeline failure.

        Args:
            error: The exception that caused the termination.
        """
        self.error = error
        self.end_time = datetime.now(UTC)
