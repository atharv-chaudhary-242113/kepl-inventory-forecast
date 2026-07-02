"""Workbook DataFrame builders.

Transforms domain models and engine results into schema-compliant
Polars DataFrames for Excel serialization. These serve as the link
between the Python object layer and the Business Intelligence
reporting layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl

from opstools.inventory_forecast.domain.enums import InventoryStatus
from opstools.inventory_forecast.domain.models import (
    DemandCharacteristics,
    ForecastResult,
    InventoryHealthReport,
    SourcingRiskReport,
    SupplierRisk,
)
from opstools.inventory_forecast.workbook.schema import (
    WorksheetName,
    get_sheet_schema,
)


def build_inventory_health_df(reports: Sequence[InventoryHealthReport]) -> pl.DataFrame:
    """Build the Inventory Health DataFrame.

    Args:
        reports: Sequence of inventory health assessments.

    Returns:
        Schema-compliant Polars DataFrame.
    """
    schema = get_sheet_schema(WorksheetName.INVENTORY_HEALTH)

    df_schema = {
        "item": pl.Utf8,
        "status": pl.Utf8,
        "months_of_cover": pl.Float64,
        "excess_inventory_value": pl.Float64,
        "action_required": pl.Utf8,
    }

    if not reports:
        return pl.DataFrame(schema=df_schema).select(list(schema.required_columns))

    data = []
    for r in reports:
        action = "Monitor"
        if r.status == InventoryStatus.OVERSTOCKED:
            action = "Reduce Orders"
        elif r.status == InventoryStatus.LOW_STOCK:
            action = "Expedite Procurement"
        elif r.status == InventoryStatus.DEAD_STOCK:
            action = "Liquidate / Write-off"

        data.append(
            {
                "item": r.item_id,
                "status": r.status.value.title(),
                "months_of_cover": float(r.months_of_cover),
                "excess_inventory_value": float(r.excess_inventory_value),
                "action_required": action,
            }
        )

    return pl.DataFrame(data, schema=df_schema).select(list(schema.required_columns))


def build_supplier_risk_df(risks: Sequence[SupplierRisk]) -> pl.DataFrame:
    """Build the Supplier Risk summary DataFrame.

    Aggregates item-level supplier risks up to the supplier level
    for the procurement dashboard.

    Args:
        risks: Sequence of supplier risk assessments.

    Returns:
        Schema-compliant Polars DataFrame.
    """
    schema = get_sheet_schema(WorksheetName.SUPPLIER_RISK)

    df_schema = {
        "supplier": pl.Utf8,
        "dependency_level": pl.Utf8,
        "risk_level": pl.Utf8,
        "supplier_count": pl.Int64,
        "items_at_risk": pl.Int64,
    }

    if not risks:
        return pl.DataFrame(schema=df_schema).select(list(schema.required_columns))

    supplier_map: dict[str, dict[str, Any]] = {}

    for r in risks:
        if r.supplier_id not in supplier_map:
            supplier_map[r.supplier_id] = {
                "dependency_level": r.dependency_level.value.title(),
                "risk_level": r.risk_level.value.title(),
                "supplier_count": r.supplier_count,
                "items_at_risk": 0,
            }
        supplier_map[r.supplier_id]["items_at_risk"] += 1

    data = [
        {
            "supplier": sup,
            "dependency_level": metrics["dependency_level"],
            "risk_level": metrics["risk_level"],
            "supplier_count": int(metrics["supplier_count"]),
            "items_at_risk": int(metrics["items_at_risk"]),
        }
        for sup, metrics in supplier_map.items()
    ]

    return pl.DataFrame(data, schema=df_schema).select(list(schema.required_columns))


def build_sourcing_risk_df(reports: Sequence[SourcingRiskReport]) -> pl.DataFrame:
    """Build the item-level Sourcing Risk DataFrame.

    Args:
        reports: Sequence of sourcing risk reports.

    Returns:
        Schema-compliant Polars DataFrame.
    """
    schema = get_sheet_schema(WorksheetName.SOURCING_RISK)

    df_schema = {
        "item": pl.Utf8,
        "supplier_count": pl.Int64,
        "primary_supplier": pl.Utf8,
        "dependency_level": pl.Utf8,
        "risk_level": pl.Utf8,
    }

    if not reports:
        return pl.DataFrame(schema=df_schema).select(list(schema.required_columns))

    data = [
        {
            "item": r.item_id,
            "supplier_count": int(r.supplier_count),
            "primary_supplier": r.primary_supplier,
            "dependency_level": r.dependency_level.value.title(),
            "risk_level": r.risk_level.value.title(),
        }
        for r in reports
    ]

    return pl.DataFrame(data, schema=df_schema).select(list(schema.required_columns))


def build_sbc_classification_df(chars: Sequence[DemandCharacteristics]) -> pl.DataFrame:
    """Build the SBC Demand Classification DataFrame.

    Args:
        chars: Sequence of demand characteristics.

    Returns:
        Schema-compliant Polars DataFrame.
    """
    schema = get_sheet_schema(WorksheetName.SBC_CLASSIFICATION)

    df_schema = {
        "supplier": pl.Utf8,
        "item": pl.Utf8,
        "adi": pl.Float64,
        "cv_squared": pl.Float64,
        "demand_class": pl.Utf8,
    }

    if not chars:
        return pl.DataFrame(schema=df_schema).select(list(schema.required_columns))

    data = [
        {
            "supplier": "N/A",  # Handled natively by workbook relationships later
            "item": c.item_id,
            "adi": float(c.adi),
            "cv_squared": float(c.cv2),
            "demand_class": c.demand_class.value.upper(),
        }
        for c in chars
    ]

    return pl.DataFrame(data, schema=df_schema).select(list(schema.required_columns))


def build_forecasts_df(forecasts: Sequence[ForecastResult]) -> pl.DataFrame:
    """Build the Forecasts DataFrame.

    Flattens time-series forecast sequences into standard row-oriented
    data required by BI visualization tools.

    Args:
        forecasts: Sequence of ForecastResult models.

    Returns:
        Schema-compliant Polars DataFrame.
    """
    schema = get_sheet_schema(WorksheetName.FORECASTS)

    df_schema = {
        "supplier": pl.Utf8,
        "item": pl.Utf8,
        "forecast_period": pl.Int64,
        "forecast_quantity": pl.Float64,
        "forecast_value": pl.Float64,
        "trend_component": pl.Float64,
        "seasonal_component": pl.Float64,
        "model_used": pl.Utf8,
        "confidence_score": pl.Float64,
    }

    if not forecasts:
        return pl.DataFrame(schema=df_schema).select(list(schema.required_columns))

    data = []
    for f in forecasts:
        # Infer a rough confidence proxy from prediction errors for BI reporting
        confidence = max(0.0, min(1.0, 1.0 - (f.metrics.mase / 10.0)))

        for i, qty in enumerate(f.forecast_values):
            data.append(
                {
                    "supplier": "N/A",  # Granular sourcing logic applied downstream
                    "item": f.item_id,
                    "forecast_period": i + 1,
                    "forecast_quantity": float(qty),
                    "forecast_value": 0.0,  # Computed if financial metadata is joined
                    "trend_component": 0.0,
                    "seasonal_component": 0.0,
                    "model_used": f.selected_model.value.upper(),
                    "confidence_score": float(confidence),
                }
            )

    return pl.DataFrame(data, schema=df_schema).select(list(schema.required_columns))
