// rust/core/src/analytics/inventory_analysis.rs
//! Inventory Valuation Engine.
//! Executes structural valuation routines against point-in-time closing stock.

use polars::prelude::*;

/// Calculates total capital deployed in standing inventory based on current standard pricing.
pub fn valuate_inventory(closing_stock_lf: LazyFrame, snapshot_date: &str) -> LazyFrame {
    closing_stock_lf
        .select([
            col("Item Details").alias("item"),
            col("Qty.").alias("quantity"),
            col("Price").alias("unit_cost"),
            lit(snapshot_date).alias("snapshot_date"),
        ])
        .with_column((col("quantity") * col("unit_cost")).alias("inventory_value"))
}
