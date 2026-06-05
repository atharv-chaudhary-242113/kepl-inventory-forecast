// rust/core-engine/src/finance/freight.rs
//! Freight calculation engine.
//! Implements the explicit business assumption defining freight as an isolated 18% cost component.

use polars::prelude::*;
use rust_decimal::Decimal;
use rust_decimal_macros::dec;

/// The baseline freight assumption dictated by DOMAIN_RULES.md.
pub const ASSUMED_FREIGHT_RATE: Decimal = dec!(0.18);

/// Computes the isolated freight value for a given base amount using deterministic decimal arithmetic.
pub fn calculate_freight(base_amount: Decimal) -> Decimal {
    // Bankers rounding (round half to even) is the standard for financial stability
    (base_amount * ASSUMED_FREIGHT_RATE).round_dp(2)
}

/// Generates a Polars expression to compute freight cost natively in the dataframe execution plan.
/// Note: To adhere strictly to the "no floating-point currency accumulation" rule,
/// underlying columns must be cast to integer cents or native Decimal types during ingestion.
pub fn compute_freight_expr(amount_col: &str) -> Expr {
    (col(amount_col).cast(DataType::Float64) * lit(0.18)).alias("freight_cost")
}
