// rust/core/src/finance/valuation.rs
//! Inventory Valuation Engine.
//! Determines standing capital exposure utilizing Closing Stock snapshots and current unit economics.

use polars::prelude::*;

/// Computes total financial exposure tied to physical inventory.
/// Extends the foundational valuation by integrating the assumed freight burden.
pub fn calculate_inventory_exposure(closing_stock_lf: LazyFrame) -> LazyFrame {
    closing_stock_lf
        .select([
            col("Item Details").alias("item"),
            col("Qty.").alias("available_quantity"),
            col("Price").alias("unit_cost"),
        ])
        .with_columns(vec![
            (col("available_quantity") * col("unit_cost")).alias("base_inventory_value"),
        ])
        .with_column(super::freight::compute_freight_expr("base_inventory_value"))
        .with_column(
            (col("base_inventory_value") + col("freight_cost")).alias("total_inventory_exposure"),
        )
}
