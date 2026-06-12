# ADR-001 — Python + Polars Own Business Logic

## Status
Accepted. Supersedes the original "Rust Owns Business Logic" decision on the
`python-engine` branch.

## Context
Forecasting, analytics, classification, and financial calculation must be correct,
fast enough at our volumes (tens of thousands of rows per source file), and cheap
to build, deploy, and maintain. The original design implemented this in Rust for
performance and type safety. Two facts reframe that choice on this branch:

1. Polars executes its query engine in Rust regardless of the calling language, so
   the dominant numeric work is already native whether we call it from Rust or
   Python.
2. The data volumes are modest. The pipeline is overwhelmingly vectorizable
   tabular work, not tight scalar loops where a handwritten systems language
   pulls decisively ahead.

## Decision
Implement all business logic in Python over the Polars LazyFrame API, with
statsforecast and scikit-learn for forecasting models. No Rust, no FFI.

## Alternatives Considered
- **Keep the Rust core (status quo, other branch).** Best raw ceiling and
  strongest compile-time guarantees, but pays FFI complexity, a second toolchain,
  per-platform native builds, and a trust boundary — for a workload that may not
  need it.
- **Python + pandas.** Familiar, but slower and less typed than Polars, and it
  pulls us toward row-wise habits we want to avoid.
- **Python + Polars (chosen).** Native numeric performance via Polars' Rust engine,
  one language, one toolchain, fast iteration.

## Consequences
**Benefits:** single language and build; no FFI to design, validate, or debug; the
whole stack is one `uv sync` away; native numeric performance retained through
Polars.

**Tradeoffs:** CPU-bound glue that can't be vectorized in Polars is slower than
Rust; weaker compile-time safety, mitigated by `mypy --strict` + Pydantic; the
performance ceiling is whatever Polars + numba provide, not hand-tuned Rust.

These tradeoffs are exactly what `BENCHMARK_PLAN.md` measures.