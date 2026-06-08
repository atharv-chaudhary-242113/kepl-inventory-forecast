# ADR-006 — Polars as the DataFrame Engine

## Status
Accepted.

## Context
The pipeline is a chain of tabular transformations from ingest to export. We need
predictable performance, lazy evaluation to fuse operations across stages, strong
dtypes (including deterministic money), and a single mental model end to end.

## Decision
Use Polars (LazyFrame API) as the single in-memory data engine. Read Excel via the
calamine engine; write via `DataFrame.write_excel` (xlsxwriter). Do not use pandas
in the processing path.

## Alternatives Considered
- **pandas.** Larger ecosystem, but slower, weaker typing, eager-only by default,
  and encourages row-wise code.
- **DuckDB as the primary engine.** Excellent for heavy SQL analytics, but adds a
  second data model and query language for a workload Polars already handles. Kept
  as a documented escalation, not a default.
- **Polars (chosen).** Lazy optimization, multithreaded execution, strong dtypes,
  Rust-backed performance, one model throughout.

## Consequences
**Benefits:** lazy query optimization and parallel execution out of the box; strong
dtypes including `Decimal` for money; one idiom from ingest to export.

**Tradeoffs:** smaller ecosystem than pandas for niche operations; some statistical
libraries expect pandas/NumPy, so we convert only at those exact call sites (e.g.
handing a series to statsforecast) and convert straight back.