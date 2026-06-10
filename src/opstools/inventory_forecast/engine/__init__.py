"""Engine layer: all business computation as pure functions over Polars frames.

Re-exports the Phase-2 core builders so the orchestrator and tests can write
`from opstools.inventory_forecast.engine import reconstruct_demand` without
reaching into submodules (consistent with the ingestion package). Every function
here is pure: same input -> same output, no I/O, and no import of `ui`, `viz`, or
`workbook` (ARCHITECTURE.md sec 4.3, Constitution Rule 1). Phase-3 forecasting
and advanced analytics extend this set.
"""

from opstools.inventory_forecast.engine.classification import (
    build_abc_classification,
    classify_sbc,
)
from opstools.inventory_forecast.engine.demand import reconstruct_demand
from opstools.inventory_forecast.engine.financials import build_financial_summary
from opstools.inventory_forecast.engine.lead_time import compute_lead_time
from opstools.inventory_forecast.engine.pending import build_pending_deliveries
from opstools.inventory_forecast.engine.valuation import build_inventory_valuation

__all__ = [
    "build_abc_classification",
    "build_financial_summary",
    "build_inventory_valuation",
    "build_pending_deliveries",
    "classify_sbc",
    "compute_lead_time",
    "reconstruct_demand",
]
