# Architecture

## 1. Purpose and Scope

This document describes how the system is structured, how data flows through it,
which layer owns what, and the invariants that keep those layers honest. It is the
map a new contributor reads before touching code, and the reference a reviewer uses
to reject a change that crosses a boundary it shouldn't.

## 2. Guiding Principles

- Business logic is isolated from presentation, and file I/O is isolated from
  business logic.
- Data flows one direction through clearly typed boundaries.
- Compute once, reuse many — the workbook is the dividing line.
- Pure functions wherever the work is computational; side effects pushed to the
  edges (ingestion, workbook, services, UI).
- The simplest design that satisfies the rules wins.

## 3. High-Level Data Flow

```text
Raw Input (POV / GRN / PV / Closing Stock)
        │
        ▼
Ingestion Layer        header-detect → forward-fill → normalize → validate
        │  Polars LazyFrame (clean, typed)
        ▼
Engine                 demand → SBC classify → forecast → analytics → financials
        │  Polars frames
        ▼
Workbook Writer        multi-sheet .xlsx + Dashboard_Cache + metadata
        │
        ▼  ════════════ PERSISTENCE BOUNDARY ════════════
        │               above: compute once   below: reuse only
        ▼
Workbook Reader        validate schema + version → load Dashboard_Cache
        │  in-memory Polars frames
        ▼
Dashboard State        filtered views, zero recomputation
        │
        ▼
Viz                    pure functions → Plotly figures
        │
        ▼
UI                     QWebEngineView inside PySide6, off-thread compute
```

The persistence boundary is the most important line in the system. Above it, work
is expensive and happens once. Below it, work is cheap, read-only, and repeatable.
No code below the line may trigger work above it.

## 4. Layers and Ownership

### 4.1 `domain` — pure types
Enums (`SourceKind`, `AbcClass`, `SbcClass`), Pydantic models for records and
results, and the `InventoryForecastError` exception hierarchy. No I/O, no dependencies on any
other layer. Everything else may import `domain`; `domain` imports nothing of ours.

### 4.2 `ingestion` — untrusted input → clean frames
Reads source files (calamine), locates the header row semantically, forward-fills
grouped columns, normalizes supplier names, maps columns by name, and validates
records. Output: `LazyFrame`s with canonical column names, `Date`-typed dates, and
non-negative numerics. This is the trust boundary for external files (Rule 7).
Depends on `domain` only.

### 4.3 `engine` — all business computation
Pure functions over Polars frames: demand reconstruction, FIFO lead-time matching,
pending deliveries, ABC and Syntetos–Boylan classification, forecasting, supplier
risk, partnership detection, valuation, reorder points, price variance, sourcing
risk, fill rate, inventory health. Same input → same output, no I/O. **Must not
import `ui`, `viz`, or `workbook`.**

### 4.4 `workbook` — persistence
Export preparation, multi-sheet writing, validated loading, schema/version checks,
and the Dashboard_Cache. Knows the sheet schema; knows nothing about how the data
was computed or how it will be drawn.

### 4.5 `services` — orchestration and state
Two transitions: "raw files → workbook" (`pipeline_service`) and "workbook →
in-memory dashboard state" (`workbook_service`). Coordinates the layers above and
exposes a thread-safe progress callback for the UI. Contains no business math.

### 4.6 `viz` — figure builders
Pure functions that take cached frames and return Plotly `Figure` objects. No Qt,
no I/O — trivially unit-testable headless.

### 4.7 `ui` — PySide6 only
Windows, views, widgets. The only layer permitted to import Qt. Long-running work
is dispatched to QThread workers so the event loop never blocks; workers return
immutable frames the UI renders.

### 4.8 `security` — guards
Path-traversal and UNC-path validation, applied at every point a user-supplied path
enters the system.

## 5. The Engine Pipeline as a DAG

`engine/orchestrator.py` wires stages as a directed acyclic graph of LazyFrames.
Each node is a pure transformation; the graph is collected once at the leaves that
need materializing. Because everything is Polars in one process, intermediate
frames pass by reference — no serialization, no copy across a language boundary.

```text
ingested(POV, GRN, PV, Closing)
   │
   ├── lead_time ──► pending ──► supplier_risk ──┐
   │                                             ├── inventory_health
   ├── demand ──► sbc_classify ──► forecast ─────┤
   │                                             │
   ├── financials ──► valuation ──► abc ─────────┼──► Dashboard_Cache
   │                                             │
   ├── price_variance ───────────────────────────┤
   ├── sourcing_risk  ────────────────────────────┤
   ├── fulfillment (fill_rate) ───────────────────┤
   └── partnerships ──────────────────────────────┘
```

Lazy evaluation lets Polars fuse and parallelize across the graph; we collect the
final per-sheet frames the writer needs, not every intermediate.

## 6. Runtime Model

**First execution:** `raw → ingest → engine (forecast + analytics) → write workbook → open dashboard`.

**Subsequent executions:** `existing workbook → validate → load Dashboard_Cache → open dashboard`. No forecasting or analytics run on reuse.

## 7. Concurrency Model

The engine is synchronous and single-threaded at the Python level; Polars
parallelizes internally across its own thread pool, and statsforecast parallelizes
across series. The UI offloads the entire pipeline to a single QThread worker so the
main thread stays responsive and can paint progress. The worker and the UI share no
mutable state — the worker hands back immutable results on completion. Filtering on
the dashboard runs synchronously on already-cached frames because it is cheap by
design (the cache is pre-aggregated).

## 8. Error Handling Strategy

All recoverable failures raise a `InventoryForecastError` subclass with an actionable message.
Ingestion converts malformed input into `SchemaError`/`ValidationError` at the
boundary; the workbook layer raises `WorkbookVersionError` on mismatch; services
translate these into user-facing messages without leaking stack traces into the UI.
Programmer errors (broken invariants) fail fast and loud.

## 9. Why No Rust on This Branch

The Rust-core design placed the engine behind a PyO3 boundary. This branch removes
both the Rust and the boundary. The reasoning: Polars already executes its query
engine in Rust regardless of the calling language, so the heavy numeric work is
native either way; the calling language mainly affects developer velocity, build,
and deployment. A single-language codebase is faster to build, ship, and maintain,
and it deletes an entire trust boundary from the threat model. Whether that costs
us throughput a user would feel is an empirical question, answered in
`BENCHMARK_PLAN.md` rather than asserted here.

## 10. Boundary Invariants (enforced in review)

- `engine` and `viz` are pure; no file, network, or Qt access.
- `engine` does not import `ui`, `viz`, or `workbook`.
- `viz` does not import Qt.
- All external paths pass through `security` before use.
- Data crossing any layer boundary is a Pydantic model or a schema-documented
  Polars frame.