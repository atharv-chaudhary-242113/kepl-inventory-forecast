"""Tests for ``build_reorder_recommendations`` (engine/reorder.py)."""

import math
from datetime import date

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.engine import (
    build_reorder_recommendations,
    compute_lead_time,
    reconstruct_demand,
)

_OUTPUT_COLUMNS = [
    "supplier",
    "item",
    "avg_monthly_demand",
    "demand_std",
    "lead_time_months",
    "reorder_point",
]


# pyrefly: ignore [implicit-any-parameter]
def test_formula_matches_documented_definition(ledger) -> None:
    """reorder = avg*LT + z*std*sqrt(LT) within float tolerance."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0),
            (date(2025, 2, 1), "O2", "Acme", "Wire", 20.0, 200.0),
        ]
    )
    grn = ledger(
        [
            (date(2025, 1, 31), "G1", "Acme", "Wire", 10.0, 100.0),
            (date(2025, 3, 2), "G2", "Acme", "Wire", 20.0, 200.0),
        ]
    )
    cfg = Settings()
    demand = reconstruct_demand(pov)
    lt = compute_lead_time(pov, grn)
    out = build_reorder_recommendations(demand, lt, cfg).collect()

    row = out.row(0, named=True)
    expected = row["avg_monthly_demand"] * row[
        "lead_time_months"
    ] + cfg.service_z * row["demand_std"] * math.sqrt(row["lead_time_months"])
    assert abs(row["reorder_point"] - expected) < 1e-6


# pyrefly: ignore [implicit-any-parameter]
def test_falls_back_to_default_lead_time(ledger) -> None:
    """No observed lead time -> cfg.default_lead_time_days / 30 months."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 10.0, 100.0),
            (date(2025, 2, 1), "O2", "Acme", "Wire", 10.0, 100.0),
        ]
    )
    grn = ledger([])
    cfg = Settings(default_lead_time_days=60)

    demand = reconstruct_demand(pov)
    lt = compute_lead_time(pov, grn)
    out = build_reorder_recommendations(demand, lt, cfg).collect()

    assert out.row(0, named=True)["lead_time_months"] == 2.0  # 60 / 30


# pyrefly: ignore [implicit-any-parameter]
def test_single_observation_zero_std(ledger) -> None:
    """One demand month -> demand_std = 0 (sample std is undefined, treated as 0)."""
    pov = ledger([(date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0)])
    grn = ledger([(date(2025, 1, 11), "G1", "Acme", "Wire", 5.0, 50.0)])

    demand = reconstruct_demand(pov)
    lt = compute_lead_time(pov, grn)
    out = build_reorder_recommendations(demand, lt, Settings()).collect()

    row = out.row(0, named=True)
    assert row["demand_std"] == 0.0
    # No std contribution -> reorder = avg * LT.
    assert (
        abs(row["reorder_point"] - row["avg_monthly_demand"] * row["lead_time_months"])
        < 1e-9
    )


# pyrefly: ignore [implicit-any-parameter]
def test_higher_service_z_increases_reorder(ledger) -> None:
    """A higher service level demands more safety stock."""
    pov = ledger(
        [
            (date(2025, 1, 1), "O1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 2, 1), "O2", "Acme", "Wire", 20.0, 200.0),  # std > 0
        ]
    )
    grn = ledger(
        [
            (date(2025, 1, 11), "G1", "Acme", "Wire", 5.0, 50.0),
            (date(2025, 2, 11), "G2", "Acme", "Wire", 20.0, 200.0),
        ]
    )
    demand = reconstruct_demand(pov)
    lt = compute_lead_time(pov, grn)
    low = build_reorder_recommendations(demand, lt, Settings(service_z=1.0)).collect()
    high = build_reorder_recommendations(demand, lt, Settings(service_z=2.5)).collect()

    assert (
        high.row(0, named=True)["reorder_point"]
        > low.row(0, named=True)["reorder_point"]
    )


# pyrefly: ignore [implicit-any-parameter]
def test_reorder_output_column_order_matches_contract(ledger) -> None:
    out = build_reorder_recommendations(
        reconstruct_demand(ledger([])),
        compute_lead_time(ledger([]), ledger([])),
        Settings(),
    ).collect()
    assert out.columns == _OUTPUT_COLUMNS
