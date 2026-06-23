"""Package entry point.

Allows execution via:

    python -m opstools.inventory_forecast

This module intentionally contains no business logic.
"""

from __future__ import annotations

from pathlib import Path

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.services.pipeline_service import (
    PipelineService,
)
from opstools.inventory_forecast.services.state import (
    PipelineRequest,
)


def main() -> int:
    """Execute a pipeline run from the command line.

    This entry point is intentionally minimal and exists
    primarily for local execution and smoke testing.
    """
    print(
        "KEPL Inventory Forecast"
    )

    print(
        "Use the dedicated UI or service layer "
        "for production execution."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
