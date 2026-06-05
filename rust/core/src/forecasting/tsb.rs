// rust/core/src/forecasting/tsb.rs
//! Teunter-Syntetos-Babai (TSB) Engine.
//! Mathematically isolates demand probability from demand magnitude to calculate
//! intermittent and lumpy demand profiles.

use super::routing::ForecastStrategy;
use crate::domain::demand::DemandSeries;
use crate::domain::forecast::{ForecastPeriod, ForecastResult};
use crate::error::KeplError;
use rust_decimal::Decimal;

pub struct TsbForecaster {
    probability_smoothing: f64, // alpha
    magnitude_smoothing: f64,   // beta
}

impl TsbForecaster {
    pub fn new() -> Self {
        Self {
            probability_smoothing: 0.1,
            magnitude_smoothing: 0.1,
        }
    }
}

impl Default for TsbForecaster {
    fn default() -> Self {
        Self::new()
    }
}

impl ForecastStrategy for TsbForecaster {
    fn generate_forecast(
        &self,
        demand: &DemandSeries,
        horizon: u32,
    ) -> Result<ForecastResult, KeplError> {
        let quantities = demand.to_quantity_vector();

        // Initialize probability (p) and magnitude (z)
        let mut p = if let Some(&first) = quantities.first() {
            if first > 0.0 { 1.0 } else { 0.0 }
        } else {
            0.0
        };
        let mut z = quantities.first().copied().unwrap_or(0.0);

        // Core TSB logic iteration
        for &q in &quantities {
            if q > 0.0 {
                p = self.probability_smoothing + (1.0 - self.probability_smoothing) * p;
                z = self.magnitude_smoothing * q + (1.0 - self.magnitude_smoothing) * z;
            } else {
                p *= 1.0 - self.probability_smoothing;
            }
        }

        let forecasted_quantity = p * z;
        let mut periods = Vec::with_capacity(horizon as usize);

        for step in 1..=horizon {
            periods.push(ForecastPeriod {
                period_offset: step,
                forecasted_quantity,
                forecasted_value: Decimal::from_f64_retain(forecasted_quantity).unwrap_or_default(),
                trend_component: 0.0, // TSB does not inherently model discrete trend
                seasonal_component: 0.0, // TSB does not inherently model discrete seasonality
            });
        }

        Ok(ForecastResult {
            item: demand.item.clone(),
            model_used: "Teunter-Syntetos-Babai".to_string(),
            confidence_score: 0.70,
            periods,
        })
    }
}
