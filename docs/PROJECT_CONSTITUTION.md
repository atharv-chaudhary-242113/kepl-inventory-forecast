# Project Constitution

## Purpose

KEPL Inventory Forecast is an offline inventory forecasting and analytics platform
built for repeatable, auditable, and reproducible business decision support. This
document states the rules the codebase is not permitted to violate. Everything
else is implementation detail subject to change; these are not.

A rule here outranks convenience, cleverness, and personal preference. If a
proposed change requires breaking a rule, the change is wrong or the rule must be
amended first — in its own commit, with justification.

---

## Core Rules

### Rule 1 — One language owns the work
The engine is pure Python. Ingestion, demand reconstruction, forecasting,
analytics, classification, financial calculation, and validation live in
`src/kepl/ingestion` and `src/kepl/engine`. There is no second language and no FFI
boundary to defend. Business logic must never live in the UI layer.

### Rule 2 — The UI owns presentation only
`src/kepl/ui` owns application lifecycle, user interaction, and rendering. It calls
services; it never computes a forecast, a risk score, or a financial figure. If a
UI handler is doing arithmetic on domain data, that arithmetic belongs in
`engine`.

### Rule 3 — Polars owns in-memory data
All tabular data is held and transformed as Polars frames. Pipeline stages pass
`LazyFrame`s and collect once, at the leaves that need it. We do not drop to pandas
in the processing path, and we do not hand-roll Python loops over rows where a
Polars expression exists. pandas/NumPy appear only as transients at a third-party
call site (e.g. handing a series to statsforecast) and are converted back
immediately.

### Rule 4 — Excel owns persistence
The generated workbook is the canonical persisted representation of engine output:
audit trail, interchange format, and dashboard source in one file. Excel is a
persistence and interchange format, **not** a database; we never query it
incrementally or treat it as live storage.

### Rule 5 — Dashboards never compute
Dashboards filter, aggregate cached data, and visualize. They must never re-run
forecasting, re-run analytics, recompute classifications, or re-read the workbook
after the initial load. This is enforced structurally: the dashboard layer has no
import path to the engine.

### Rule 6 — Compute once per dataset
Forecasting and analytics run exactly once per dataset, on first execution. Their
results are persisted in the workbook (including a precomputed Dashboard_Cache) and
reused on every subsequent open. Expensive computation is never repeated for a
dataset already processed.

### Rule 7 — All external input is untrusted
Validate files, workbook contents, metadata, and user input before processing.
Validation is a typed boundary (Pydantic models and documented Polars schemas),
not scattered `if` checks. Bad input fails loudly with an actionable error, never
silently with a wrong number.

### Rule 8 — Type safety is mandatory
Every public function is fully annotated. `mypy --strict` runs and must pass. Data
crossing a layer boundary is a Pydantic model or a Polars frame with a documented
schema — never an untyped `dict`. `Any` requires a comment justifying it.

### Rule 9 — Reproducibility is mandatory
The environment is defined by `pyproject.toml` and pinned by `uv.lock`. The same
inputs under the same application version must produce identical classifications,
forecasts, risk scores, and workbook bytes (modulo the generation timestamp).
Non-determinism — unseeded models, dict-ordering dependence, wall-clock in
logic — is a defect.

### Rule 10 — Measure before optimizing
Performance work targets a profiled bottleneck against `PERFORMANCE_BUDGET.md`. We
do not pre-optimize on intuition, and we record every optimization against the
number it actually moved.

### Rule 11 — Documentation reflects implementation
When the architecture changes, the affected document changes in the same commit. A
document that lies is worse than no document. The doc set is part of the
deliverable, not a courtesy.

---

## Precedence

When rules appear to conflict, correctness (Rule 7) and reproducibility (Rule 9)
win over performance (Rule 10), which wins over convenience. The layering rules
(1–5) are absolute; a performance need never justifies business logic in the UI or
recomputation in a dashboard — it justifies a faster engine or a richer cache.

## Amendment

A rule changes only by editing this file in a dedicated commit that states what
changed and why, and updates any document or ADR the change touches.