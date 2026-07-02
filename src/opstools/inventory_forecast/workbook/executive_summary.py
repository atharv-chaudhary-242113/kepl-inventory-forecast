"""Executive summary and procurement insights builders.

Transforms orchestration outputs into the presentation-ready
Executive Summary and Procurement Insights worksheets.
"""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from opstools.inventory_forecast.domain.models import (
    ExecutiveMetric,
    ProcurementInsight,
)
from opstools.inventory_forecast.workbook.schema import (
    WorksheetName,
    get_sheet_schema,
)


def build_executive_summary_df(metrics: Sequence[ExecutiveMetric]) -> pl.DataFrame:
    """Build the Executive Summary DataFrame for the workbook.

    Args:
        metrics: Sequence of executive-level KPIs.

    Returns:
        A Polars DataFrame conforming to the Executive Summary worksheet schema.
    """
    schema = get_sheet_schema(WorksheetName.EXECUTIVE_SUMMARY)

    df_schema = {
        "category": pl.Utf8,
        "metric_name": pl.Utf8,
        "value": pl.Float64,
        "trend": pl.Utf8,
        "status": pl.Utf8,
    }

    if not metrics:
        return pl.DataFrame(schema=df_schema).select(list(schema.required_columns))

    df = pl.DataFrame(
        [
            {
                "category": m.category,
                "metric_name": m.metric_name,
                "value": float(m.value),
                "trend": m.trend.value,
                "status": m.status,
            }
            for m in metrics
        ],
        schema=df_schema,
    )

    return df.select(list(schema.required_columns))


def build_procurement_insights_df(
    insights: Sequence[ProcurementInsight],
) -> pl.DataFrame:
    """Build the Procurement Insights DataFrame for the workbook.

    Args:
        insights: Sequence of actionable procurement insights.

    Returns:
        A Polars DataFrame conforming to the Procurement Insights worksheet schema.
    """
    schema = get_sheet_schema(WorksheetName.PROCUREMENT_INSIGHTS)

    df_schema = {
        "insight_type": pl.Utf8,
        "priority": pl.Utf8,
        "description": pl.Utf8,
        "affected_items": pl.Int64,
        "potential_impact": pl.Float64,
    }

    if not insights:
        return pl.DataFrame(schema=df_schema).select(list(schema.required_columns))

    df = pl.DataFrame(
        [
            {
                "insight_type": i.insight_type,
                "priority": i.priority.value,
                "description": i.description,
                "affected_items": int(i.affected_items),
                "potential_impact": float(i.potential_impact),
            }
            for i in insights
        ],
        schema=df_schema,
    )

    return df.select(list(schema.required_columns))
