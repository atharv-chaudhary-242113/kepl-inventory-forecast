"""Dashboard data builders.

Transforms pre-computed visualization data from the orchestration
layer into the presentation-ready Dashboard Data worksheet.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from opstools.inventory_forecast.domain.models import DashboardPanelData
from opstools.inventory_forecast.workbook.schema import (
    WorksheetName,
    get_sheet_schema,
)


def build_dashboard_data_df(panels: Sequence[DashboardPanelData]) -> pl.DataFrame:
    """Build the Dashboard Data DataFrame for the workbook.

    This pre-calculated data powers downstream Plotly dashboards
    without requiring further in-memory aggregation.

    Args:
        panels: Sequence of pre-calculated dashboard visualization points.

    Returns:
        A Polars DataFrame conforming to the Dashboard Data worksheet schema.
    """
    schema = get_sheet_schema(WorksheetName.DASHBOARD_DATA)

    df_schema = {
        "panel_id": pl.Utf8,
        "dimension": pl.Utf8,
        "metric": pl.Utf8,
        "value": pl.Float64,
        "percentage": pl.Float64,
    }

    if not panels:
        return pl.DataFrame(schema=df_schema).select(list(schema.required_columns))

    df = pl.DataFrame(
        [
            {
                "panel_id": p.panel_id,
                "dimension": p.dimension,
                "metric": p.metric,
                "value": float(p.value),
                "percentage": float(p.percentage),
            }
            for p in panels
        ],
        schema=df_schema,
    )

    return df.select(list(schema.required_columns))
