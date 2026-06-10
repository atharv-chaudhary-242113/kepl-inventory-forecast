"""Tests for ``build_abc_classification`` and ``classify_sbc`` (classification.py)."""

from datetime import date
from decimal import Decimal

import polars as pl

from opstools.inventory_forecast.config.settings import Settings
from opstools.inventory_forecast.domain.enums import AbcClass, SbcClass
from opstools.inventory_forecast.engine import build_abc_classification, classify_sbc


def _demand(rows: list[tuple[str, str, date, float]]) -> pl.LazyFrame:
    """Build a sparse Demand_History frame ``(supplier, item, period, qty)``."""
    return pl.LazyFrame(
        {
            "period": [r[2] for r in rows],
            "supplier": [r[0] for r in rows],
            "item": [r[1] for r in rows],
            "demand_quantity": [r[3] for r in rows],
            "demand_value": [Decimal(str(r[3])) for r in rows],
        },
        schema={
            "period": pl.Date,
            "supplier": pl.Utf8,
            "item": pl.Utf8,
            "demand_quantity": pl.Float64,
            "demand_value": pl.Decimal(scale=4),
        },
    )


# --- ABC ------------------------------------------------------------------


def test_abc_bands_split_by_cumulative_value(ledger) -> None:
    """Items fall into A/B/C by where their cumulative value share sits."""
    cfg = Settings()
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "High", 1.0, 800.0),
            (date(2025, 1, 1), "P2", "Acme", "Mid", 1.0, 150.0),
            (date(2025, 1, 1), "P3", "Acme", "Low", 1.0, 50.0),
        ]
    )
    out = build_abc_classification(pv, cfg).collect()
    by_item = {r["item"]: r for r in out.iter_rows(named=True)}

    # Cumulative: High 0.80 (<=0.80 -> A), +Mid 0.95 (<=0.95 -> B), +Low 1.0 -> C.
    assert by_item["High"]["abc_class"] == AbcClass.A.value
    assert by_item["Mid"]["abc_class"] == AbcClass.B.value
    assert by_item["Low"]["abc_class"] == AbcClass.C.value


def test_abc_annual_value_stays_decimal_and_aggregates(ledger) -> None:
    """Per-item value is the exact Decimal sum across PV lines."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "Wire", 1.0, 100.0),
            (date(2025, 2, 1), "P2", "Acme", "Wire", 1.0, 50.0),
        ]
    )
    out = build_abc_classification(pv, Settings()).collect()

    assert out.schema["annual_value"] == pl.Decimal(precision=38, scale=4)
    assert out.row(0, named=True)["annual_value"] == Decimal("150.0000")


def test_abc_cumulative_percentage_is_monotonic(ledger) -> None:
    """The cumulative curve climbs to 1.0 at the last (lowest-value) item."""
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "A", 1.0, 600.0),
            (date(2025, 1, 1), "P2", "Acme", "B", 1.0, 300.0),
            (date(2025, 1, 1), "P3", "Acme", "C", 1.0, 100.0),
        ]
    )
    out = build_abc_classification(pv, Settings()).collect()
    cum = out["cumulative_percentage"].to_list()

    assert cum == sorted(cum)  # non-decreasing
    assert abs(cum[-1] - 1.0) < 1e-9


def test_abc_respects_configured_thresholds(ledger) -> None:
    """Custom cut-points move the band boundaries."""
    cfg = Settings(abc_a_threshold=0.5, abc_b_threshold=0.9)
    pv = ledger(
        [
            (date(2025, 1, 1), "P1", "Acme", "High", 1.0, 600.0),
            (date(2025, 1, 1), "P2", "Acme", "Low", 1.0, 400.0),
        ]
    )
    out = build_abc_classification(pv, cfg).collect()
    by_item = {r["item"]: r["abc_class"] for r in out.iter_rows(named=True)}

    # High alone = 0.60 > 0.50 a-threshold -> B; cumulative 1.0 > 0.9 -> C.
    assert by_item["High"] == AbcClass.B.value
    assert by_item["Low"] == AbcClass.C.value


# --- SBC ------------------------------------------------------------------


def test_sbc_smooth_low_adi_low_cv2() -> None:
    """Regular, even-sized demand classifies as smooth."""
    rows = [("Acme", "Wire", date(2025, m, 1), 10.0) for m in range(1, 7)]
    out = classify_sbc(_demand(rows)).collect().row(0, named=True)

    assert out["adi"] == 1.0  # demand every month
    assert out["cv_squared"] == 0.0  # identical sizes
    assert out["demand_class"] == SbcClass.SMOOTH.value


def test_sbc_erratic_low_adi_high_cv2() -> None:
    """Frequent demand with volatile sizes classifies as erratic."""
    sizes = [1.0, 50.0, 2.0, 80.0, 3.0, 100.0]
    rows = [("Acme", "Wire", date(2025, m, 1), sizes[m - 1]) for m in range(1, 7)]
    out = classify_sbc(_demand(rows)).collect().row(0, named=True)

    assert out["adi"] < 1.32
    assert out["cv_squared"] >= 0.49
    assert out["demand_class"] == SbcClass.ERRATIC.value


def test_sbc_intermittent_high_adi_low_cv2() -> None:
    """Sparse demand with even sizes classifies as intermittent."""
    # Demand in 3 of 9 months, all equal size -> ADI=3, CV2=0.
    rows = [
        ("Acme", "Wire", date(2025, 1, 1), 10.0),
        ("Acme", "Wire", date(2025, 4, 1), 10.0),
        ("Acme", "Wire", date(2025, 7, 1), 10.0),
    ]
    out = classify_sbc(_demand(rows)).collect().row(0, named=True)

    assert out["adi"] >= 1.32
    assert out["cv_squared"] < 0.49
    assert out["demand_class"] == SbcClass.INTERMITTENT.value


def test_sbc_lumpy_high_adi_high_cv2() -> None:
    """Sparse demand with volatile sizes classifies as lumpy."""
    rows = [
        ("Acme", "Wire", date(2025, 1, 1), 2.0),
        ("Acme", "Wire", date(2025, 5, 1), 90.0),
        ("Acme", "Wire", date(2025, 9, 1), 5.0),
    ]
    out = classify_sbc(_demand(rows)).collect().row(0, named=True)

    assert out["adi"] >= 1.32
    assert out["cv_squared"] >= 0.49
    assert out["demand_class"] == SbcClass.LUMPY.value


def test_sbc_densifies_zero_months_into_adi() -> None:
    """Gaps between observed months count as zero-demand months in ADI."""
    # Two observations 6 months apart -> grid of 6 months, 2 active -> ADI=3.0.
    rows = [
        ("Acme", "Wire", date(2025, 1, 1), 10.0),
        ("Acme", "Wire", date(2025, 6, 1), 10.0),
    ]
    out = classify_sbc(_demand(rows)).collect().row(0, named=True)

    assert out["adi"] == 3.0


def test_sbc_single_observation_has_zero_cv2() -> None:
    """A lone observation has undefined sample std; CV2 defaults to 0."""
    rows = [("Acme", "Wire", date(2025, 1, 1), 10.0)]
    out = classify_sbc(_demand(rows)).collect().row(0, named=True)

    assert out["cv_squared"] == 0.0
