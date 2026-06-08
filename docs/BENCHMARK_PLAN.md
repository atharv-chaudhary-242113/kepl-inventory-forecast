# Benchmark Plan — Python Engine vs Rust Core

## Goal
Decide, with measurements rather than opinion, whether the Rust core earns its
complexity for this workload. Both branches implement the same `DOMAIN_RULES.md`
and emit the same `WORKBOOK_SCHEMA.md`, so they are directly comparable.

## What We Measure

| Dimension          | Metric                                                         |
| ------------------ | -------------------------------------------------------------- |
| Throughput         | Full-pipeline wall time at 5k / 20k / 50k rows per file        |
| Per-stage time     | ingest, demand, classify, forecast, analytics, write           |
| Workbook load      | validate + Dashboard_Cache load wall time                      |
| Peak memory        | RSS high-water mark during the full pipeline                   |
| Cold start         | process start → first dashboard paint                          |
| Build / deploy     | clean build time; installer size                              |
| Maintainability    | LOC; module count; number of languages and toolchains          |

## Method
1. **Fixtures.** Synthetic datasets at each size, committed and content-hashed so
   runs are comparable over time.
2. **Environment.** Same machine, plugged in, no competing load. Five runs per
   measurement; report median and interquartile range, not a single best run.
3. **Harness.** Python via `pytest tests/benchmarks --benchmark-only`; Rust via the
   existing `phase3_builders_test` harness extended with timing.
4. **Like-for-like forecasting.** Compare the same models (ETS, Theta, Croston-SBA,
   TSB) on identical series, scored with MASE/RMSSE; never a fast Python model
   against a slow Rust one.
5. **JIT isolation.** numba warmup is timed and reported separately from
   steady-state forecasting throughput.

## Correctness Gate (precedes all timing)
Before any timing counts, both engines must produce **identical** classifications,
forecasts, risk scores, and financial figures on the fixtures (within a documented
floating-point tolerance for the forecasting numerics). A faster engine that
disagrees on the numbers has not won anything.

## Honest Interpretation
- If Python comes within a comfortable margin of every target in
  `PERFORMANCE_BUDGET.md`, the single-language build wins on maintainability and
  deployment — even with a raw-speed gap.
- Rust "wins" only if it clears a target Python misses, or beats Python by a margin
  a *user* would feel — not on a microbenchmark in isolation.
- Maintainability and deployment cost are weighed alongside speed, not as an
  afterthought.

## Output
A results table in `benchmarks/README.md`, updated as each roadmap phase lands,
ending in a one-paragraph, evidence-based recommendation on whether the Rust core
is worth keeping for this product.