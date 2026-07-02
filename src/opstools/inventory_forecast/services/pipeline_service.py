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
        source_data = _ingest_data(state)

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

        # Determine dataset statistics for metadata
        total_suppliers = 0
        if "supplier_id" in pov_df.columns:
            total_suppliers = pov_df.select("supplier_id").n_unique()

        total_items = 0
        if "item_id" in closing_stock_df.columns:
            total_items = closing_stock_df.select("item_id").n_unique()

        total_records = len(pov_df) + len(grn_df) + len(pv_df) + len(closing_stock_df)

        state.complete_engine(
            total_suppliers=total_suppliers,
            total_items=total_items,
            total_records=total_records,
        )

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
        )

        state.complete_workbook()
        logger.info("Pipeline completed successfully.")

    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        state.fail(exc)
        raise


def _ingest_data(state: PipelineState) -> dict[SourceKind, pl.DataFrame]:
    """Read and combine raw data from the configured source set.

    Uses Polars directly to ensure the pipeline functions independently
    of the underlying ingestion modules' refactor status.
    """
    data: dict[SourceKind, list[pl.DataFrame]] = {kind: [] for kind in SourceKind}

    for path, kind in state.config.source_set.iter_with_kind():
        if not path.exists():
            logger.warning("Source file not found: %s", path)
            continue

        try:
            if path.suffix.lower() == ".csv":
                # Increase schema inference length for robust reading
                df = pl.read_csv(path, infer_schema_length=10000)
            else:
                df = pl.read_excel(path, engine="calamine")
            data[kind].append(df)
        except Exception as exc:
            logger.error("Failed to read %s: %s", path, exc)
            raise

    # Combine multiple files of the same kind into unified DataFrames
    result: dict[SourceKind, pl.DataFrame] = {}
    for kind, dfs in data.items():
        if dfs:
            # relaxed appending allows for slight schema variations in yearly files
            result[kind] = pl.concat(dfs, how="vertical_relaxed")
        else:
            result[kind] = pl.DataFrame()

    return result


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
