// rust/core-engine/src/utils/metrics.rs
//! Safe mathematical operations for analytical aggregations.
//! Enforces panic prevention at the FFI boundary by explicitly handling division-by-zero vectors.

use polars::prelude::*;

/// Executes safe division within a Polars execution plan.
/// Neutralizes division-by-zero panics and undefined behaviors by returning a declared default value.
pub fn safe_divide_expr(numerator: Expr, denominator: Expr, default_val: f64) -> Expr {
    when(
        denominator
            .clone()
            .eq(lit(0.0))
            .or(denominator.clone().is_null()),
    )
    .then(lit(default_val))
    .otherwise(numerator / denominator)
}
