// rust/core/src/forecasting/routing.rs
//! Forecast strategy resolution and pipeline orchestration.
//! Adheres to the Open-Closed Principle for algorithmic extensibility.

use crate::classification::sbc::DemandClass;
use crate::domain::demand::DemandSeries;
use crate::domain::forecast::ForecastResult;
use crate::error::KeplError;
use log::{debug, info};

use super::glm::GlmForecaster;
use super::holt_winters::HoltWintersBaseline;
use super::random_forest::RandomForestForecaster;
use super::tsb::TsbForecaster;

/// Defines the operational contract for all forecasting models.
pub trait ForecastStrategy {
    fn generate_forecast(
        &self,
        demand: &DemandSeries,
        horizon: u32,
    ) -> Result<ForecastResult, KeplError>;
}

/// Routes the target demand series to the mathematically optimal forecasting algorithm
/// based on its Syntetos-Boylan Classification (SBC).
pub fn resolve_strategy(sbc_class: &DemandClass) -> Box<dyn ForecastStrategy> {
    match sbc_class {
        DemandClass::Smooth => Box::new(RandomForestForecaster::new()),
        DemandClass::Erratic => Box::new(GlmForecaster::new()),
        DemandClass::Intermittent | DemandClass::Lumpy => Box::new(TsbForecaster::new()),
    }
}

/// Executes the canonical forecast pipeline defined in DOMAIN_RULES.md.
/// 1. Holt-Winters Baseline
/// 2. Model-Specific Refinement via SBC Routing
pub fn execute_forecast_pipeline(
    demand: &DemandSeries,
    sbc_class: &DemandClass,
    horizon: u32,
) -> Result<ForecastResult, KeplError> {
    info!(
        "Initiating forecasting pipeline for item: {:?}",
        demand.item
    );

    // 1. Establish the baseline using Holt-Winters
    let baseline_engine = HoltWintersBaseline::new();
    let baseline_result = baseline_engine.generate_forecast(demand, horizon)?;

    // 2. Resolve and execute the supplementary/refinement model
    debug!(
        "SBC Classification resolved to: {:?}. Routing to optimal model.",
        sbc_class
    );
    let refinement_engine = resolve_strategy(sbc_class);

    let refinement_result = refinement_engine.generate_forecast(demand, horizon)?;

    let final_result = if refinement_result
        .periods
        .iter()
        .all(|p| p.forecasted_quantity == 0.0)
    {
        info!("Refinement model yielded all zeroes. Falling back to Holt-Winters baseline.");
        baseline_result
    } else {
        refinement_result
    };

    info!("Forecasting pipeline execution complete.");
    Ok(final_result)
}
