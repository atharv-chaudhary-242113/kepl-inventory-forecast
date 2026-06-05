// rust/core/src/finance/costing.rs
//! Procurement Costing Engine.
//! Derives precise unit costs and aggregates supplier spend exclusively from Purchase Vouchers (PV).

use polars::prelude::*;

/// Computes the true unit cost from PV financial records.
/// Identifies and extracts exact cost baselines prior to aggregate analytics.
pub fn extract_unit_costs(pv_lf: LazyFrame) -> LazyFrame {
    pv_lf
        .select([
            col("Particulars").alias("supplier"),
            col("Item Details").alias("item"),
            col("Qty.").alias("quantity"),
            col("Amount").alias("total_base_cost"),
        ])
        // Domain rule: Prevent division by zero or negative quantities
        .filter(col("quantity").gt(lit(0.0)))
        .with_columns(vec![
            (col("total_base_cost") / col("quantity")).alias("unit_cost"),
        ])
}

/// Aggregates total capital deployed per supplier.
/// Enforces the separation of base cost and assumed freight components.
pub fn compute_supplier_spend(pv_lf: LazyFrame) -> LazyFrame {
    pv_lf
        .group_by([col("Particulars").alias("supplier")])
        .agg([
            col("Amount").sum().alias("total_base_spend"),
            col("Qty.").sum().alias("total_units_purchased"),
        ])
        .with_column(super::freight::compute_freight_expr("total_base_spend"))
        .with_column((col("total_base_spend") + col("freight_cost")).alias("total_landed_spend"))
}

pub fn build_financial_summary(pv_lf: LazyFrame) -> LazyFrame {
    pv_lf
        .group_by([
            col("Particulars").alias("supplier"),
            col("Item Details").alias("item"),
        ])
        .agg([
            col("Qty.").sum().alias("quantity"),
            col("Amount").sum().alias("total_cost"),
        ])
        // Guard the weighted unit-cost division against zero-quantity groups.
        .filter(col("quantity").gt(lit(0.0)))
        .with_column((col("total_cost") / col("quantity")).alias("unit_cost"))
        .with_column(super::freight::compute_freight_expr("total_cost")) // adds "freight_cost"
        .with_column((col("total_cost") + col("freight_cost")).alias("total_spend"))
        .select([
            col("supplier"),
            col("item"),
            col("quantity"),
            col("unit_cost"),
            col("freight_cost"),
            col("total_cost"),
            col("total_spend"),
        ])
}
