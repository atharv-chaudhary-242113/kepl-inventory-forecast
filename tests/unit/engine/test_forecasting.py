"""Tests for ``forecast_demand`` (engine/forecasting.py).

These run statsforecast for real (so the suite exercises the same numba-compiled
models the pipeline uses), but assertions target *invariants* rather than exact
forecast values: schema/contract, horizon length, non-negativity, SBC routing into
the allowed model pool, the Decimal value arithmetic, the three series tiers
(selected / fallback / trivial), and the trend/seasonal components. Exact point
forecasts are model-internal and deliberately not asserted.
"""

from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from opstools.inventory_forecast.config.settings import Settings
from opstools.inventory_forecast.engine.forecasting import _as_polars, forecast_demand

# Labels each SBC class is allowed to be served by (class candidates + baselines),
# mirroring _CLASS_CANDIDATES + _BASELINES mapped through _ALIAS_TO_MODEL.
_BASELINE_LABELS = {"naive", "seasonal_naive", "ses"}
_SMOOTH_LABELS = {"auto_ets", "theta"} | _BASELINE_LABELS
_INTERMITTENT_LABELS = {"tsb", "croston_sba"} | _BASELINE_LABELS

_OUTPUT_COLUMNS = [
    "supplier",
    "item",
    "forecast_period",
    "forecast_quantity",
    "forecast_value",
    "trend_component",
    "seasonal_component",
    "model_used",
    "confidence_score",
]


# --- Builders -------------------------------------------------------------


def _month(offset: int, *, year: int = 2023, month: int = 1) -> date:
    """Return the month-start `offset` months after (year, month), 0-based."""
    total = (year * 12 + (month - 1)) + offset
    y, m = divmod(total, 12)
    return date(y, m + 1, 1)


def _demand(
    rows: list[tuple[str, str, date, float]],
    *,
    price: float = 10.0,
) -> pl.LazyFrame:
    """Build a monthly Demand_History frame ``(supplier, item, period, qty)``.

    demand_value is derived as ``qty * price`` so the value-weighted unit cost is a
    constant ``price`` — letting tests assert forecast_value = quantity * price.
    """
    return pl.LazyFrame(
        {
            "period": [r[2] for r in rows],
            "supplier": [r[0] for r in rows],
            "item": [r[1] for r in rows],
            "demand_quantity": [r[3] for r in rows],
            "demand_value": [Decimal(str(r[3] * price)) for r in rows],
        },
        schema={
            "period": pl.Date,
            "supplier": pl.Utf8,
            "item": pl.Utf8,
            "demand_quantity": pl.Float64,
            "demand_value": pl.Decimal(scale=4),
        },
    )


def _sbc(rows: list[tuple[str, str, str]]) -> pl.LazyFrame:
    """Build an SBC frame ``(supplier, item, demand_class)``.

    adi/cv_squared are filler — forecast_demand reads only demand_class.
    """
    return pl.LazyFrame(
        {
            "supplier": [r[0] for r in rows],
            "item": [r[1] for r in rows],
            "adi": [1.0 for _ in rows],
            "cv_squared": [0.0 for _ in rows],
            "demand_class": [r[2] for r in rows],
        },
        schema={
            "supplier": pl.Utf8,
            "item": pl.Utf8,
            "adi": pl.Float64,
            "cv_squared": pl.Float64,
            "demand_class": pl.Utf8,
        },
    )


def _smooth_series(
    supplier: str = "Acme",
    item: str = "Wire",
    n: int = 12,
    qty: float = 10.0,
) -> list[tuple[str, str, date, float]]:
    """A regular, even-sized monthly series — long enough for CV selection."""
    return [(supplier, item, _month(m), qty) for m in range(n)]


# --- Contract & basic invariants ------------------------------------------


def test_empty_demand_returns_empty_contract_frame() -> None:
    """No demand input yields an empty frame with the Forecasts schema."""
    empty = pl.LazyFrame(
        schema={
            "period": pl.Date,
            "supplier": pl.Utf8,
            "item": pl.Utf8,
            "demand_quantity": pl.Float64,
            "demand_value": pl.Decimal(scale=4),
        }
    )
    sbc = _sbc([])
    out = forecast_demand(empty, sbc, horizon=3, cfg=Settings()).collect()

    assert out.height == 0
    assert out.columns == _OUTPUT_COLUMNS


def test_output_column_order_matches_contract() -> None:
    """Schema must equal the Forecasts sheet column order."""
    demand = _demand(_smooth_series())
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    assert out.columns == _OUTPUT_COLUMNS


def test_one_row_per_future_month() -> None:
    """Each item produces exactly `horizon` forecast rows."""
    demand = _demand(_smooth_series())
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=4, cfg=Settings()).collect()

    assert out.height == 4


def test_forecast_quantity_is_non_negative() -> None:
    """Demand cannot be negative; forecasts are clipped at zero."""
    demand = _demand(_smooth_series())
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=6, cfg=Settings()).collect()

    assert (out["forecast_quantity"] >= 0.0).all()


def test_forecast_value_dtype_is_decimal() -> None:
    """Forecast value stays Decimal at the output boundary."""
    demand = _demand(_smooth_series())
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    assert out.schema["forecast_value"] == pl.Decimal(scale=4)


def test_forecast_value_is_quantity_times_unit_value() -> None:
    """forecast_value = forecast_quantity * value-weighted unit cost (Decimal)."""
    # Constant price 7.0 -> unit_value is exactly 7.0 for every row.
    demand = _demand(_smooth_series(qty=10.0), price=7.0)
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    for row in out.iter_rows(named=True):
        expected = Decimal(str(row["forecast_quantity"])) * Decimal("7")
        # Compare in Decimal space at the sheet scale (rounding at scale 4).
        assert row["forecast_value"] == expected.quantize(Decimal("0.0001"))


def test_confidence_score_in_unit_interval() -> None:
    """Confidence is a bounded (0, 1] score, never a hardcoded sentinel > 1."""
    demand = _demand(_smooth_series())
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    conf = out["confidence_score"]
    assert (conf > 0.0).all()
    assert (conf <= 1.0).all()


# --- Period continuity ----------------------------------------------------


def test_forecast_periods_are_consecutive_months_after_history() -> None:
    """Forecast months follow the last observed month, one month apart."""
    # 12 months of history: 2023-01f...2023-12.
    demand = _demand(_smooth_series(n=12))
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    periods = out["forecast_period"].to_list()
    assert periods == [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)]


# --- SBC routing ----------------------------------------------------------


def test_smooth_series_routes_within_allowed_pool() -> None:
    """A smooth series is served by an ETS/Theta model or a baseline, never TSB."""
    demand = _demand(_smooth_series(n=12))
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    models = set(out["model_used"].to_list())
    assert models <= _SMOOTH_LABELS


def test_intermittent_series_routes_within_allowed_pool() -> None:
    """A sparse series is served by TSB/Croston or a baseline, never ETS/Theta."""
    # Demand in 3 of 12 months -> intermittent shape, long enough for CV.
    rows = [
        ("Acme", "Wire", _month(0), 10.0),
        ("Acme", "Wire", _month(5), 10.0),
        ("Acme", "Wire", _month(10), 10.0),
    ]
    demand = _demand(rows)
    sbc = _sbc([("Acme", "Wire", "intermittent")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    models = set(out["model_used"].to_list())
    assert models <= _INTERMITTENT_LABELS


def test_missing_sbc_class_routes_through_baselines_only() -> None:
    """An item absent from the SBC frame still forecasts, via baselines only."""
    demand = _demand(_smooth_series(n=12))
    sbc = _sbc([])  # no class for ("Acme", "Wire")
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    assert out.height == 3
    models = set(out["model_used"].to_list())
    assert models <= _BASELINE_LABELS


# --- Series tiers ---------------------------------------------------------


def test_trivial_short_series_is_naive_last_value() -> None:
    """A 2-point series is too short to fit: flat naive carry-forward."""
    rows = [
        ("Acme", "Wire", _month(0), 5.0),
        ("Acme", "Wire", _month(1), 8.0),
    ]
    demand = _demand(rows)
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    assert out.height == 3
    assert out["model_used"].to_list() == ["naive", "naive", "naive"]
    # Last observed demand (8.0) carried forward across the whole horizon.
    assert out["forecast_quantity"].to_list() == [8.0, 8.0, 8.0]
    assert out["forecast_period"].to_list() == [
        date(2023, 3, 1),
        date(2023, 4, 1),
        date(2023, 5, 1),
    ]


def test_model_used_is_a_known_label() -> None:
    """Every emitted model label is a recognised canonical string."""
    demand = _demand(_smooth_series(n=12))
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    known = {
        "auto_ets",
        "theta",
        "croston_sba",
        "tsb",
        "naive",
        "seasonal_naive",
        "ses",
    }
    assert set(out["model_used"].to_list()) <= known


# --- Multiple series ------------------------------------------------------


def test_distinct_items_forecast_independently() -> None:
    """Two items each get their own horizon of forecasts, kept distinct."""
    rows = _smooth_series("Acme", "Wire", n=12) + _smooth_series("Acme", "Bolt", n=12)
    demand = _demand(rows)
    sbc = _sbc(
        [
            ("Acme", "Wire", "smooth"),
            ("Acme", "Bolt", "smooth"),
        ]
    )
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    assert out.height == 6
    counts = out.group_by("item").len().sort("item")
    assert counts["len"].to_list() == [3, 3]  # Bolt, Wire


def test_supplier_and_item_are_part_of_the_key() -> None:
    """The same item under two suppliers stays two independent series."""
    rows = _smooth_series("Acme", "Wire", n=12) + _smooth_series("Globex", "Wire", n=12)
    demand = _demand(rows)
    sbc = _sbc(
        [
            ("Acme", "Wire", "smooth"),
            ("Globex", "Wire", "smooth"),
        ]
    )
    out = forecast_demand(demand, sbc, horizon=2, cfg=Settings()).collect()

    assert set(out["supplier"].to_list()) == {"Acme", "Globex"}
    assert out.height == 4


# --- DataFrame Conversion -------------------------------------------------


def test_as_polars_converts_pandas_dataframe() -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "item_id": ["A"],
            "value": [1.0],
        }
    )

    result = _as_polars(frame)

    assert isinstance(result, pl.DataFrame)
    assert result.shape == (1, 2)


def test_as_polars_rejects_unexpected_type() -> None:
    with pytest.raises(
        TypeError,
        match="unexpected statsforecast return type",
    ):
        _as_polars("not a dataframe")


# --- Components -----------------------------------------------------------


def test_trend_component_is_positive_for_rising_demand() -> None:
    """A linearly increasing series has a positive trend slope."""
    rows = [("Acme", "Wire", _month(m), float(m + 1) * 5.0) for m in range(12)]
    demand = _demand(rows)
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    # Slope is constant across the horizon; check the first row.
    assert out["trend_component"][0] > 0.0


def test_seasonal_component_nonzero_with_full_year_history() -> None:
    """A clearly seasonal 24-month series yields non-flat seasonal deviations."""
    # Alternating high/low by calendar month over two full years.
    rows = [
        ("Acme", "Wire", _month(m), 100.0 if m % 12 < 6 else 10.0) for m in range(24)
    ]
    demand = _demand(rows)
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=12, cfg=Settings()).collect()

    seasonal = out["seasonal_component"].to_list()
    assert any(abs(v) > 1e-9 for v in seasonal)


def test_seasonal_component_zero_for_short_history() -> None:
    """With under a year of history, seasonality is not yet identifiable (0)."""
    demand = _demand(_smooth_series(n=8))  # 8 months < season length
    sbc = _sbc([("Acme", "Wire", "smooth")])
    out = forecast_demand(demand, sbc, horizon=3, cfg=Settings()).collect()

    assert all(abs(v) < 1e-9 for v in out["seasonal_component"].to_list())
