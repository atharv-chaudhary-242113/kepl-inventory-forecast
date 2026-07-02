"""Workbook generation and persistence.

Transforms domain models and engine results into a structured Excel workbook
that acts as the single source of truth for the Business Intelligence platform.

No analytics or domain calculations are performed here. This module
is strictly responsible for schema enforcement, formatting, and I/O.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from opstools.inventory_forecast.domain.models import (
    AnalyticsSummary,
    WorkbookMeta,
)
from opstools.inventory_forecast.workbook import (
    builders,
    dashboard_data,
    executive_summary,
)
from opstools.inventory_forecast.workbook.schema import (
    WorksheetName,
    get_sheet_schema,
    required_sheet_names,
)


def write_workbook(
    path: Path,
    meta: WorkbookMeta,
    summary: AnalyticsSummary,
    demand_df: pl.DataFrame,
    lead_time_df: pl.DataFrame,
    pending_df: pl.DataFrame,
    financials_df: pl.DataFrame,
    valuation_df: pl.DataFrame,
    abc_df: pl.DataFrame,
    supplier_analysis_df: pl.DataFrame,
    supplier_summary_df: pl.DataFrame,
    readiness_df: pl.DataFrame,
    exceptions_df: pl.DataFrame | None = None,
) -> None:
    """Write the complete analytics results to an Excel workbook.

    Enforces the presentation schema required by business managers and
    downstream dashboarding tools.

    Args:
        path: Destination file path.
        meta: Workbook provenance and metadata.
        summary: Aggregated business intelligence results from the orchestrator.
        demand_df: Current demand records.
        lead_time_df: Processed lead-time calculations.
        pending_df: Outstanding purchase orders.
        financials_df: Item-level financial summary.
        valuation_df: Current inventory valuation snapshot.
        abc_df: Value-based inventory classification.
        supplier_analysis_df: Detailed supplier performance metrics.
        supplier_summary_df: Aggregated supplier portfolio metrics.
        readiness_df: Forecast viability assessment.
        exceptions_df: Exception reports.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    meta_schema = get_sheet_schema(WorksheetName.METADATA)
    meta_df = pl.DataFrame(
        [
            {
                "schema_version": meta.schema_version,
                "application_version": meta.application_version,
                "generated_at": meta.generated_at.isoformat(),
                "forecast_horizon": meta.forecast_horizon,
                "total_suppliers": meta.total_suppliers,
                "total_items": meta.total_items,
                "total_records": meta.total_records,
                "processing_time_seconds": meta.processing_time_seconds,
            }
        ],
        schema={
            "schema_version": pl.Utf8,
            "application_version": pl.Utf8,
            "generated_at": pl.Utf8,
            "forecast_horizon": pl.Int64,
            "total_suppliers": pl.Int64,
            "total_items": pl.Int64,
            "total_records": pl.Int64,
            "processing_time_seconds": pl.Float64,
        },
    ).select(list(meta_schema.required_columns))

    exec_summary_df = executive_summary.build_executive_summary_df(
        summary.executive_metrics
    )
    dash_data_df = dashboard_data.build_dashboard_data_df(summary.dashboard_data)
    proc_insights_df = executive_summary.build_procurement_insights_df(
        summary.procurement_insights
    )

    inv_health_df = builders.build_inventory_health_df(summary.inventory_health)
    sup_risk_df = builders.build_supplier_risk_df(summary.supplier_risks)
    src_risk_df = builders.build_sourcing_risk_df(summary.sourcing_risks)

    demand_chars = [
        type(
            "TempSbc",
            (),
            {
                "item_id": f.item_id,
                "adi": 0.0,
                "cv2": 0.0,
                "demand_class": f.demand_class,
            },
        )()
        for f in summary.forecasts
    ]
    sbc_df = builders.build_sbc_classification_df(demand_chars)
    forecasts_df = builders.build_forecasts_df(summary.forecasts)

    sheet_mapping = {
        WorksheetName.METADATA: meta_df,
        WorksheetName.EXECUTIVE_SUMMARY: exec_summary_df,
        WorksheetName.DASHBOARD_DATA: dash_data_df,
        WorksheetName.CURRENT_DEMAND: _enforce_schema(
            WorksheetName.CURRENT_DEMAND, demand_df
        ),
        WorksheetName.INVENTORY_HEALTH: inv_health_df,
        WorksheetName.PROCUREMENT_INSIGHTS: proc_insights_df,
        WorksheetName.SUPPLIER_ANALYSIS: _enforce_schema(
            WorksheetName.SUPPLIER_ANALYSIS, supplier_analysis_df
        ),
        WorksheetName.SUPPLIER_SUMMARY: _enforce_schema(
            WorksheetName.SUPPLIER_SUMMARY, supplier_summary_df
        ),
        WorksheetName.SUPPLIER_RISK: sup_risk_df,
        WorksheetName.SOURCING_RISK: src_risk_df,
        WorksheetName.LEAD_TIME: _enforce_schema(WorksheetName.LEAD_TIME, lead_time_df),
        WorksheetName.PENDING_DELIVERIES: _enforce_schema(
            WorksheetName.PENDING_DELIVERIES, pending_df
        ),
        WorksheetName.FINANCIAL_SUMMARY: _enforce_schema(
            WorksheetName.FINANCIAL_SUMMARY, financials_df
        ),
        WorksheetName.INVENTORY_VALUATION: _enforce_schema(
            WorksheetName.INVENTORY_VALUATION, valuation_df
        ),
        WorksheetName.ABC_CLASSIFICATION: _enforce_schema(
            WorksheetName.ABC_CLASSIFICATION, abc_df
        ),
        WorksheetName.SBC_CLASSIFICATION: sbc_df,
        WorksheetName.FORECAST_READINESS: _enforce_schema(
            WorksheetName.FORECAST_READINESS, readiness_df
        ),
        WorksheetName.FORECASTS: forecasts_df,
        WorksheetName.DASHBOARD_CACHE: pl.DataFrame(),
    }

    _write_to_excel(path, sheet_mapping, exceptions_df)


def _enforce_schema(name: WorksheetName, df: pl.DataFrame) -> pl.DataFrame:
    schema = get_sheet_schema(name)
    for col in schema.required_columns:
        if col not in df.columns:
            dtype = (
                pl.Float64
                if "value" in col or "quantity" in col or "cost" in col
                else pl.Utf8
            )
            df = df.with_columns(pl.lit(None).cast(dtype).alias(col))
    return df.select(list(schema.required_columns))


def _write_to_excel(
    path: Path,
    sheet_mapping: dict[WorksheetName, pl.DataFrame],
    exceptions_df: pl.DataFrame | None = None,
) -> None:
    with pl.Config(tbl_rows=10):
        string_keyed_mapping = {
            sheet_name.value: df for sheet_name, df in sheet_mapping.items()
        }

        # Dynamically append the Exceptions sheet if data exists
        if exceptions_df is not None and not exceptions_df.is_empty():
            string_keyed_mapping["Exceptions"] = exceptions_df

        ordered_mapping = {}
        for sheet_name in required_sheet_names():
            if sheet_name.value in string_keyed_mapping:
                ordered_mapping[sheet_name.value] = string_keyed_mapping[
                    sheet_name.value
                ]

        # Ensure Exceptions is placed at the end of the workbook
        if "Exceptions" in string_keyed_mapping:
            ordered_mapping["Exceptions"] = string_keyed_mapping["Exceptions"]

        import xlsxwriter

        with xlsxwriter.Workbook(path) as workbook:
            header_format = workbook.add_format(
                {
                    "bold": True,
                    "bg_color": "#2C3E50",
                    "font_color": "white",
                    "border": 1,
                }
            )

            for sheet_name_str, df in ordered_mapping.items():
                worksheet = workbook.add_worksheet(sheet_name_str)

                for col_num, column_name in enumerate(df.columns):
                    worksheet.write(0, col_num, column_name, header_format)

                if len(df) > 0:
                    for row_num, row_data in enumerate(df.iter_rows()):
                        for col_num, cell_value in enumerate(row_data):
                            worksheet.write(row_num + 1, col_num, cell_value)

                worksheet.autofit()
