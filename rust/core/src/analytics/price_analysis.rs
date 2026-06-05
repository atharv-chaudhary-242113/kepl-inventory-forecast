// rust/core/src/analytics/price_analysis.rs
//! Price Variance Engine.
//! Surfaces per-item unit-cost dispersion across suppliers and time — the raw signal for
//! negotiation leverage ("we pay 2x more for this item from one source than another").

use crate::utils::metrics::safe_divide_expr;
use polars::prelude::*;

/// Per-item unit-cost dispersion from PV (the authoritative price source).
/// unit_cost is derived per line (Amount / Qty.), then min/max/avg are taken across every PV row
/// for that item — collapsing both the supplier and time dimensions into one "how spread out is
/// this item's price" view.
pub fn build_price_variance(pv_lf: LazyFrame) -> LazyFrame {
    pv_lf
        // Guard the per-line unit cost against divide-by-zero.
        .filter(col("Qty.").gt(lit(0.0)))
        .with_column((col("Amount") / col("Qty.")).alias("unit_cost"))
        .group_by([col("Item Details").alias("item")])
        .agg([
            col("unit_cost").min().alias("min_unit_cost"),
            col("unit_cost").max().alias("max_unit_cost"),
            col("unit_cost").mean().alias("avg_unit_cost"),
            // How many distinct suppliers price this item — context for the spread.
            col("Particulars").n_unique().alias("supplier_count"),
        ])
        .with_column((col("max_unit_cost") - col("min_unit_cost")).alias("price_spread"))
        .with_column(
            // Relative spread = (max - min) / min. This is the negotiation signal: a spread_pct of
            // 1.0 means the priciest source charges double the cheapest. safe_divide guards min == 0.
            safe_divide_expr(col("price_spread"), col("min_unit_cost"), 0.0)
                .alias("price_spread_pct"),
        )
        .select([
            col("item"),
            col("min_unit_cost"),
            col("max_unit_cost"),
            col("avg_unit_cost"),
            col("price_spread"),
            col("price_spread_pct"),
            col("supplier_count"),
        ])
}
