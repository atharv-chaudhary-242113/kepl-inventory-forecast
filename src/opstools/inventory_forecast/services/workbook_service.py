"""Workbook application service.

Provides a stable service boundary around workbook
reader/writer/cache infrastructure.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import polars as pl

from opstools.inventory_forecast.domain import WorkbookMeta, WorksheetName
from opstools.inventory_forecast.services.state import (
    DashboardState,
    build_dashboard_state,
)
from opstools.inventory_forecast.workbook.cache import DashboardCache
from opstools.inventory_forecast.workbook.reader import (
    load_dashboard_state as reader_load_dashboard_state,
)
from opstools.inventory_forecast.workbook.writer import (
    write_workbook,
)


class WorkbookService:
    """Workbook persistence façade."""

    @staticmethod
    def save_workbook(
        *,
        output_path: Path,
        metadata: WorkbookMeta,
        cache: DashboardCache,
        datasets: Mapping[
            WorksheetName,
            pl.DataFrame | pl.LazyFrame,
        ],
    ) -> None:
        """Save workbook to disk."""
        write_workbook(
            output_path=output_path,
            meta=metadata,
            cache=cache,
            datasets=datasets,
        )

    @staticmethod
    def load_dashboard_state(
        path: Path,
    ) -> DashboardState:
        """Load dashboard state from file."""
        metadata, cache = reader_load_dashboard_state(
            path,
        )

        return build_dashboard_state(
            metadata,
            cache,
        )
