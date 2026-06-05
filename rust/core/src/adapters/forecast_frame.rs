use polars::prelude::*;

use crate::domain::forecast::ForecastResult;
use crate::error::KeplError;

pub fn forecast_results_to_frame(forecasts: &[ForecastResult]) -> Result<DataFrame, KeplError> {
    let mut suppliers = Vec::<String>::new();
    let mut items = Vec::<String>::new();

    let mut offsets = Vec::<u32>::new();

    let mut forecast_qty = Vec::<f64>::new();
    let mut forecast_val = Vec::<String>::new();

    let mut trend = Vec::<f64>::new();
    let mut seasonal = Vec::<f64>::new();

    let mut models = Vec::<String>::new();
    let mut confidence = Vec::<f64>::new();

    for forecast in forecasts {
        for period in &forecast.periods {
            suppliers.push(forecast.item.supplier.0.clone());

            items.push(forecast.item.details.clone());

            offsets.push(period.period_offset);

            forecast_qty.push(period.forecasted_quantity);

            forecast_val.push(period.forecasted_value.to_string());

            trend.push(period.trend_component);

            seasonal.push(period.seasonal_component);

            models.push(forecast.model_used.clone());

            confidence.push(forecast.confidence_score);
        }
    }

    let height = forecasts.iter().map(|f| f.periods.len()).sum::<usize>();

    DataFrame::new(
        height,
        vec![
            Column::new("supplier".into(), suppliers),
            Column::new("item".into(), items),
            Column::new("forecast_period".into(), offsets),
            Column::new("forecast_quantity".into(), forecast_qty),
            Column::new("forecast_value".into(), forecast_val),
            Column::new("trend_component".into(), trend),
            Column::new("seasonal_component".into(), seasonal),
            Column::new("model_used".into(), models),
            Column::new("confidence_score".into(), confidence),
        ],
    )
    .map_err(KeplError::from)
}
