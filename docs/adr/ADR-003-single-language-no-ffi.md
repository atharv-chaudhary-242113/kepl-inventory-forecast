# ADR-003 — Single-Language Architecture, No FFI

## Status
Accepted. Supersedes the original ADR-003 "PyO3 Interoperability Layer".

## Context
The Rust-core design required a PyO3 boundary between the engine and the UI. That
boundary added build complexity, a class of FFI bugs (type mapping, panic
containment, ownership across the boundary), and a trust boundary the threat model
had to defend. On this branch the engine is Python, so the boundary does not exist
and should not be reintroduced casually.

## Decision
Adopt a single-language architecture with no foreign function interface. Layers
communicate through ordinary Python calls, passing Polars frames and Pydantic
models by reference within one process.

## Consequences
**Benefits:** no serialization or copying across a language boundary; no
panic-containment or type-mapping concerns; the threat model loses an entire trust
boundary; packaging simplifies because there is no native extension to compile per
platform.

**Tradeoffs:** we lose the ability to drop into Rust for a hot loop without
re-introducing FFI. If a *profiled* bottleneck ever demands it, the sanctioned
escalation path is, in order: (1) rewrite the hot path as a vectorized Polars
expression; (2) a numba kernel on the NumPy view; (3) only then reconsider a native
extension — and that reconsideration reopens this ADR. The escalation is documented
in `PERFORMANCE_BUDGET.md`.