// rust/core/src/analytics/pending_delivery.rs
//! Pending Deliveries Engine.
//! Identifies open procurement cycles where Ordered Quantity exceeds Delivered Quantity.

use polars::prelude::*;

/// Computes the backlog of pending inventory deliveries and calculates order age.
pub fn compute_pending_deliveries(lead_time_lf: LazyFrame) -> LazyFrame {
    lead_time_lf
        .with_column((col("ordered_qty") - col("delivered_qty")).alias("pending_qty"))
        .filter(col("pending_qty").gt(lit(0.0)))
        .with_column(
            (col("pov_date").max() - col("pov_date"))
                .dt()
                .total_days(true)
                .alias("age_days"),
        )
        .select([
            col("supplier"),
            col("item"),
            col("voucher_number"),
            col("ordered_qty"),
            col("delivered_qty"),
            col("pending_qty"),
            col("pov_date").alias("order_date"),
            col("age_days"),
        ])
}
