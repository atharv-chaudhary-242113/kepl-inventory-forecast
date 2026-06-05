// rust/core/src/classification/sbc.rs
//! Syntetos-Boylan Classification (SBC) Engine.
//! Routes demand streams into Smooth, Erratic, Intermittent, or Lumpy categories
//! based on Average Inter-Demand Interval (ADI) and Squared Coefficient of Variation (CV²).

use polars::prelude::*;
use serde::{Deserialize, Serialize};

/// Syntetos-Boylan Classification (SBC) categories.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DemandClass {
    Smooth,
    Erratic,
    Intermittent,
    Lumpy,
}

const ADI_THRESHOLD: f64 = 1.32;
const CV2_THRESHOLD: f64 = 0.49;

/// Computes ADI (Average Inter-Demand Interval).
/// ADI = Total periods / Periods with non-zero demand
pub fn compute_adi_expr(demand_col: &str) -> Expr {
    let total_periods = col(demand_col).count().cast(DataType::Float64);
    let non_zero_periods = col(demand_col)
        .filter(col(demand_col).gt(lit(0.0)))
        .count()
        .cast(DataType::Float64);

    (total_periods / non_zero_periods).alias("adi")
}

/// Computes CV² (Squared Coefficient of Variation) of strictly non-zero demands.
/// CV² = (Standard Deviation of non-zero demands / Mean of non-zero demands)²
pub fn compute_cv2_expr(demand_col: &str) -> Expr {
    let non_zero_demand = col(demand_col).filter(col(demand_col).gt(lit(0.0)));
    let std_dev = non_zero_demand.clone().std(1); // 1 degree of freedom (sample std)
    let mean = non_zero_demand.mean();

    (std_dev / mean).pow(2.0).alias("cv_squared")
}

/// Generates the Polars expression to classify demand based on computed ADI and CV².
pub fn sbc_class_expr(adi_col: &str, cv2_col: &str) -> Expr {
    when(
        col(adi_col)
            .lt(lit(ADI_THRESHOLD))
            .and(col(cv2_col).lt(lit(CV2_THRESHOLD))),
    )
    .then(lit("Smooth"))
    .when(
        col(adi_col)
            .lt(lit(ADI_THRESHOLD))
            .and(col(cv2_col).gt_eq(lit(CV2_THRESHOLD))),
    )
    .then(lit("Erratic"))
    .when(
        col(adi_col)
            .gt_eq(lit(ADI_THRESHOLD))
            .and(col(cv2_col).lt(lit(CV2_THRESHOLD))),
    )
    .then(lit("Intermittent"))
    .otherwise(lit("Lumpy"))
    .alias("demand_class")
}

/// Applies SBC to a chronological demand history LazyFrame.
/// Requires grouping by `supplier` and `item` to calculate metrics over the `demand_quantity` vector.
pub fn apply_sbc_classification(demand_history_lf: LazyFrame) -> LazyFrame {
    demand_history_lf
        .group_by(vec![col("supplier"), col("item")])
        .agg(vec![
            compute_adi_expr("demand_quantity"),
            compute_cv2_expr("demand_quantity"),
        ])
        .with_column(sbc_class_expr("adi", "cv_squared"))
}
