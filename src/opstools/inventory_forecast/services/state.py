"""Application state models.

Phase-5 service layer state contracts.

The UI should consume DashboardState rather than interacting
with workbook.cache directly.
"""

from __future__ import annotations

from dataclasses import dataclass

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
