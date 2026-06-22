"""SBC-routed demand forecasting (Phase-3 forecast engine).

DOMAIN_RULES.md ("Forecast Routing") routes each item's monthly demand series by
its Syntetos-Boylan class and selects the per-class winner by backtested accuracy
against naive baselines:

    smooth / erratic  -> AutoETS or AutoTheta
    intermittent      -> TSB (benchmarked vs Croston-SBA)
    lumpy             -> TSB / Croston-SBA

Every series is also scored against Naive / SeasonalNaive / SES baselines, and the
model with the lowest MASE (rolling-origin cross-validation) wins (ADR-007,
API_CONTRACT.md `forecast_demand`). This module is *almost* pure over Polars: the
only non-Polars step is handing each densified series to statsforecast, whose
output is read straight back into Polars (Constitution Rule 3; ADR-006/007).

Three series tiers keep the statsforecast call safe across the very uneven
history lengths real ERP data produces:

    selected : long enough for cross-validation  -> CV picks the model
    fallback : fittable but too short for CV      -> class-default model, no CV
    trivial  : too short to fit at all            -> Naive last-value, no model fit

Determinism (Constitution Rule 9): every model is parameter-fixed or
auto-optimised on the data only, statsforecast runs single-threaded (`n_jobs=1`),
and all tie-breaks are by an explicit, stable ordering — no wall-clock, no
dict-order, no unseeded randomness.
"""

from __future__ import annotations

import polars as pl
from statsforecast import StatsForecast
from statsforecast.models import (
    TSB,
    AutoETS,
    AutoTheta,
    CrostonSBA,
    Naive,
    SeasonalNaive,
    SimpleExponentialSmoothingOptimized,
)

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.domain import ForecastModel, SbcClass

# --- Constants ------------------------------------------------------------

# Monthly grid (Demand_History granularity, WORKBOOK_SCHEMA.md) and the seasonal
# cycle length that goes with it. statsforecast takes the polars-style interval.
_MONTHLY: str = "1mo"
_SEASON_LENGTH: int = 12

# Money stays Decimal at the output boundary (THREAT_MODEL.md "Floating-Point
# Errors"); the ingestion money scale is 4 (ingestion/schema.py MONEY_SCALE).
_MONEY: pl.Decimal = pl.Decimal(scale=4)

# A control character that cannot occur inside a supplier or item string, used to
# pack (supplier, item) into statsforecast's single `unique_id` and split it back
# afterwards. `+` (not concat_str) keeps us off the feature-gated string API.
_KEY_SEP: str = "\x01"

# Series-length tiers (see module docstring). Tuned conservatively; raise these if
# you have longer histories and want stricter selection.
_MIN_FIT_LEN: int = 3  # below this, no model is fit — pure last-value naive.
_MIN_CV_LEN: int = 8  # below this, fit but do not cross-validate (no selection).

# Rolling-origin CV geometry. cv_h is clamped to the requested horizon so a tiny
# horizon does not demand more history than it needs.
_CV_WINDOWS: int = 2
_MAX_CV_H: int = 3

# A no-backtest confidence for fallback/trivial series. It is *not* a quality
# claim — there was no backtest — so it is deliberately middling and the actual
# substitution is recorded in `model_used` so dashboards never misreport it.
_FALLBACK_CONFIDENCE: float = 0.5

# statsforecast alias -> the model set we run once for every series. Explicit
# aliases make the returned column names stable to read back.
_MODEL_ALIASES: tuple[str, ...] = (
    "AutoETS",
    "AutoTheta",
    "CrostonSBA",
    "TSB",
    "Naive",
    "SeasonalNaive",
    "SESOpt",
)

# Class -> the candidate models that class is *allowed* to be served by. Baselines
# are always added to every series' selection pool below.
_CLASS_CANDIDATES: dict[str, tuple[str, ...]] = {
    SbcClass.SMOOTH.value: ("AutoETS", "AutoTheta"),
    SbcClass.ERRATIC.value: ("AutoETS", "AutoTheta"),
    SbcClass.INTERMITTENT.value: ("TSB", "CrostonSBA"),
    SbcClass.LUMPY.value: ("TSB", "CrostonSBA"),
}
_BASELINES: tuple[str, ...] = ("Naive", "SeasonalNaive", "SESOpt")

# The single model a fallback (no-CV) series of each class gets — the first
# candidate for the class, i.e. the documented primary model for that quadrant.
_CLASS_DEFAULT: dict[str, str] = {
    cls: cands[0] for cls, cands in _CLASS_CANDIDATES.items()
}
# A series with no SBC class (absent from the SBC frame) routes through baselines
# only; its fallback default is the plain Naive.
_NULL_CLASS: str = "__missing_sbc_class__"
_NULL_CLASS_DEFAULT: str = "Naive"

# alias -> the model label written to the Forecasts sheet. SES has no enum member
# (it is baseline-only), so it maps to a literal; everything else uses the enum.
_ALIAS_TO_MODEL: dict[str, str] = {
    "AutoETS": ForecastModel.AUTO_ETS.value,
    "AutoTheta": ForecastModel.THETA.value,
    "CrostonSBA": ForecastModel.CROSTON_SBA.value,
    "TSB": ForecastModel.TSB.value,
    "Naive": ForecastModel.NAIVE.value,
    "SeasonalNaive": ForecastModel.SEASONAL_NAIVE.value,
    "SESOpt": "ses",
}

# Deterministic tie-break priority for model selection (Constitution Rule 9): when
# two models tie on MASE, the earlier alias here wins. Class-specific models are
# preferred over baselines.
_ALIAS_PRIORITY: dict[str, int] = {a: i for i, a in enumerate(_MODEL_ALIASES)}

# Output column order — the Forecasts sheet contract (WORKBOOK_SCHEMA.md).
_OUTPUT_SCHEMA: dict[str, pl.datatypes.DataTypeClass | pl.Decimal] = {
    "supplier": pl.Utf8,
    "item": pl.Utf8,
    "forecast_period": pl.Date,
    "forecast_quantity": pl.Float64,
    "forecast_value": _MONEY,
    "trend_component": pl.Float64,
    "seasonal_component": pl.Float64,
    "model_used": pl.Utf8,
    "confidence_score": pl.Float64,
}


def forecast_demand(
    demand: pl.LazyFrame,
    sbc: pl.LazyFrame,
    horizon: int,
    cfg: Settings,
) -> pl.LazyFrame:
    """Produce a per-item demand forecast routed by Syntetos-Boylan class.

    Args:
        demand: The monthly Demand_History frame from ``reconstruct_demand``
            (``[period, supplier, item, demand_quantity, demand_value]``).
        sbc: The SBC classification frame from ``classify_sbc``
            (``[supplier, item, adi, cv_squared, demand_class]``); supplies each
            item's routing class.
        horizon: Number of future monthly periods to forecast (``cfg`` carries the
            same value; passed explicitly so the function is self-describing).
        cfg: Run settings (currently unused beyond ``horizon`` validation, kept in
            the signature so the routing policy can become configurable without a
            contract change).

    Returns:
        A LazyFrame ``[supplier, item, forecast_period(Date),
        forecast_quantity(Float64), forecast_value(Decimal), trend_component,
        seasonal_component, model_used(Utf8), confidence_score(Float64)]`` — the
        Forecasts sheet contract (WORKBOOK_SCHEMA.md). One row per (item, future
        month). ``forecast_quantity`` is clipped at zero (demand cannot be
        negative); ``forecast_value`` is the quantity at the item's value-weighted
        unit cost, kept Decimal-exact; ``model_used`` records the *actual* model
        that produced the row (so HW/baseline substitutions never misreport).
    """
    _ = cfg  # reserved for future configurable routing thresholds.
    dem = demand.collect()
    if dem.height == 0:
        return _empty_output().lazy()

    classes = sbc.select(["supplier", "item", "demand_class"]).collect()

    # Pack the two-part key, densify to a gap-free monthly grid (a month with no
    # POV is a real zero-demand month, not a missing one), and record each key's
    # supplier/item and value-weighted unit cost for reassembly later.
    long = _build_long_frame(dem)
    key_map = _key_attributes(dem)

    lengths = long.group_by("unique_id").agg(pl.len().alias("n"))
    long = long.join(lengths, on="unique_id", how="left")

    trivial = long.filter(pl.col("n") < _MIN_FIT_LEN)
    fittable = long.filter(pl.col("n") >= _MIN_FIT_LEN)

    chosen = _select_models(fittable, classes, horizon)
    fitted = _forecast_fitted(fittable, chosen, horizon)
    trivial_fc = _forecast_trivial(trivial, horizon)

    forecasts = pl.concat([fitted, trivial_fc], how="vertical")
    components = _trend_and_seasonal(long)

    out = _assemble(forecasts, components, key_map)
    return out.lazy()


# --- Frame preparation ----------------------------------------------------


def _build_long_frame(dem: pl.DataFrame) -> pl.DataFrame:
    """Pack the key and densify each series to a contiguous monthly grid.

    Returns ``[unique_id, ds(Date), y(Float64)]`` sorted by (key, ds), with a
    zero-demand row inserted for every month between an item's first and last
    observed demand. Sorting here is what lets the later one-step ``diff`` (the
    MASE scale) and the trend index follow chronological order.
    """
    keyed = dem.select(
        # `+` over concat_str avoids the feature-gated string-concat API.
        (pl.col("supplier") + pl.lit(_KEY_SEP) + pl.col("item")).alias("unique_id"),
        pl.col("period").alias("ds"),
        pl.col("demand_quantity").alias("y"),
    )

    grid = (
        keyed.group_by("unique_id")
        .agg(
            pl.col("ds").min().alias("_start"),
            pl.col("ds").max().alias("_end"),
        )
        .with_columns(
            pl.date_ranges(pl.col("_start"), pl.col("_end"), interval=_MONTHLY).alias(
                "ds"
            )
        )
        .explode("ds")
        .select(["unique_id", "ds"])
    )

    return (
        grid.join(keyed, on=["unique_id", "ds"], how="left")
        .with_columns(pl.col("y").fill_null(0.0))
        .sort(["unique_id", "ds"])
    )


def _key_attributes(dem: pl.DataFrame) -> pl.DataFrame:
    """Map each key back to (supplier, item) and its value-weighted unit cost.

    ``unit_value`` is ``sum(demand_value) / sum(demand_quantity)`` per item, kept
    Decimal (cast quantity into Decimal space first so the division does not
    silently downcast to Float64). It turns a forecast *quantity* into a forecast
    *value* at the output boundary. A zero-quantity item yields a null unit cost,
    coalesced to zero downstream.
    """
    return (
        dem.group_by(["supplier", "item"])
        .agg(
            pl.col("demand_value").sum().alias("_value"),
            pl.col("demand_quantity").sum().alias("_qty"),
        )
        .with_columns(
            (pl.col("supplier") + pl.lit(_KEY_SEP) + pl.col("item")).alias("unique_id"),
            pl.when(pl.col("_qty") > 0)
            .then(pl.col("_value") / pl.col("_qty").cast(_MONEY))
            .otherwise(None)
            .alias("unit_value"),
        )
        .select(["unique_id", "supplier", "item", "unit_value"])
    )


# --- Model selection (rolling-origin MASE) --------------------------------


def _select_models(
    fittable: pl.DataFrame,
    classes: pl.DataFrame,
    horizon: int,
) -> pl.DataFrame:
    """Choose one model per key: CV-backtested where possible, class-default else.

    Returns ``[unique_id, model_alias, confidence_score]``. Keys with enough
    history are cross-validated and the lowest-MASE model (restricted to the
    class-allowed pool plus baselines) wins, with confidence ``1/(1+MASE)``. Keys
    too short for CV fall back to their class default at a no-backtest confidence.
    """
    key_class = (
        fittable.select(["unique_id", "n"])
        .unique()
        .join(_key_to_class(fittable, classes), on="unique_id", how="left")
    )

    eligible = key_class.filter(pl.col("n") >= _MIN_CV_LEN)
    fallback = key_class.filter(pl.col("n") < _MIN_CV_LEN)

    selected = _select_by_cv(fittable, eligible, horizon)
    fb = fallback.with_columns(
        # Null class -> baselines only -> plain Naive; otherwise the class primary.
        pl.col("demand_class")
        .replace_strict(_CLASS_DEFAULT, default=_NULL_CLASS_DEFAULT)
        .alias("model_alias"),
        pl.lit(_FALLBACK_CONFIDENCE).alias("confidence_score"),
    ).select(["unique_id", "model_alias", "confidence_score"])

    return pl.concat([selected, fb], how="vertical")


def _key_to_class(fittable: pl.DataFrame, classes: pl.DataFrame) -> pl.DataFrame:
    """Resolve each key's SBC class from the (supplier, item) classification."""
    keyed_class = classes.with_columns(
        (pl.col("supplier") + pl.lit(_KEY_SEP) + pl.col("item")).alias("unique_id")
    ).select(["unique_id", "demand_class"])
    return (
        fittable.select("unique_id")
        .unique()
        .join(keyed_class, on="unique_id", how="left")
    )


def _select_by_cv(
    fittable: pl.DataFrame,
    eligible: pl.DataFrame,
    horizon: int,
) -> pl.DataFrame:
    """Backtest the eligible keys and pick the lowest-MASE allowed model each."""
    if eligible.height == 0:
        return _empty_selection()

    eligible_long = fittable.join(
        eligible.select("unique_id"), on="unique_id", how="semi"
    )
    cv_h = min(horizon, _MAX_CV_H)

    sf = StatsForecast(models=_build_models(), freq=_MONTHLY, n_jobs=1)
    cv = _as_polars(
        sf.cross_validation(
            df=eligible_long.select(["unique_id", "ds", "y"]),
            h=cv_h,
            n_windows=_CV_WINDOWS,
            step_size=1,
        )
    )

    # Per (key, model) mean absolute error across all CV points, melted long.
    errors = (
        cv.unpivot(
            index=["unique_id", "y"],
            on=list(_MODEL_ALIASES),
            variable_name="model_alias",
            value_name="pred",
        )
        .with_columns((pl.col("y") - pl.col("pred")).abs().alias("abs_err"))
        .group_by(["unique_id", "model_alias"])
        .agg(pl.col("abs_err").mean().alias("mae"))
    )

    scale = _naive_scale(eligible_long)
    mase = (
        errors.join(scale, on="unique_id", how="left")
        # MASE = mean abs forecast error / mean abs one-step naive error.
        .with_columns((pl.col("mae") / pl.col("scale")).alias("mase"))
        .join(
            eligible.select(["unique_id", "demand_class"]), on="unique_id", how="left"
        )
        .with_columns(pl.col("demand_class").fill_null(_NULL_CLASS))
        # Keep only models this key's class is allowed to use (candidates + baselines).
        .join(_allowed_pool(), on=["demand_class", "model_alias"], how="semi")
        .with_columns(
            pl.col("model_alias")
            .replace_strict(_ALIAS_PRIORITY, default=len(_ALIAS_PRIORITY))
            .alias("_prio")
        )
        # Lowest MASE wins; ties break by the stable priority order (Rule 9).
        .sort(["unique_id", "mase", "_prio"])
        .group_by("unique_id", maintain_order=True)
        .first()
        .with_columns(
            # Bounded, monotone-decreasing in error: a perfect backtest -> 1.0,
            # a MASE of 1 (no better than naive) -> 0.5, and so on. Not hardcoded.
            (1.0 / (1.0 + pl.col("mase").fill_null(1.0))).alias("confidence_score")
        )
        .select(["unique_id", "model_alias", "confidence_score"])
    )
    return mase


def _naive_scale(long: pl.DataFrame) -> pl.DataFrame:
    """Per-key MASE denominator: mean absolute one-step (naive) difference.

    A constant series has a zero difference scale, which would divide by zero, so
    we fall back to the mean absolute level, and finally to 1.0, keeping MASE
    finite and the ranking well-defined.
    """
    return (
        long.sort(["unique_id", "ds"])
        .group_by("unique_id")
        .agg(
            pl.col("y").diff().abs().mean().alias("_diff_scale"),
            pl.col("y").abs().mean().alias("_level_scale"),
        )
        .with_columns(
            pl.max_horizontal(
                pl.coalesce(
                    [
                        pl.col("_diff_scale"),
                        pl.col("_level_scale"),
                        pl.lit(1.0),
                    ]
                ),
                pl.lit(1e-9),
            ).alias("scale")
        )
        .select(["unique_id", "scale"])
    )


def _allowed_pool() -> pl.DataFrame:
    """(demand_class, model_alias) pairs each class may be served by.

    Built from candidates + baselines, with an extra null-class row group so an
    item missing from the SBC frame still has a baseline-only pool. Null join keys
    do not match in Polars, so missing classes are represented internally with
    ``_NULL_CLASS``.
    """
    rows: list[tuple[str | None, str]] = []
    for cls, cands in _CLASS_CANDIDATES.items():
        for alias in (*cands, *_BASELINES):
            rows.append((cls, alias))
    for alias in _BASELINES:
        rows.append((_NULL_CLASS, alias))
    return pl.DataFrame(
        {
            "demand_class": [r[0] for r in rows],
            "model_alias": [r[1] for r in rows],
        },
        schema={"demand_class": pl.Utf8, "model_alias": pl.Utf8},
    )


# --- Forecast generation --------------------------------------------------


def _forecast_fitted(
    fittable: pl.DataFrame,
    chosen: pl.DataFrame,
    horizon: int,
) -> pl.DataFrame:
    """Fit all models on every fittable key, then keep each key's chosen column.

    A single full-data fit produces the horizon for every model; we then pick, per
    key, the column named by the model selection. Negative forecasts are clipped
    to zero (demand cannot be negative).
    """
    if fittable.height == 0:
        return _empty_forecast()

    sf = StatsForecast(models=_build_models(), freq=_MONTHLY, n_jobs=1)
    wide = _as_polars(
        sf.forecast(df=fittable.select(["unique_id", "ds", "y"]), h=horizon)
    )

    return (
        wide.unpivot(
            index=["unique_id", "ds"],
            on=list(_MODEL_ALIASES),
            variable_name="model_alias",
            value_name="forecast_quantity",
        )
        # Inner-join on (key, alias) keeps only the selected model's rows per key.
        .join(chosen, on=["unique_id", "model_alias"], how="inner")
        .with_columns(
            pl.col("forecast_quantity").clip(lower_bound=0.0).alias("forecast_quantity")
        )
        .select(
            [
                "unique_id",
                pl.col("ds").alias("forecast_period"),
                "forecast_quantity",
                "model_alias",
                "confidence_score",
            ]
        )
    )


def _forecast_trivial(trivial: pl.DataFrame, horizon: int) -> pl.DataFrame:
    """Forecast too-short series as the last observed value, repeated `horizon`.

    These series cannot support a fitted model, so the honest forecast is a flat
    naive carry-forward of the latest demand. Recorded as the Naive model at the
    no-backtest confidence so dashboards do not over-trust them.
    """
    if trivial.height == 0:
        return _empty_forecast()

    last = (
        trivial.sort(["unique_id", "ds"])
        .group_by("unique_id", maintain_order=True)
        .agg(
            pl.col("y").last().alias("forecast_quantity"),
            pl.col("ds").max().alias("_last_period"),
        )
    )
    # Generate the next `horizon` month-starts after each key's last period.
    return (
        last.with_columns(
            pl.date_ranges(
                pl.col("_last_period").dt.offset_by(_MONTHLY),
                pl.col("_last_period").dt.offset_by(f"{horizon}mo"),
                interval=_MONTHLY,
            ).alias("forecast_period")
        )
        .explode("forecast_period")
        .with_columns(
            pl.col("forecast_quantity")
            .clip(lower_bound=0.0)
            .alias("forecast_quantity"),
            pl.lit("Naive").alias("model_alias"),
            pl.lit(_FALLBACK_CONFIDENCE).alias("confidence_score"),
        )
        .select(
            [
                "unique_id",
                "forecast_period",
                "forecast_quantity",
                "model_alias",
                "confidence_score",
            ]
        )
    )


def _build_models() -> list[object]:
    """Instantiate the full candidate + baseline model set (fixed/auto params).

    Every model is either parameter-free, optimised on the data, or carries fixed
    smoothing constants — no source of run-to-run nondeterminism (Rule 9). TSB's
    decay constants (0.1) are conventional starting values; a future increment can
    optimise them per series.
    """
    return [
        AutoETS(season_length=_SEASON_LENGTH, alias="AutoETS"),
        AutoTheta(season_length=_SEASON_LENGTH, alias="AutoTheta"),
        CrostonSBA(alias="CrostonSBA"),
        TSB(alpha_d=0.1, alpha_p=0.1, alias="TSB"),
        Naive(alias="Naive"),
        SeasonalNaive(season_length=_SEASON_LENGTH, alias="SeasonalNaive"),
        SimpleExponentialSmoothingOptimized(alias="SESOpt"),
    ]


def _as_polars(frame: object) -> pl.DataFrame:
    """Coerce a statsforecast result (polars *or* pandas) to a polars DataFrame.

    statsforecast returns the same frame flavour it was handed, but its declared
    return type is a polars|pandas union. Pinning it to polars here keeps the rest
    of the module Polars-only (Constitution Rule 3) and resolves the union at the
    one place it legitimately appears — the statsforecast boundary (ADR-006).
    """
    if isinstance(frame, pl.DataFrame):
        return frame
    # Only reached if a statsforecast build returns pandas; convert at the seam.
    import pandas as pd  # transient, statsforecast-boundary only (DEPENDENCY_POLICY).

    if isinstance(frame, pd.DataFrame):
        return pl.from_pandas(frame)
    msg = f"unexpected statsforecast return type: {type(frame)!r}"
    raise TypeError(msg)


# --- Trend & seasonal components -----------------------------------------


def _trend_and_seasonal(long: pl.DataFrame) -> pl.DataFrame:
    """Deterministic trend slope per key and per-month seasonal deviation.

    A lightweight decomposition of the *historical* series, attached to each
    forecast row so the Forecasts sheet carries real components rather than the
    1.0 placeholder the Rust review flagged:

      * trend_component: the OLS slope of demand on a 0-based month index — the
        marginal monthly trend (units/month). Constant for an item across the
        horizon. Zero when the series is a single point (slope undefined).
      * seasonal_component: the additive deviation of each calendar month from the
        item's overall mean, but only for items with at least one full year of
        history; shorter items get 0 (seasonality is not yet identifiable).

    Returns ``[unique_id, month(Int), trend_component, seasonal_component]`` (one
    row per key-month that occurs); forecast rows left-join and fill 0 on a miss.
    """
    indexed = long.with_columns(
        pl.int_range(pl.len()).over("unique_id").cast(pl.Float64).alias("_t"),
        pl.col("ds").dt.month().alias("month"),
    )

    # OLS slope via the closed form: (n*Σty - Σt*Σy) / (n*Σt² - (Σt)²).
    trend = (
        indexed.group_by("unique_id")
        .agg(
            pl.len().cast(pl.Float64).alias("_n"),
            pl.col("_t").sum().alias("_st"),
            pl.col("y").sum().alias("_sy"),
            (pl.col("_t") * pl.col("y")).sum().alias("_sty"),
            (pl.col("_t") ** 2).sum().alias("_stt"),
        )
        .with_columns(
            (pl.col("_n") * pl.col("_stt") - pl.col("_st") ** 2).alias("_denom")
        )
        .with_columns(
            pl.when(pl.col("_denom") > 0)
            .then(
                (pl.col("_n") * pl.col("_sty") - pl.col("_st") * pl.col("_sy"))
                / pl.col("_denom")
            )
            .otherwise(0.0)
            .alias("trend_component")
        )
        .select(["unique_id", "trend_component"])
    )

    overall = indexed.group_by("unique_id").agg(
        pl.col("y").mean().alias("_overall_mean"),
        pl.len().alias("_n"),
    )
    seasonal = (
        indexed.group_by(["unique_id", "month"])
        .agg(pl.col("y").mean().alias("_month_mean"))
        .join(overall, on="unique_id", how="left")
        .with_columns(
            # Seasonality only once a full cycle of history exists; else 0.
            pl.when(pl.col("_n") >= _SEASON_LENGTH)
            .then(pl.col("_month_mean") - pl.col("_overall_mean"))
            .otherwise(0.0)
            .alias("seasonal_component")
        )
        .select(["unique_id", "month", "seasonal_component"])
    )

    return seasonal.join(trend, on="unique_id", how="left")


# --- Assembly -------------------------------------------------------------


def _assemble(
    forecasts: pl.DataFrame,
    components: pl.DataFrame,
    key_map: pl.DataFrame,
) -> pl.DataFrame:
    """Join components, value, and (supplier, item) onto the chosen forecasts."""
    return (
        forecasts.with_columns(pl.col("forecast_period").dt.month().alias("month"))
        .join(components, on=["unique_id", "month"], how="left")
        .join(key_map, on="unique_id", how="left")
        .with_columns(
            pl.col("trend_component").fill_null(0.0),
            pl.col("seasonal_component").fill_null(0.0),
            # forecast_value = forecast_quantity * unit_value, kept Decimal. Cast
            # the float quantity into Decimal space first so the product never
            # accumulates currency in float; coalesce a missing unit cost to 0.
            (
                pl.col("forecast_quantity").cast(_MONEY)
                * pl.coalesce([pl.col("unit_value"), pl.lit(0, dtype=_MONEY)])
            )
            .cast(_MONEY)
            .alias("forecast_value"),
            # Map the statsforecast alias to the canonical sheet model label.
            pl.col("model_alias")
            .replace_strict(_ALIAS_TO_MODEL, default="unknown")
            .alias("model_used"),
        )
        .select(
            [
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
        )
        .sort(["supplier", "item", "forecast_period"])
    )


# --- Empty-frame builders (correct schema for empty inputs) ---------------


def _empty_output() -> pl.DataFrame:
    """The Forecasts contract with zero rows (empty demand input)."""
    return pl.DataFrame(schema=_OUTPUT_SCHEMA)


def _empty_forecast() -> pl.DataFrame:
    """Empty intermediate forecast frame (no fittable / no trivial series)."""
    return pl.DataFrame(
        schema={
            "unique_id": pl.Utf8,
            "forecast_period": pl.Date,
            "forecast_quantity": pl.Float64,
            "model_alias": pl.Utf8,
            "confidence_score": pl.Float64,
        }
    )


def _empty_selection() -> pl.DataFrame:
    """Empty model-selection frame (no CV-eligible series)."""
    return pl.DataFrame(
        schema={
            "unique_id": pl.Utf8,
            "model_alias": pl.Utf8,
            "confidence_score": pl.Float64,
        }
    )
