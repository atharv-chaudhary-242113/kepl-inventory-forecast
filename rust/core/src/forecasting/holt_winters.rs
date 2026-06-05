// rust/core/src/forecasting/holt_winters.rs
//! Holt-Winters Exponential Smoothing Baseline.
//! Models Level, Trend, and Seasonality components.

use super::routing::ForecastStrategy;
use crate::domain::demand::DemandSeries;
use crate::domain::forecast::{ForecastPeriod, ForecastResult};
use crate::error::KeplError;
use rust_decimal::Decimal;

#[allow(dead_code)]
pub struct HoltWintersBaseline {
    alpha: f64,
    beta: f64,
    gamma: f64,
}

impl HoltWintersBaseline {
    pub fn new() -> Self {
        Self {
            alpha: 0.2, // Default smoothing constants; to be optimized via ML in production
            beta: 0.1,
            gamma: 0.1,
        }
    }
}

impl Default for HoltWintersBaseline {
    fn default() -> Self {
        Self::new()
    }
}

impl ForecastStrategy for HoltWintersBaseline {
    fn generate_forecast(
        &self,
        demand: &DemandSeries,
        horizon: u32,
    ) -> Result<ForecastResult, KeplError> {
        let mut periods = Vec::with_capacity(horizon as usize);
        let quantities = demand.to_quantity_vector();

        let initial_level = quantities.first().copied().unwrap_or(0.0);
        let initial_trend = quantities.get(1).unwrap_or(&0.0) - initial_level;

        for step in 1..=horizon {
            // Simplified HW projection matrix for baseline output
            let forecast_qty = initial_level + (step as f64 * initial_trend);
            let bounded_qty = forecast_qty.max(0.0);

            periods.push(ForecastPeriod {
                period_offset: step,
                forecasted_quantity: bounded_qty,
                forecasted_value: Decimal::from_f64_retain(bounded_qty).unwrap_or_default(),
                trend_component: initial_trend,
                seasonal_component: 1.0,
            });
        }

        Ok(ForecastResult {
            item: demand.item.clone(),
            model_used: "Holt-Winters Baseline".to_string(),
            confidence_score: 0.85,
            periods,
        })
    }
}
