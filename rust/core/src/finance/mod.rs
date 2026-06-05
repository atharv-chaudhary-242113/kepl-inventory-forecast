// rust/core-engine/src/finance/mod.rs
//! Financial calculations and valuation layer.
//! Enforces deterministic decimal arithmetic across all monetary evaluations
//! to eliminate floating-point desynchronization.

pub mod costing;
pub mod freight;
pub mod valuation;
