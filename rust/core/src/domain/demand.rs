// rust/coree/src/domain/demand.rs
//! Demand history modeling.
//! Represents the chronological demand sequence reconstructed from GRN, PV, and Closing Stock.

use crate::domain::item::ItemId;
use chrono::NaiveDate;
use rust_decimal::Decimal;

/// A single period's observed demand for an item.
#[derive(Debug, Clone)]
pub struct DemandRecord {
    pub period_start: NaiveDate,
    pub item: ItemId,
    pub quantity: f64,
    pub value: Decimal,
}

/// The contiguous chronological demand series utilized by the forecasting engine.
#[derive(Debug, Clone)]
pub struct DemandSeries {
    pub item: ItemId,
    pub records: Vec<DemandRecord>,
}

impl DemandSeries {
    /// Extracts the physical quantity vector for mathematical modeling.
    pub fn to_quantity_vector(&self) -> Vec<f64> {
        self.records.iter().map(|r| r.quantity).collect()
    }
}
