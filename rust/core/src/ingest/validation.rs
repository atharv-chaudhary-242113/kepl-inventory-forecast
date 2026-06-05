// rust/core/src/ingest/validation.rs
//! Enforces INPUT_SCHEMA.md constraints via Polars LazyFrame transformations.
//! Implements dynamic header detection, forward-filling, and supplier normalization.

use polars::prelude::*;

/// Normalizes supplier names by removing parenthetical suffixes.
/// Example: "ABC Electricals (Noida)" -> "ABC Electricals"
pub fn normalize_supplier_expr(column_name: &str) -> Expr {
    col(column_name)
        .str()
        .replace_all(lit(r"\s*\(.*?\)\s*"), lit(""), false)
        .str()
        .strip_chars(lit(Null {}))
}

/// Applies the canonicalization sequence defined in INPUT_SCHEMA.md.
/// 1. Remove Empty Separator Rows
/// 2. Forward Fill Grouped Columns
/// 3. Normalize Supplier Names
pub fn canonicalize_report(lf: LazyFrame) -> LazyFrame {
    lf.filter(
        // Reject rows where both Particulars and Item Details are null or empty
        col("Particulars")
            .is_not_null()
            .and(col("Particulars").str().len_chars().gt(lit(0)))
            .or(col("Item Details")
                .is_not_null()
                .and(col("Item Details").str().len_chars().gt(lit(0)))),
    )
    .with_column(
        // Forward fill the supplier column for hierarchical grouping
        col("Particulars").fill_null_with_strategy(FillNullStrategy::Forward(None)),
    )
    .with_column(
        // Normalize the supplier name
        normalize_supplier_expr("Particulars").alias("Particulars"),
    )
    .filter(
        // Final sanity check post-normalization
        col("Particulars")
            .is_not_null()
            .and(col("Particulars").str().len_chars().gt(lit(0)))
            .and(col("Item Details").is_not_null())
            .and(col("Item Details").str().len_chars().gt(lit(0))),
    )
}

/// Enforces non-negative constraints on financial and physical quantity columns.
pub fn enforce_domain_constraints(lf: LazyFrame) -> LazyFrame {
    lf.filter(
        col("Qty.")
            .gt_eq(lit(0.0))
            .and(col("Price").gt_eq(lit(0.0)))
            .and(col("Amount").gt_eq(lit(0.0))),
    )
}
