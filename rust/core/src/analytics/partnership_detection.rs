// rust/core/src/analytics/partnership_detection.rs
//! Supplier Partnership Detection.
//! Identifies potential collusive or redundant vendor relationships via catalog crossover analysis.

use polars::prelude::*;

/// Flags parallel suppliers who consistently provide identical item details.
/// Domain Rule: Observed Frequency >= 3 triggers a partnership review.
pub fn detect_partnerships(pv_lf: LazyFrame) -> LazyFrame {
    let left = pv_lf
        .clone()
        .select([col("Particulars").alias("supplier_a"), col("Item Details")]);
    let right = pv_lf.select([col("Particulars").alias("supplier_b"), col("Item Details")]);

    left.join(
        right,
        [col("Item Details")],
        [col("Item Details")],
        JoinArgs::new(JoinType::Inner),
    )
    // Eliminate identity matches
    .filter(col("supplier_a").lt(col("supplier_b")))
    .group_by([col("supplier_a"), col("supplier_b")])
    .agg([col("Item Details").n_unique().alias("matching_events")])
    // Domain threshold enforcement
    .filter(col("matching_events").gt_eq(lit(3)))
    .with_columns(vec![
        // Baselines required by WORKBOOK_SCHEMA.md
        lit(1.0).alias("confidence_score"),
        lit("Suspected").alias("status"),
    ])
}
