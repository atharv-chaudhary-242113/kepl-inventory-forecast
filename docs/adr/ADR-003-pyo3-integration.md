# ADR-003

## Title

PyO3 Interoperability Layer

## Status

Accepted

## Context

Rust business logic must integrate with Python presentation layers.

## Decision

Use PyO3 for Rust-Python interoperability.

## Consequences

Benefits:

* Strong integration
* Low overhead
* Direct type mapping

Tradeoffs:

* FFI boundary complexity
