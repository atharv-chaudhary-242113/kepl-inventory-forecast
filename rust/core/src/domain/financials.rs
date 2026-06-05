// rust/core/src/domain/financials.rs
//! Financial constants and type constraints.
//! Enforces Decimal usage across all monetary calculations to prevent floating-point desynchronization.

use rust_decimal::Decimal;
use rust_decimal_macros::dec;

/// Represents the assumed freight cost ratio.
/// DOMAIN_RULES.md specifies a current assumption of 18%.
pub use crate::finance::freight::ASSUMED_FREIGHT_RATE;

/// Computes the total procurement cost including assumed freight.
pub fn compute_landed_cost(unit_cost: Decimal, quantity: f64) -> Decimal {
    let base_cost = unit_cost * Decimal::from_f64_retain(quantity).unwrap_or(dec!(0.0));
    let freight_cost = base_cost * ASSUMED_FREIGHT_RATE;
    base_cost + freight_cost
}
