// rust/core/src/analytics/supplier_analysis.rs
//! Supplier Performance and Risk Engine.
//! Fuses financial spend, chronological reliability, and delivery integrity into a unified risk profile.

use crate::utils::metrics::safe_divide_expr;
use polars::prelude::*;

/// Synthesizes comprehensive supplier metrics conforming to WORKBOOK_SCHEMA.md.
pub fn analyze_suppliers(
    pv_lf: LazyFrame,
    lead_time_lf: LazyFrame,
    pending_lf: LazyFrame,
) -> LazyFrame {
    // 1. Authoritative Spend Aggregation (PV is the financial source of truth)
    let spend_agg = pv_lf.group_by([col("Particulars")]).agg([
        col("Amount").sum().alias("total_spend"),
        col("Amount").count().alias("total_orders"),
    ]);

    // 2. Operational Reliability Aggregation
    let lt_agg = lead_time_lf.group_by([col("supplier")]).agg([
        col("lead_time_days").mean().alias("average_lead_time"),
        col("lead_time_days").std(1).alias("lead_time_stddev"),
        col("delivered_qty").sum().alias("total_deliveries"),
    ]);

    // 3. Risk Exposure Aggregation
    let pending_agg = pending_lf
        .group_by([col("supplier")])
        .agg([col("pending_qty").sum().alias("pending_deliveries")]);

    // 4. Matrix Synthesis
    spend_agg
        .join(
            lt_agg,
            [col("Particulars")],
            [col("supplier")],
            JoinArgs::new(JoinType::Left),
        )
        .join(
            pending_agg,
            [col("Particulars")],
            [col("supplier")],
            JoinArgs::new(JoinType::Left),
        )
        .with_columns(vec![
            // Reliability = Deliveries / Orders
            safe_divide_expr(col("total_deliveries"), col("total_orders"), 0.0)
                .alias("reliability_score"),
            safe_divide_expr(col("lead_time_stddev"), col("average_lead_time"), 0.0)
                .alias("risk_score"),
        ])
        .rename(["Particulars"], ["supplier"], true)
}
