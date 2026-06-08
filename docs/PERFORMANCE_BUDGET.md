# Performance Budget

These targets originate in `ACCEPTANCE_CRITERIA.md` and are the bar both the Python
and Rust builds are measured against. A build that misses a target is not done.

| Operation                          | Target     | Conditions                          |
| ---------------------------------- | ---------- | ----------------------------------- |
| Full processing (~20k rows / file) | < 60 s     | first execution, cold workstation   |
| Workbook load                      | < 5 s      | validate + load Dashboard_Cache     |
| Dashboard startup                  | < 3 s      | after workbook loaded               |
| Filter response                    | < 200 ms   | per interaction, on cached data     |

## Hot Paths and Known Risks

### 1. Filter response (< 200 ms) — tightest budget
Filtering runs on pre-aggregated Polars frames in memory and is fast. The risk is
*rendering*: a full Plotly redraw inside QWebEngineView can exceed 200 ms.
Mitigations, applied in order and only when a profiled chart misses budget:
1. `Plotly.react` to diff the figure instead of redrawing it.
2. Pre-aggregate further in the Dashboard_Cache so figures receive small frames.
3. As a last resort for a specific interactive view, render it with pyqtgraph
   (native, fast) instead of Plotly. This is an escape hatch, not a default, and is
   recorded against the chart it was applied to.

### 2. First-run forecasting — numba JIT warmup
statsforecast triggers a one-time numba compile per process. Warm the models once
at application startup so the user's first real run is not charged the compile cost.
In benchmarks, JIT warmup is reported separately from steady-state throughput.

### 3. Excel write — I/O and formatting bound
Writing 10+ formatted sheets is bound by formatting and I/O, not computation. Build
all frames first, apply formatting once per sheet, and write in a single pass.

### 4. Demand reconstruction and FIFO matching
The FIFO POV↔GRN match is the most logic-heavy stage and the likeliest place a
naive implementation drops to a Python row loop. Keep it expressed as Polars
group/window operations; a row loop here requires a comment justifying why it
cannot be vectorized, and is a candidate for the ADR-003 escalation path if it
becomes a profiled bottleneck.

## Rules
- Measure before optimizing (Constitution Rule 10).
- Use `pytest-benchmark` for engine functions and a frame-timer for UI interactions.
- Record every optimization against the number it moved; if it moved nothing, revert
  it.
- Optimize the budget that is actually missed, not the one easiest to chase.