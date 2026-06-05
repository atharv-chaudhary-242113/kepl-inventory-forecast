use std::collections::HashMap;

use chrono::NaiveDate;
use polars::prelude::*;
use rust_decimal::Decimal;

use crate::domain::demand::{DemandRecord, DemandSeries};
use crate::domain::item::ItemId;
use crate::domain::supplier::SupplierId;
use crate::error::KeplError;

pub fn frames_to_demand_series(df: &DataFrame) -> Result<Vec<DemandSeries>, KeplError> {
    let suppliers = df.column("supplier")?.str()?;
    let items = df.column("item")?.str()?;
    let periods = df.column("period")?.str()?;
    let quantities = df.column("demand_quantity")?.f64()?;

    let values = df.column("demand_value")?.f64()?;

    let mut grouped: HashMap<ItemId, Vec<DemandRecord>> = HashMap::new();

    for idx in 0..df.height() {
        let supplier = suppliers
            .get(idx)
            .ok_or_else(|| KeplError::Forecasting("Missing supplier".into()))?;

        let item = items
            .get(idx)
            .ok_or_else(|| KeplError::Forecasting("Missing item".into()))?;

        let quantity = quantities.get(idx).unwrap_or(0.0);

        let value = values.get(idx).unwrap_or(0.0);

        let period_str = periods
            .get(idx)
            .ok_or_else(|| KeplError::Forecasting("Missing period".into()))?;

        let date = NaiveDate::parse_from_str(&period_str, "%Y-%m-%d")
            .map_err(|e| KeplError::Forecasting(e.to_string()))?;

        let item_id = ItemId::new(SupplierId::new(supplier), item.to_string());

        grouped
            .entry(item_id.clone())
            .or_default()
            .push(DemandRecord {
                period_start: date,
                item: item_id,
                quantity,
                value: Decimal::from_f64_retain(value).unwrap_or_default(),
            });
    }

    let mut result = Vec::new();

    for (item, mut records) in grouped {
        records.sort_by_key(|r| r.period_start);

        result.push(DemandSeries { item, records });
    }

    Ok(result)
}
