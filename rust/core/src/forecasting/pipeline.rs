use polars::prelude::*;

use crate::adapters::{forecast_results_to_frame, frames_to_demand_series, sbc_frame_to_class_map};
use crate::classification::sbc::{DemandClass, apply_sbc_classification};
use crate::error::KeplError;

use super::demand_reconstruction::reconstruct_demand;
use super::routing::execute_forecast_pipeline;

/// Executes the complete forecasting workflow:
///
/// GRN + PV + Stock
///        ↓
/// Demand Reconstruction
///        ↓
/// SBC Classification
///        ↓
/// Frame → Domain Adapters
///        ↓
/// Forecast Routing
///        ↓
/// ForecastResult → DataFrame
pub fn generate_forecasts(
    grn_lf: LazyFrame,
    pv_lf: LazyFrame,
    stock_lf: LazyFrame,
    horizon: u32,
) -> Result<DataFrame, KeplError> {
    //
    // 1. Reconstruct demand history
    //
    let demand_history_lf = reconstruct_demand(grn_lf, pv_lf, stock_lf)?;

    let demand_history_df = demand_history_lf.collect()?;

    //
    // 2. Compute SBC classifications
    //
    let sbc_lf = apply_sbc_classification(demand_history_df.clone().lazy());

    let sbc_df = sbc_lf.collect()?;

    //
    // 3. Convert DataFrames into domain models
    //
    let demand_series = frames_to_demand_series(&demand_history_df)?;

    let class_map = sbc_frame_to_class_map(&sbc_df)?;

    //
    // 4. Execute forecasting per item
    //
    let mut forecasts = Vec::new();

    for series in demand_series {
        let demand_class = class_map
            .get(&series.item)
            .unwrap_or(&DemandClass::Intermittent);

        let forecast = execute_forecast_pipeline(&series, demand_class, horizon)?;

        forecasts.push(forecast);
    }

    //
    // 5. Convert forecast results back to a DataFrame
    //
    forecast_results_to_frame(&forecasts)
}
