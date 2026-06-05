use polars::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum AbcClass {
    A,
    B,
    C,
}

pub fn classify_abc(lf: LazyFrame, value_col: &str) -> LazyFrame {
    let total_val = col(value_col).sum();
    lf.sort(
        vec![value_col],
        SortMultipleOptions::default().with_order_descending(true),
    )
    .with_column((col(value_col).cum_sum(false) / total_val).alias("cum_pct"))
    .with_column(
        when(col("cum_pct").lt_eq(lit(0.80)))
            .then(lit("A"))
            .when(col("cum_pct").lt_eq(lit(0.95)))
            .then(lit("B"))
            .otherwise(lit("C"))
            .alias("abc_class"),
    )
}

pub fn build_abc_classification(pv_lf: LazyFrame) -> LazyFrame {
    let annual = pv_lf
        .group_by([
            col("Particulars").alias("supplier"),
            col("Item Details").alias("item"),
        ])
        .agg([col("Amount").sum().alias("annual_value")]);

    classify_abc(annual, "annual_value").select([
        col("supplier"),
        col("item"),
        col("annual_value"),
        col("cum_pct").alias("cumulative_percentage"),
        col("abc_class"),
    ])
}
