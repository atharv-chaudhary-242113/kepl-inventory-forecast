// rust/core/src/domain/forecast.rs
//! Forecast output entities.
//! Structures the results of the Holt-Winters, GLM, Random Forest, or TSB engines.

use crate::domain::item::ItemId;
use rust_decimal::Decimal;

/// A single point forecast for a specific future period.
#[derive(Debug, Clone)]
pub struct ForecastPeriod {
    pub period_offset: u32,
    pub forecasted_quantity: f64,
    pub forecasted_value: Decimal,
    pub trend_component: f64,
    pub seasonal_component: f64,
}

/// The aggregate forecast output for a given item.
#[derive(Debug, Clone)]
pub struct ForecastResult {
    pub item: ItemId,
    pub model_used: String,
    pub confidence_score: f64,
    pub periods: Vec<ForecastPeriod>,
}
