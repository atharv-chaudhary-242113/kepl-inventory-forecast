"""Tests for the engine orchestrator (engine/orchestrator.py)."""

from datetime import date

import polars as pl

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.engine import EngineOutput, run_engine

_SNAP = date(2025, 6, 30)


def _smooth_pov(ledger) -> pl.LazyFrame:
    # 12 months of regular demand so forecasting has enough history to run.
    return ledger(
        [(date(2024, m, 1), f"O{m}", "Acme", "Wire", 10.0, 100.0) for m in range(1, 13)]
    )


def test_run_engine_returns_engine_output(ledger, closing) -> None:
    """The DAG produces a fully-populated EngineOutput dataclass."""
    out = run_engine(
        pov=_smooth_pov(ledger),
        grn=ledger([(date(2024, 2, 1), "G1", "Acme", "Wire", 10.0, 100.0)]),
        pv=ledger([(date(2024, 1, 1), "P1", "Acme", "Wire", 12.0, 120.0)]),
        closing=closing([("Wire", 30.0, 10.0)]),
        cfg=Settings(),
        snapshot_date=_SNAP,
    )
    assert isinstance(out, EngineOutput)


def test_run_engine_outputs_are_collected_dataframes(ledger, closing) -> None:
    """Every leaf is materialized — services get DataFrames, not LazyFrames."""
    out = run_engine(
        pov=_smooth_pov(ledger),
        grn=ledger([]),
        pv=ledger([(date(2024, 1, 1), "P1", "Acme", "Wire", 1.0, 10.0)]),
        closing=closing([]),
        cfg=Settings(),
        snapshot_date=_SNAP,
    )
    for name in (
        "demand_history",
        "forecasts",
        "supplier_analysis",
        "supplier_partnerships",
        "lead_time_analysis",
        "pending_deliveries",
        "financial_summary",
        "abc_classification",
        "sbc_classification",
        "inventory_valuation",
        "reorder_recommendations",
        "price_variance",
        "sourcing_risk",
        "fill_rate",
        "inventory_health",
    ):
        assert isinstance(getattr(out, name), pl.DataFrame), name


def test_sheet_map_keys_match_workbook_schema(ledger, closing) -> None:
    """sheet_map() exposes exactly the ten canonical Phase-3 sheet names."""
    out = run_engine(
        pov=ledger([]),
        grn=ledger([]),
        pv=ledger([]),
        closing=closing([]),
        cfg=Settings(),
        snapshot_date=_SNAP,
    )
    assert set(out.sheet_map().keys()) == {
        "Demand_History",
        "Forecasts",
        "Supplier_Analysis",
        "Supplier_Partnerships",
        "Lead_Time_Analysis",
        "Pending_Deliveries",
        "Financial_Summary",
        "ABC_Classification",
        "SBC_Classification",
        "Inventory_Valuation",
    }


def test_lead_time_sheet_matches_workbook_contract(ledger, closing) -> None:
    """Lead_Time_Analysis is projected to the seven sheet columns."""
    out = run_engine(
        pov=ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0)]),
        grn=ledger([(date(2025, 1, 6), "G1", "Acme", "Wire", 5.0, 50.0)]),
        pv=ledger([]),
        closing=closing([]),
        cfg=Settings(),
        snapshot_date=_SNAP,
    )
    assert out.lead_time_analysis.columns == [
        "supplier",
        "item",
        "pov_date",
        "grn_date",
        "ordered_qty",
        "delivered_qty",
        "lead_time_days",
    ]


def test_supplier_risk_toggle_empties_frame_but_keeps_schema(ledger, closing) -> None:
    """Disabling supplier risk yields an empty Supplier_Analysis with stable schema."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0)])
    cfg = Settings(enable_supplier_risk=False)
    out = run_engine(
        pov=pov,
        grn=ledger([]),
        pv=ledger([]),
        closing=closing([]),
        cfg=cfg,
        snapshot_date=_SNAP,
    )
    assert out.supplier_analysis.height == 0
    assert out.supplier_analysis.columns == [
        "supplier",
        "total_spend",
        "total_orders",
        "total_deliveries",
        "average_lead_time",
        "lead_time_stddev",
        "pending_deliveries",
        "reliability_score",
        "risk_score",
    ]


def test_partnerships_toggle_empties_frame_but_keeps_schema(ledger, closing) -> None:
    """Disabling partnership detection yields an empty (typed) frame."""
    cfg = Settings(enable_partnerships=False)
    out = run_engine(
        pov=ledger([]),
        grn=ledger([]),
        pv=ledger([]),
        closing=closing([]),
        cfg=cfg,
        snapshot_date=_SNAP,
    )
    assert out.supplier_partnerships.height == 0
    assert out.supplier_partnerships.columns == [
        "supplier_a",
        "supplier_b",
        "matching_events",
        "confidence_score",
        "status",
    ]


def test_empty_inputs_yield_all_empty_outputs(ledger, closing) -> None:
    """The DAG runs end-to-end on empty inputs and produces empty (typed) frames."""
    out = run_engine(
        pov=ledger([]),
        grn=ledger([]),
        pv=ledger([]),
        closing=closing([]),
        cfg=Settings(),
        snapshot_date=_SNAP,
    )
    for frame in out.sheet_map().values():
        assert frame.height == 0
    for name in (
        "reorder_recommendations",
        "price_variance",
        "sourcing_risk",
        "fill_rate",
        "inventory_health",
    ):
        assert getattr(out, name).height == 0


def test_snapshot_date_is_stamped_in_valuation(ledger, closing) -> None:
    """The explicit snapshot_date flows through to Inventory_Valuation rows."""
    out = run_engine(
        pov=ledger([]),
        grn=ledger([]),
        pv=ledger([]),
        closing=closing([("Wire", 5.0, 10.0)]),
        cfg=Settings(),
        snapshot_date=_SNAP,
    )
    assert out.inventory_valuation["snapshot_date"].to_list() == [_SNAP]
