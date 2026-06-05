// rust/core/src/analytics/fulfillment.rs
//! Supplier Fulfillment Engine.
//! Measures how completely each supplier delivers what was ordered: received (GRN) vs ordered (POV).

use crate::utils::metrics::safe_divide_expr;
use polars::prelude::*;

/// Aggregate per-supplier fill rate. This is the COARSE version (total received / total ordered
/// over the whole window), deliberately avoiding per-order FIFO line-matching — that precision
/// (B.5) is Phase-7. As a KPI, a fill_rate well under 1.0 flags a chronic under-deliverer.
pub fn build_fill_rate(pov_lf: LazyFrame, grn_lf: LazyFrame) -> LazyFrame {
    let ordered = pov_lf
        .group_by([col("Particulars").alias("supplier")])
        .agg([col("Qty.").sum().alias("total_ordered")]);

    let received = grn_lf
        .group_by([col("Particulars").alias("supplier")])
        .agg([col("Qty.").sum().alias("total_received")]);

    ordered
        .join(
            received,
            [col("supplier")],
            [col("supplier")],
            JoinArgs::new(JoinType::Left),
        )
        // A supplier with orders but no receipts yet → received is null → treat as 0 delivered.
        .with_column(col("total_received").fill_null(lit(0.0)))
        .with_column(
            safe_divide_expr(col("total_received"), col("total_ordered"), 0.0).alias("fill_rate"),
        )
        .select([
            col("supplier"),
            col("total_ordered"),
            col("total_received"),
            col("fill_rate"),
        ])
}
