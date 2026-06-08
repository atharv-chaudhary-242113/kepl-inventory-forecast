# KEPL Inventory Forecast — Python

> Offline desktop platform for procurement, supplier, and inventory analytics.
> Ingests raw ERP exports, reconstructs and forecasts demand, computes supply-chain
> and financial analytics, and produces a self-contained, auditable Excel workbook
> that also powers the interactive dashboards.

<!-- Replace with live badges once CI is wired up -->
![Python](https://img.shields.io/badge/python-3.12-blue)
![Typing](https://img.shields.io/badge/mypy-strict-success)
![Lint](https://img.shields.io/badge/ruff-enabled-success)
![License](https://img.shields.io/badge/license-Proprietary-lightgrey)
![Status](https://img.shields.io/badge/status-active%20development-orange)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Why This Branch Exists](#2-why-this-branch-exists)
3. [Features](#3-features)
4. [Architecture at a Glance](#4-architecture-at-a-glance)
5. [Technology Stack](#5-technology-stack)
6. [Prerequisites](#6-prerequisites)
7. [Installation](#7-installation)
8. [Running the Application](#8-running-the-application)
9. [The End-to-End Workflow](#9-the-end-to-end-workflow)
10. [Configuration](#10-configuration)
11. [Project Structure](#11-project-structure)
12. [Development](#12-development)
13. [Testing](#13-testing)
14. [Benchmarking](#14-benchmarking)
15. [Packaging & Deployment](#15-packaging--deployment)
16. [Documentation Map](#16-documentation-map)
17. [Roadmap](#17-roadmap)
18. [Security](#18-security)
19. [Branch & Contribution Model](#19-branch--contribution-model)
20. [Troubleshooting](#20-troubleshooting)
21. [License & Status](#21-license--status)

---

## 1. Overview

KEPL Inventory Forecast turns the four Excel/CSV reports an ERP and produces —
**Purchase Order Voucher (POV)**, **Goods Received Note (GRN)**, **Purchase
Voucher (PV)**, and **Closing Stock** — into decision-ready analytics for a
procurement-driven inventory operation.

The business does not run on fixed reorder levels or safety-stock policies;
replenishment is consumption-driven. The platform therefore *reconstructs*
historical demand from receipts, purchases, and stock snapshots, classifies each
item's demand pattern, forecasts it with a method suited to that pattern, and
layers on supplier risk, lead-time, financial, and inventory-health analytics.

Everything runs **offline**. There is no server, no
database, and no network dependency. The unit of persistence is a single Excel
workbook, which is simultaneously the audit trail, the interchange format, and
the dashboard's data source.

**Intended user:** a procurement or operations analyst who opens the app, points
it at this period's ERP exports (or a previously generated workbook), and reads
the dashboards — without touching a terminal.

---

## 2. Why This Branch Exists

This is a **`python-only`** branch: a pure Python implementation of the same
system that also exists with a Rust core (`inventory-core` + PyO3 bindings).

Both branches implement the identical business rules (`docs/DOMAIN_RULES.md`) and
emit the identical workbook contract (`docs/WORKBOOK_SCHEMA.md`), which makes them
directly comparable. The branch exists to answer one question with measurements
instead of opinion:

> For this workload and these data volumes, does the Rust core earn its
> complexity — or does Python over Polars (which is itself Rust underneath)
> deliver the same outcomes with far less build, deployment, and maintenance cost?

The methodology and acceptance bar are defined in `docs/BENCHMARK_PLAN.md`. The
honest position going in: Rust only "wins" if it clears a target Python misses,
or beats it by a margin a *user* would feel — not merely on a microbenchmark.

---

## 3. Features

**Ingestion**
- Reads `.xlsx`, `.xls`, and `.csv` exports via the calamine engine.
- Semantic header detection — does not assume headers start on a fixed row;
  tolerates company banners, report titles, date ranges, and blank rows.
- Hierarchical report handling: forward-fills grouped supplier rows so an item
  inherits the supplier printed above it.
- Supplier-name normalization (strips parenthetical branch suffixes, e.g.
  `ABC Electricals (Noida)` → `ABC Electricals`) to a canonical identifier.
- Typed validation: rejects missing columns, unparseable dates, and negative
  quantities/prices/amounts.

**Demand & forecasting**
- Demand reconstruction from GRN, PV, and Closing Stock (no direct sales ledger).
- Syntetos–Boylan classification (ADI, CV²) into smooth / erratic / intermittent
  / lumpy.
- Class-routed forecasting over naive/SES baselines: ETS or Theta for smooth and
  erratic series, Teunter–Syntetos–Babai (benchmarked against Croston-SBA) for
  intermittent and lumpy; the per-class model is chosen by backtested MASE/RMSSE.
- Configurable forecast horizon and granularity; forecast and model-quality
  metrics emitted alongside the forecast.

**Supply-chain analytics**
- FIFO POV↔GRN matching with partial-delivery support, yielding per-relationship
  lead times.
- Pending-delivery detection (ordered > delivered).
- Composite supplier risk (lead time, lead-time variability, fill rate, pending
  deliveries, dependency, price volatility).
- Suspected supplier-partnership flagging (review signal only — never an
  automated fraud conclusion).
- Reorder-point recommendations:
  `reorder_point = (avg_monthly_demand × lead_time_months) + (service_z × demand_std × √lead_time_months)`.
- Price-variance, sourcing-risk, fill-rate, and inventory-health analytics.

**Financials**
- PV treated as the financial source of truth.
- Inventory valuation against a snapshot date, ABC classification by cumulative
  procurement value, freight handled as a separate cost component (current
  business assumption: 18%).
- Deterministic money arithmetic (Polars `Decimal` / Python `Decimal` at
  accumulation boundaries — never floating-point currency accumulation).

**Output & dashboards**
- Multi-sheet workbook: metadata, demand history, forecasts, classifications,
  financials, supplier analytics, pending deliveries, partnerships, and a
  precomputed **Dashboard_Cache**.
- Five PySide6 dashboards (Executive, Forecast, Supplier, Inventory, Financial)
  with interactive Plotly charts, sub-200 ms filtering on cached data, and
  exportable visualizations.

---

## 4. Architecture at a Glance

```text
Raw Input (POV / GRN / PV / Closing Stock)
        │
        ▼
Ingestion        header-detect → forward-fill → normalize → validate
        │  Polars LazyFrame
        ▼
Engine           demand → SBC classify → forecast → analytics → financials
        │  Polars frames
        ▼
Workbook Writer  multi-sheet .xlsx + Dashboard_Cache
        │
        ▼  ─── persistence boundary: "compute once" above, "reuse only" below
        │
Workbook Reader  validate schema/version → load Dashboard_Cache
        │  in-memory Polars frames
        ▼
Dashboard State  filtered views, zero recomputation
        │
        ▼
Plotly figures → QWebEngineView (PySide6)
```

The single most important rule is the persistence boundary: everything above it
runs **once per dataset**; everything below it only filters and renders cached
results. Full detail in `docs/ARCHITECTURE.md`.

---

## 5. Technology Stack

| Concern            | Library / Tool                  | Rationale                                                       | ADR |
| ------------------ | ------------------------------- | --------------------------------------------------------------- | --- |
| Data engine        | Polars (LazyFrame API)          | Rust-backed, lazy, typed; single mental model ingest→export    | 006 |
| Excel read         | Polars + calamine               | Fast, handles `.xls` and `.xlsx`                                | 006 |
| Excel write        | Polars `write_excel` (xlsxwriter)| Rich formatting, multi-sheet, tables                           | 004 |
| Forecasting         | statsforecast (Nixtla)          | numba-fast; ETS, Theta, Croston-SBA, TSB, naive baselines       | 007 |
| ML challenger (opt.)| scikit-learn / LightGBM         | optional global GBM benchmark, not a per-class default          | 007 |
| Validation/config  | Pydantic v2                     | Typed boundaries and settings                                   | —   |
| Desktop UI         | PySide6                         | Native, offline, fine-grained control                          | 002 |
| Charts             | Plotly                          | Interactive, exportable                                         | 005 |
| Environment        | uv + `uv.lock`                  | Reproducible, fast, single source of truth                      | —   |
| Lint/format        | ruff                            | One tool for lint + format                                      | —   |
| Type checking      | mypy (strict)                   | Compile-time-style safety in a dynamic language                 | —   |
| Test               | pytest, pytest-benchmark        | Unit/integration + the Rust comparison harness                  | —   |
| Packaging          | PyInstaller                     | One-click offline Windows bundle                                | —   |

Deliberately **not** used: pandas in the processing path, DuckDB (documented
escalation only), and any Rust/FFI. See `docs/DEPENDENCY_POLICY.md`.

---

## 6. Prerequisites

- **Python 3.12** (pinned in `.python-version`).
- **[uv](https://docs.astral.sh/uv/)** for environment and dependency management.
- **Windows 10/11** for the packaged build; development works on any OS uv
  supports.
- A C/build toolchain is **not** required — all dependencies ship as wheels.

Install uv (Windows PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## 7. Installation

### Developer setup

```bash
git clone <repo-url>
cd kepl-inventory-forecast
git switch python

uv sync                 # creates .venv and installs the locked dependency set
```

`uv sync` is reproducible: it installs exactly what `uv.lock` pins, so every
developer and the CI runner get an identical environment.

### End-user install

End users do not install Python or uv. They receive the packaged bundle produced
by `scripts/build_windows.py` (see [Packaging](#15-packaging--deployment)) and
run a single executable. No terminal, no network.

---

## 8. Running the Application

From a developer environment:

```bash
uv run python -m opstools.inventory_forecast
```

This launches the desktop window. From there the entire workflow is GUI-driven —
see below.

---

## 9. The End-to-End Workflow

### First execution (compute once)

1. **File Selection** — choose this period's POV, GRN, PV, and Closing Stock
   files. The app shows record counts, date ranges, and validation status before
   you proceed.
2. **Configuration** — set forecast horizon and granularity, toggle supplier-risk
   and partnership detection.
3. **Run** — ingestion, forecasting, and analytics execute on a background
   thread with live progress. The UI stays responsive throughout.
4. **Export** — a workbook is written to your chosen output location.
5. **Dashboards** — the five dashboards open against the freshly computed cache.

### Subsequent executions (reuse only)

1. **Open existing workbook** — point the app at a previously generated workbook.
2. The app validates the schema and workbook version, loads the **Dashboard_Cache**,
   and opens the dashboards.
3. **No forecasting or analytics run.** Reuse is read-only and fast (target < 5 s
   to load, < 3 s to first dashboard paint).

This split is enforced by the architecture, not left to discipline:
dashboards have no code path that can trigger recomputation.

---

## 10. Configuration

Runtime parameters are typed Pydantic settings (`src/kepl/config/settings.py`),
overridable per run from the Configuration view. The business-tunable values:

| Setting                  | Meaning                                                   | Default        |
| ------------------------ | --------------------------------------------------------- | -------------- |
| `forecast_horizon`       | Number of future periods to forecast                      | 12             |
| `forecast_granularity`   | `monthly` or `quarterly`                                   | `monthly`      |
| `service_z`              | Service-level z-score in the reorder-point formula        | 1.65 (≈95%)    |
| `default_lead_time_days` | Fallback lead time when history is insufficient           | 30             |
| `freight_rate`           | Freight treated as a separate cost component              | 0.18           |
| `abc_thresholds`         | Cumulative-value cut points for A/B/C                      | 0.80 / 0.95    |
| `enable_supplier_risk`   | Toggle supplier-risk analytics                            | `true`         |
| `enable_partnerships`    | Toggle suspected-partnership detection                    | `true`         |

Several of these (freight interpretation, supplier risk weighting, demand
reconstruction methodology) are **pending business validation** — see
`docs/DOMAIN_RULES.md`. They are configurable precisely so we never hard-code an
unvalidated assumption.

---

## 11. Project Structure

```text
src/kepl/
├── config/        # Pydantic settings
├── domain/        # pure types: enums, models, error hierarchy (no I/O)
├── ingestion/     # read → header-detect → forward-fill → normalize → validate
├── engine/        # ALL business logic; pure functions over Polars frames
├── workbook/      # write, validated read, version checks, Dashboard_Cache
├── services/      # orchestration + state (no business math)
├── viz/           # pure Plotly figure builders (no Qt)
├── ui/            # PySide6 only; long work runs on QThread workers
└── security/      # path-traversal / UNC guards
```

The dependency direction is strictly downward: `engine` never imports `ui`,
`viz`, or `workbook`; `viz` never imports Qt. The full annotated tree lives in
`docs/ARCHITECTURE.md`.

---

## 12. Development

```bash
uv run ruff format .        # format (the single formatter)
uv run ruff check .         # lint
uv run ruff check . --fix   # lint + autofix
uv run mypy src             # strict type check
uv run pytest               # unit + integration
```

Conventions (full text in `docs/CODING_STANDARDS.md`):
- PEP 8 + PEP 257; `mypy --strict` must pass; no unjustified `Any`.
- Pure functions in `engine`/`viz`; side effects confined to
  `ingestion`/`workbook`/`services`/`ui`.
- Prefer Polars expressions over per-row Python loops; a row loop in the
  processing path requires a comment explaining why it can't be vectorized.
- Non-obvious transformations carry a short teaching comment (the *what and why*).

---

## 13. Testing

```bash
uv run pytest                       # everything
uv run pytest tests/unit            # fast unit tests
uv run pytest tests/integration     # full pipeline + workbook round-trip
uv run pytest -k forecast           # by keyword
```

Layout mirrors the source tree: each engine module has a unit test; integration
tests cover ingest→engine→workbook→state end-to-end, including a lossless
workbook round-trip and a workbook-version-mismatch rejection.

---

## 14. Benchmarking

The comparison against the Rust core is a first-class deliverable, not an
afterthought.

```bash
uv run pytest tests/benchmarks --benchmark-only
```

We measure full-pipeline wall time at 5k/20k/50k rows per file, per-stage timing,
workbook-load time, peak memory, cold start, and build/deploy cost — against a
correctness gate (both engines must produce identical outputs on the fixtures
before any timing counts). numba JIT warmup is reported separately from
steady-state throughput. Results and the running recommendation live in
`benchmarks/README.md`; methodology in `docs/BENCHMARK_PLAN.md`.

---

## 15. Packaging & Deployment

```bash
uv run python scripts/build_windows.py
```

Produces a self-contained Windows bundle via PyInstaller:
- One executable, double-click to launch.
- All dependencies bundled — no Python install, no internet.
- statsforecast models are warmed once at startup so the user's first run is not
  charged the numba compile cost.

Deployment is a file copy. There is no installer service, registry change, or
admin requirement beyond writing to the install directory.

---

## 16. Documentation Map

| Document                  | Purpose                                            |
| ------------------------- | -------------------------------------------------- |
| `PROJECT_CONSTITUTION.md` | Non-negotiable rules of the codebase               |
| `ARCHITECTURE.md`         | Layers, data flow, ownership, the pipeline DAG     |
| `API_CONTRACT.md`         | Internal module boundaries and signatures          |
| `DOMAIN_RULES.md`         | Authoritative business rules                       |
| `INPUT_SCHEMA.md`         | Accepted source-file formats and parsing rules     |
| `WORKBOOK_SCHEMA.md`      | Output workbook sheet contract                     |
| `DASHBOARD_SPEC.md`       | Dashboard views, KPIs, charts, filters             |
| `ACCEPTANCE_CRITERIA.md`  | Functional, performance, reliability, security bar |
| `PERFORMANCE_BUDGET.md`   | Latency/throughput targets and hot-path risks      |
| `BENCHMARK_PLAN.md`       | Rust-vs-Python comparison methodology              |
| `THREAT_MODEL.md`         | Security objectives, boundaries, controls          |
| `CODING_STANDARDS.md`     | Style, typing, docstring, and structure rules      |
| `DEPENDENCY_POLICY.md`    | Allowed libraries; how new ones are added          |
| `ROADMAP.md`              | The phased build sequence                          |
| `ADR/`                    | Architecture decision records                      |

---

## 17. Roadmap

Built phase-by-phase, each phase gated on a green test suite before the next
begins (full detail in `docs/ROADMAP.md`):

`0` scaffolding · `1` ingestion · `2` core engine · `3` forecasting & advanced
analytics · `4` workbook · `5` services · `6` UI & viz · `7` packaging & benchmark.

---

## 18. Security

The platform treats every external file, every workbook, and all user input as
untrusted. Controls include path-traversal and UNC-path guards, formula-injection
prevention on Excel output, workbook integrity and version validation, and
renderer-resource limits on the chart layer. The full model — assets, trust
boundaries, threats, and controls — is in `docs/THREAT_MODEL.md`. Note that the
single-language design removes the FFI trust boundary the Rust branch must defend.

---

## 19. Branch & Contribution Model

- `python` — this pure-Python build.
- The Rust-core build lives on its own branch; the two share `DOMAIN_RULES.md`
  and `WORKBOOK_SCHEMA.md` verbatim so they stay comparable.
- Work proceeds in named, scoped increments within each roadmap phase; tests must
  pass before moving on.
- Every architecture change updates the affected document in the same commit
  (Constitution Rule 11).

---

## 20. Troubleshooting

| Symptom                                   | Likely cause / fix                                                        |
| ----------------------------------------- | ------------------------------------------------------------------------- |
| `SchemaError` on a known-good file        | ERP changed column headers; matching is name-based — check spelling/case. |
| All rows for a supplier rejected as empty | Forward-fill didn't run before validation; confirm the header row was found.|
| First run is slow, later runs fast        | numba JIT warmup; expected. Packaged build warms models at startup.        |
| Filter feels laggy (> 200 ms)             | Plotly re-render, not the data. See hot-path mitigations in `PERFORMANCE_BUDGET.md`.|
| `WorkbookVersionError` on open            | Workbook was written by an incompatible version; regenerate from sources.  |

---

## 21. License & Status

**License:** Proprietary — internal company use. Documentation may be shared as
portfolio material; internal datasets, generated workbooks, logs, exports, and
credentials must never be committed.

**Status:** Active development on the `python` branch, greenfield, built
to the phased roadmap. Designed for correctness, maintainability, security,
reproducibility, and operational efficiency.