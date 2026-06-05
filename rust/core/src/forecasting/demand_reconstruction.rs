// rust/core/src/forecasting/demand_reconstruction.rs
//! Demand Reconstruction Engine.
//! Synthesizes a chronological demand sequence from disparate procurement lifecycle events (GRN, PV, Closing Stock).

use crate::error::KeplError;
use polars::prelude::*;

/// Reconstructs the historical demand time-series.
/// DOMAIN_RULES.md specifies that actual sales ledgers are unavailable;
/// consumption must be inferred via procurement receipts and stock deltas.

fn demand_projection(lf: LazyFrame) -> LazyFrame {
    lf.select([
        col("Particulars").alias("supplier"),
        col("Item Details").alias("item"),
        (col("Date").str().slice(lit(0), lit(7)) + lit("-01")).alias("period"),
        col("Qty.").alias("demand_quantity"),
        col("Amount").alias("demand_value"),
    ])
}

pub fn reconstruct_demand(
    grn_lf: LazyFrame,
    pv_lf: LazyFrame,
    _closing_stock_lf: LazyFrame,
) -> Result<LazyFrame, KeplError> {
    // The precise reconstruction methodology is marked as a "Pending Business Decision".
    // This implementation provides the architectural baseline: aligning GRN and PV dates.

    let grn_demand = demand_projection(grn_lf);

    let pv_demand = demand_projection(pv_lf);

    // Concatenate physical receipts and financial transactions, prioritizing PV valuations
    let merged = concat(vec![grn_demand, pv_demand], UnionArgs::default())
        .map_err(|e| KeplError::Computation(e.to_string()))?;

    Ok(merged
        .group_by([col("supplier"), col("item"), col("period")])
        .agg([col("demand_quantity").sum(), col("demand_value").sum()])
        .sort(vec!["period"], SortMultipleOptions::default()))
}
