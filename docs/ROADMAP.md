# Roadmap — Phased Build Sequence

Each phase is gated: its tests must pass before the next begins. The phase order
follows the dependency order of the source tree (top to bottom), so every phase
builds only on layers already complete and tested. Within a phase, work proceeds in
named, scoped increments, each with its own test verification.

---

## Phase 0 — Scaffolding
- **Build:** `pyproject.toml`, `uv.lock`, ruff/mypy/pytest configuration,
`config/settings.py`, `domain/{enums,models,errors}.py`.
- **Gate:** `mypy --strict` clean; empty/placeholder test suite green; `uv run python -m opstools/inventory_forecast` starts and exits cleanly.

## Phase 1 — Ingestion
**Build:** `ingestion/{reader,header_detection,normalize,schema}.py`.
**Gate:** reads each of the four source types from fixtures into validated
LazyFrames meeting the canonical schema; forward-fill and supplier normalization
verified; malformed input rejected per `INPUT_SCHEMA.md` with the correct error type.

## Phase 2 — Core Engine
**Build:** `engine/{demand,lead_time,pending,classification,financials,valuation}.py`.
**Gate:** unit tests for ABC bands, Syntetos–Boylan (ADI / CV²) classification, FIFO
lead-time matching with partial deliveries, pending-delivery detection, and
valuation against an explicit `snapshot_date`.

## Phase 3 — Forecasting & Advanced Analytics
**Build:** `engine/{forecasting,supplier_risk,partnerships,reorder,price_variance,
sourcing,fulfillment,inventory_health}.py` and `engine/orchestrator.py`.
**Gate:** SBC-routed forecasts match fixtures within tolerance; reorder-point formula
verified against worked examples; the full DAG collects end to end; all advanced
analytics produce their documented schemas.

## Phase 4 — Workbook
**Build:** `workbook/{schema,writer,reader,cache}.py`.
**Gate:** write → read round-trip is lossless; workbook version mismatch rejected
with `WorkbookVersionError`; Dashboard_Cache built and reloadable; formula-injection
sanitization verified.

## Phase 5 — Services
**Build:** `services/{pipeline_service,workbook_service,state}.py`.
**Gate:** raw files → workbook → dashboard state runs end to end with a thread-safe
progress callback; reuse path loads state without triggering any recomputation.

## Phase 6 — UI & Visualization
**Build:** `viz/*` (pure figure builders, tested headless) then `ui/*` (PySide6
windows, views, widgets, QThread workers, QWebEngineView).
**Gate:** the app launches, runs a pipeline off the UI thread with live progress,
renders all five dashboards, and meets the filter-response budget (or applies a
recorded mitigation from `PERFORMANCE_BUDGET.md`).

## Phase 7 — Packaging & Benchmark
**Build:** `scripts/build_windows.py` (PyInstaller) and `tests/benchmarks/*`.
**Gate:** a one-click Windows bundle launches fully offline; the benchmark table in
`benchmarks/README.md` is populated against the Rust baseline and ends in an
evidence-based recommendation.

---

## Working Discipline
- Tests pass before advancing; no phase is "mostly done."
- Each architecture change updates its document in the same commit.
- Performance work waits for a profiled bottleneck against the budget.