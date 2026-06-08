# ADR-007 — statsforecast for Demand Forecasting

## Status
Accepted.

## Context
`DOMAIN_RULES.md` routes forecasting by Syntetos–Boylan class: smooth/erratic toward
standard models, intermittent/lumpy toward Teunter–Syntetos–Babai (TSB). We have
many short per-item series, need a Holt-Winters baseline plus Croston/TSB, want fast
execution across thousands of items, and require determinism.

## Decision
Use Nixtla's statsforecast as the forecasting library, with the model routed by
Syntetos–Boylan class and the per-class winner chosen by backtested accuracy:
- Smooth/erratic → AutoETS (or Theta).
- Intermittent → TSB, benchmarked against Croston-SBA.
- Lumpy → TSB / Croston-SBA, output expressed as a lead-time demand distribution
  feeding the reorder point.
- All classes scored against Naive/SeasonalNaive/SES baselines using MASE/RMSSE.
  scikit-learn (or LightGBM) is retained only as an optional global ML challenger in
  the benchmark, never as a per-class default. Random Forest per class is dropped:
  it cannot extrapolate trend and overfits short per-item series.

## Alternatives Considered
- **statsmodels.** Solid Holt-Winters, but slower across many series and lacks
  first-class intermittent-demand models.
- **Hand-rolled Croston/TSB.** Full control, but reinvents tested numerics and
  costs maintenance for no clear gain.
- **statsforecast (chosen).** numba-compiled, fast across many short series, TSB and
  Croston are first-class — exactly our intermittent/lumpy path — and deterministic.

## Consequences
**Benefits:** numba-compiled models, fast at scale; TSB/Croston built in;
deterministic given fixed seeds and inputs.

**Tradeoffs:** numba adds a one-time JIT compile cost per process (warmed at app
startup so users don't pay it on first run); adds NumPy/pandas to the dependency
tree, but only at the forecasting call site.