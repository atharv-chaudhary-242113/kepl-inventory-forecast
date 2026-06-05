// rust/core/src/domain/supplier.rs
//! Supplier entity and risk modeling.
//! Defines the canonical supplier identity and composite performance metrics.

use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};

/// Canonical identifier for a supplier, post-normalization.
#[derive(Debug, Clone, Hash, Eq, PartialEq, Serialize, Deserialize)]
pub struct SupplierId(pub String);

impl SupplierId {
    pub fn new(name: &str) -> Self {
        Self(name.to_string())
    }
}

/// Composite metrics defining supplier performance and operational risk.
#[derive(Debug, Clone)]
pub struct SupplierMetrics {
    pub total_spend: Decimal,
    pub total_orders: u32,
    pub total_deliveries: u32,
    pub average_lead_time_days: f64,
    pub lead_time_stddev: f64,
    pub pending_deliveries: u32,
    pub reliability_score: f64,
    pub risk_score: f64,
}
