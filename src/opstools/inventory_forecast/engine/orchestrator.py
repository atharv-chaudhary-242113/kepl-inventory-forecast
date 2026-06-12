"""Engine pipeline DAG: ingested frames -> all computed engine outputs.

Wires the pure engine builders into the directed acyclic graph described in
ARCHITECTURE.md §5, collecting once at the leaves. This module is the single
place the engine layer is composed; it imports only sibling engine modules and
``domain``/``config`` (never ``ingestion``, ``workbook``, ``viz``, or ``ui`` —
Constitution Rule 1, ARCHITECTURE.md §4.3). Ingestion (file -> LazyFrame) and
persistence (frames -> workbook) live in the surrounding layers; the orchestrator
takes already-validated canonical LazyFrames and returns collected DataFrames.

``snapshot_date`` is passed explicitly (API_CONTRACT.md; Constitution Rule 9) so
valuation never depends on the wall clock. The ``enable_*`` toggles (README §10)
are honoured by emitting a correctly-typed *empty* frame when an analysis is off,
keeping every output's schema stable for the workbook writer.
"""

from dataclasses import dataclass
from datetime import date

import polars as pl

from opstools.inventory_forecast.config.settings import Settings
from opstools.inventory_forecast.engine.classification import (
    build_abc_classification,
    classify_sbc,
)
from opstools.inventory_forecast.engine.demand import reconstruct_demand
from opstools.inventory_forecast.engine.financials import build_financial_summary
from opstools.inventory_forecast.engine.forecasting import forecast_demand
from opstools.inventory_forecast.engine.fulfillment import build_fill_rate
from opstools.inventory_forecast.engine.inventory_health import build_inventory_health
from opstools.inventory_forecast.engine.lead_time import compute_lead_time
from opstools.inventory_forecast.engine.partnerships import detect_partnerships
from opstools.inventory_forecast.engine.pending import build_pending_deliveries
from opstools.inventory_forecast.engine.price_variance import build_price_variance
from opstools.inventory_forecast.engine.reorder import build_reorder_recommendations
from opstools.inventory_forecast.engine.sourcing import build_sourcing_risk
from opstools.inventory_forecast.engine.supplier_risk import build_supplier_analysis
from opstools.inventory_forecast.engine.valuation import build_inventory_valuation

# The seven Lead_Time_Analysis sheet columns (WORKBOOK_SCHEMA.md). compute_lead_time
# returns a superset (with the internal order_id/voucher_number keys); the sheet
# drops those, so the orchestrator projects down to the contract here.
_LEAD_TIME_SHEET_COLUMNS: tuple[str, ...] = (
    "supplier",
    "item",
    "pov_date",
    "grn_date",
    "ordered_qty",
    "delivered_qty",
    "lead_time_days",
)


@dataclass(frozen=True, slots=True)
class EngineOutput:
    """All collected engine frames for one pipeline run.

    The first ten frames map 1:1 onto WORKBOOK_SCHEMA.md sheets (everything except
    Metadata and the Dashboard_Cache, both built in the Phase-4 workbook layer).
    The final five are the advanced analytics that feed the Dashboard_Cache and
    the supporting dashboards (DASHBOARD_SPEC.md) but have no standalone sheet.
    """

    # --- Canonical workbook sheets ---
    demand_history: pl.DataFrame
    forecasts: pl.DataFrame
    supplier_analysis: pl.DataFrame
    supplier_partnerships: pl.DataFrame
    lead_time_analysis: pl.DataFrame
    pending_deliveries: pl.DataFrame
    financial_summary: pl.DataFrame
    abc_classification: pl.DataFrame
    sbc_classification: pl.DataFrame
    inventory_valuation: pl.DataFrame
    # --- Advanced analytics (no standalone sheet) ---
    reorder_recommendations: pl.DataFrame
    price_variance: pl.DataFrame
    sourcing_risk: pl.DataFrame
    fill_rate: pl.DataFrame
    inventory_health: pl.DataFrame

    def sheet_map(self) -> dict[str, pl.DataFrame]:
        """Return the canonical-sheet frames keyed by WORKBOOK_SCHEMA.md sheet name.

        This is the handoff the Phase-4 workbook writer consumes (Metadata and
        Dashboard_Cache are added by that layer, so they are absent here).
        """
        return {
            "Demand_History": self.demand_history,
            "Forecasts": self.forecasts,
            "Supplier_Analysis": self.supplier_analysis,
            "Supplier_Partnerships": self.supplier_partnerships,
            "Lead_Time_Analysis": self.lead_time_analysis,
            "Pending_Deliveries": self.pending_deliveries,
            "Financial_Summary": self.financial_summary,
            "ABC_Classification": self.abc_classification,
            "SBC_Classification": self.sbc_classification,
            "Inventory_Valuation": self.inventory_valuation,
        }


def run_engine(
    pov: pl.LazyFrame,
    grn: pl.LazyFrame,
    pv: pl.LazyFrame,
    closing: pl.LazyFrame,
    cfg: Settings,
    snapshot_date: date,
) -> EngineOutput:
    """Run the full engine DAG over the four ingested ledgers.

    Args:
        pov: Canonical POV ledger (orders / demand signal).
        grn: Canonical GRN ledger (receipts).
        pv: Canonical PV ledger (authoritative financial source).
        closing: Canonical closing-stock snapshot.
        cfg: Run settings (horizon, freight rate, ABC thresholds, toggles).
        snapshot_date: Explicit valuation date (never the wall clock).

    Returns:
        An ``EngineOutput`` with every frame collected. Each frame already meets
        its documented schema, so the workbook layer can write them directly.
    """
    # --- Demand -> classification -> forecast branch ---
    demand = reconstruct_demand(pov)
    sbc = classify_sbc(demand)
    abc = build_abc_classification(pv, cfg)
    forecasts = forecast_demand(demand, sbc, cfg.forecast_horizon, cfg)

    # --- Financial branch (PV is the source of truth) ---
    financial = build_financial_summary(pv, cfg)
    valuation = build_inventory_valuation(closing, pv, snapshot_date)

    # --- Operational branch (FIFO lead time feeds pending / supplier / fill rate) ---
    lead_time = compute_lead_time(pov, grn)
    pending = build_pending_deliveries(lead_time)
    supplier_analysis = build_supplier_analysis(lead_time, pending, financial, cfg)
    partnerships = detect_partnerships(pov, cfg)

    # --- Advanced analytics ---
    reorder = build_reorder_recommendations(demand, lead_time, cfg)
    price_variance = build_price_variance(pv)
    sourcing = build_sourcing_risk(pv)
    fill_rate = build_fill_rate(lead_time)
    inventory_health = build_inventory_health(valuation, demand)

    # Honour the run toggles by zeroing out the rows while preserving the schema,
    # so a disabled analysis still hands a well-typed (empty) frame downstream.
    if not cfg.enable_supplier_risk:
        supplier_analysis = supplier_analysis.head(0)
    if not cfg.enable_partnerships:
        partnerships = partnerships.head(0)

    # Project the lead-time superset down to the Lead_Time_Analysis sheet contract.
    lead_time_sheet = lead_time.select(list(_LEAD_TIME_SHEET_COLUMNS))

    # Collect once at every leaf (ARCHITECTURE.md §5). forecast_demand already
    # materialized internally; .collect() on its returned LazyFrame is a no-op pass.
    return EngineOutput(
        demand_history=demand.collect(),
        forecasts=forecasts.collect(),
        supplier_analysis=supplier_analysis.collect(),
        supplier_partnerships=partnerships.collect(),
        lead_time_analysis=lead_time_sheet.collect(),
        pending_deliveries=pending.collect(),
        financial_summary=financial.collect(),
        abc_classification=abc.collect(),
        sbc_classification=sbc.collect(),
        inventory_valuation=valuation.collect(),
        reorder_recommendations=reorder.collect(),
        price_variance=price_variance.collect(),
        sourcing_risk=sourcing.collect(),
        fill_rate=fill_rate.collect(),
        inventory_health=inventory_health.collect(),
    )
