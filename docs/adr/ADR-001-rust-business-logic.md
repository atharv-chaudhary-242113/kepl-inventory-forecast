# ADR-001

## Title

Rust Owns Business Logic

## Status

Accepted

## Context

Forecasting, analytics, classification, and financial calculations are computationally intensive and require strong type safety.

## Decision

Implement all business logic in Rust.

## Consequences

Benefits:

* Performance
* Memory safety
* Type safety

Tradeoffs:

* Increased FFI complexity
* Additional build complexity
