// rust/core/src/analytics/sourcing.rs
//! Sourcing Risk Engine.
//! Maps each item to how many suppliers actually supply it. Single-sourced high-value items are
//! your supply-chain fragility points — one supplier failing stops that line entirely.

use polars::prelude::*;

/// Per-item supplier concentration from PV, weighted by annual_value so the dashboard can rank
/// single-source items by how much money is exposed (a single-source ₹5L item matters more than
/// a single-source ₹500 one).
pub fn build_sourcing_risk(pv_lf: LazyFrame) -> LazyFrame {
    pv_lf
        .group_by([col("Item Details").alias("item")])
        .agg([
            col("Particulars").n_unique().alias("supplier_count"),
            col("Amount").sum().alias("annual_value"),
        ])
        .with_column(
            // Bucket the risk. <=1 supplier is the danger zone; 2 is fragile-but-hedged; 3+ is safe.
            when(col("supplier_count").lt_eq(lit(1)))
                .then(lit("Single-Source"))
                .when(col("supplier_count").lt_eq(lit(2)))
                .then(lit("Dual-Source"))
                .otherwise(lit("Multi-Source"))
                .alias("sourcing_risk"),
        )
        .select([
            col("item"),
            col("supplier_count"),
            col("annual_value"),
            col("sourcing_risk"),
        ])
}
