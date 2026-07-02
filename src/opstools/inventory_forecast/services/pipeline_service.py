"""Pipeline execution service.

Coordinates the end-to-end execution of the inventory analytics platform.
Responsible for transitioning between ingestion, engine processing,
and workbook generation phases while updating the pipeline state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import polars as pl

from opstools.inventory_forecast.domain.enums import SourceKind
from opstools.inventory_forecast.domain.models import WorkbookMeta
from opstools.inventory_forecast.engine.orchestrator import run_analytics_engine
from opstools.inventory_forecast.ingestion import read_source
from opstools.inventory_forecast.services.state import PipelineState
from opstools.inventory_forecast.workbook.writer import write_workbook

# Fallback imports for legacy engine modules that might still produce
# raw DataFrame outputs required by the historical workbook schema.
try:
    from opstools.inventory_forecast.engine import (
        classification,
        demand,
        financials,
        lead_time,
        pending,
        valuation,
    )

    _HAS_LEGACY_ENGINE = True
except ImportError:
    classification = None
    demand = None
    financials = None
    lead_time = None
    pending = None
    valuation = None
    _HAS_LEGACY_ENGINE = False

logger = logging.getLogger(__name__)


def execute_pipeline(state: PipelineState) -> None:
    """Execute the full analytics pipeline.

    Coordinates ingestion, business intelligence analytics, and
    workbook persistence while maintaining runtime state.

    Args:
        state: The runtime state and configuration container.
    """
    try:
        logger.info("Starting Business Intelligence pipeline.")

        # Phase 1: Ingestion
        logger.info("Phase 1: Data Ingestion")
        source_data, exceptions_df = _ingest_data(state)

        pov_df = source_data.get(SourceKind.POV, pl.DataFrame())
        grn_df = source_data.get(SourceKind.GRN, pl.DataFrame())
        pv_df = source_data.get(SourceKind.PV, pl.DataFrame())
        closing_stock_df = source_data.get(SourceKind.CLOSING_STOCK, pl.DataFrame())

        state.complete_ingestion()

        # Phase 2: Analytics Engine
        logger.info("Phase 2: Analytics Engine")
        summary = run_analytics_engine(
            pov_df=pov_df,
            grn_df=grn_df,
            pv_df=pv_df,
            closing_stock_df=closing_stock_df,
            forecast_horizon=state.config.forecast_horizon,
        )

        # Phase 3: Legacy DataFrame Collection
        logger.info("Phase 3: Collecting secondary data sets")
        legacy_dfs = _collect_legacy_dataframes(
            pov_df=pov_df,
            grn_df=grn_df,
            pv_df=pv_df,
            closing_stock_df=closing_stock_df,
        )

        # Determine dataset statistics
        if "supplier_id" in pov_df.columns:
            total_suppliers = pov_df.select("supplier_id").n_unique()
        else:
            total_suppliers = 0
        if "item_id" in closing_stock_df.columns:
            total_items = closing_stock_df.select("item_id").n_unique()
        else:
            total_items = 0
        total_records = len(pov_df) + len(grn_df) + len(pv_df) + len(closing_stock_df)

        state.complete_engine(total_suppliers, total_items, total_records)

        # Phase 4: Workbook Generation
        logger.info("Phase 4: Workbook Generation")
        current_processing_time = (datetime.now(UTC) - state.start_time).total_seconds()

        meta = WorkbookMeta(
            schema_version="2.0.0",
            application_version=state.config.application_version,
            generated_at=datetime.now(UTC),
            forecast_horizon=state.config.forecast_horizon,
            total_suppliers=total_suppliers,
            total_items=total_items,
            total_records=total_records,
            processing_time_seconds=current_processing_time,
        )

        write_workbook(
            path=state.config.output_workbook_path,
            meta=meta,
            summary=summary,
            demand_df=legacy_dfs["demand"],
            lead_time_df=legacy_dfs["lead_time"],
            pending_df=legacy_dfs["pending"],
            financials_df=legacy_dfs["financials"],
            valuation_df=legacy_dfs["valuation"],
            abc_df=legacy_dfs["abc"],
            supplier_analysis_df=legacy_dfs["supplier_analysis"],
            supplier_summary_df=legacy_dfs["supplier_summary"],
            readiness_df=legacy_dfs["readiness"],
            exceptions_df=exceptions_df,
        )

        state.complete_workbook()
        logger.info("Pipeline completed successfully.")

    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        state.fail(exc)
        raise


def _ingest_data(
        state: PipelineState
) -> tuple[dict[SourceKind, pl.DataFrame], pl.DataFrame]:
    data: dict[SourceKind, list[pl.DataFrame]] = {kind: [] for kind in SourceKind}
    exceptions_list: list[pl.DataFrame] = []

    for path, kind in state.config.source_set.iter_with_kind():
        if not path.exists():
            logger.warning("Source file not found: %s", path)
            continue

        try:
            df_lazy, exc_df = read_source(path, kind)
            data[kind].append(df_lazy.collect())
            if exc_df.height > 0:
                exceptions_list.append(exc_df)
        except Exception as exc:
            logger.error("Failed to read %s: %s", path, exc)
            raise

    result: dict[SourceKind, pl.DataFrame] = {}
    for kind, dfs in data.items():
        result[kind] = pl.concat(dfs, how="vertical_relaxed") if dfs else pl.DataFrame()

    exc_schema = {
        "File Name": pl.Utf8,
        "Row Number": pl.Int64,
        "Reason": pl.Utf8,
        "Offending Value": pl.Utf8,
        "Full Record": pl.Utf8,
    }
    if exceptions_list:
        final_exceptions = pl.concat(exceptions_list)
    else:
        final_exceptions = pl.DataFrame(schema=exc_schema)

    return result, final_exceptions


def _collect_legacy_dataframes(
    pov_df: pl.DataFrame,
    grn_df: pl.DataFrame,
    pv_df: pl.DataFrame,
    closing_stock_df: pl.DataFrame,
) -> dict[str, pl.DataFrame]:
    """Attempt to collect legacy analytical DataFrames.

    Returns empty DataFrames if the legacy engine modules are
    unavailable or have been fully deprecated.
    """
    dfs = {
        "demand": pl.DataFrame(),
        "lead_time": pl.DataFrame(),
        "pending": pl.DataFrame(),
        "financials": pl.DataFrame(),
        "valuation": pl.DataFrame(),
        "abc": pl.DataFrame(),
        "supplier_analysis": pl.DataFrame(),
        "supplier_summary": pl.DataFrame(),
        "readiness": pl.DataFrame(),
    }

    if not _HAS_LEGACY_ENGINE:
        return dfs

    dfs["demand"] = _safe_call(
        getattr(demand, "calculate_current_demand", None), pov_df, grn_df
    )
    dfs["lead_time"] = _safe_call(
        getattr(lead_time, "calculate_lead_times_df", None), pov_df, grn_df
    )
    dfs["pending"] = _safe_call(
        getattr(pending, "calculate_pending_deliveries", None), pov_df, grn_df
    )
    dfs["financials"] = _safe_call(
        getattr(financials, "calculate_financial_summary", None), pv_df
    )
    dfs["valuation"] = _safe_call(
        getattr(valuation, "calculate_inventory_valuation", None),
        closing_stock_df,
        pv_df,
    )
    dfs["abc"] = _safe_call(
        getattr(classification, "classify_abc_df", None), pv_df, closing_stock_df
    )

    return dfs


def _safe_call[**P, R](
    func: Callable[P, R] | None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> pl.DataFrame:
    """Invoke an engine module safely, catching all errors."""
    if func is None:
        return pl.DataFrame()

    try:
        result = func(*args, **kwargs)
        if isinstance(result, pl.DataFrame):
            return result
        return pl.DataFrame()
    except Exception as exc:
        logger.debug("Legacy engine module skipped or failed: %s", exc)
        return pl.DataFrame()
