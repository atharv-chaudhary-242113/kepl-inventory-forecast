use std::collections::HashMap;

use polars::prelude::*;

use crate::classification::sbc::DemandClass;
use crate::domain::item::ItemId;
use crate::domain::supplier::SupplierId;
use crate::error::KeplError;

pub fn sbc_frame_to_class_map(df: &DataFrame) -> Result<HashMap<ItemId, DemandClass>, KeplError> {
    let suppliers = df.column("supplier")?.str()?;

    let items = df.column("item")?.str()?;

    let classes = df.column("demand_class")?.str()?;

    let mut result = HashMap::new();

    for idx in 0..df.height() {
        let supplier = suppliers
            .get(idx)
            .ok_or_else(|| KeplError::Forecasting("Missing supplier".into()))?;

        let item = items
            .get(idx)
            .ok_or_else(|| KeplError::Forecasting("Missing item".into()))?;

        let class_str = classes
            .get(idx)
            .ok_or_else(|| KeplError::Forecasting("Missing demand class".into()))?;

        let demand_class = match class_str {
            "Smooth" => DemandClass::Smooth,
            "Erratic" => DemandClass::Erratic,
            "Intermittent" => DemandClass::Intermittent,
            "Lumpy" => DemandClass::Lumpy,
            other => {
                return Err(KeplError::Forecasting(format!(
                    "Unknown demand class: {}",
                    other
                )));
            }
        };

        result.insert(
            ItemId::new(SupplierId::new(supplier), item.to_string()),
            demand_class,
        );
    }

    Ok(result)
}
