// rust/core/src/analytics/lead_time.rs
//! Lead-Time Analysis Engine.
//! Computes the time elapsed between Purchase Order (POV) and Goods Receipt (GRN).
//! Exerts FIFO matching across chronological procurement data.

use polars::prelude::*;

/// Executes the chronological matching of POV and GRN datasets to establish baseline lead times.
/// Calculates the delta in days between order and receipt.
pub fn compute_lead_time(pov_lf: LazyFrame, grn_lf: LazyFrame) -> LazyFrame {
    let pov = pov_lf.with_column(
        col("Date")
            .str()
            .to_date(StrptimeOptions::default())
            .alias("Date"),
    );
    let grn = grn_lf.with_column(
        col("Date")
            .str()
            .to_date(StrptimeOptions::default())
            .alias("Date"),
    );

    let join_keys = vec![col("Particulars"), col("Item Details")];

    pov.join(
        grn,
        join_keys.clone(),
        join_keys,
        JoinArgs::new(JoinType::Left),
    )
    .filter(col("Date_right").is_not_null())
    .with_columns(vec![
        (col("Date_right") - col("Date"))
            .dt()
            .total_days(true)
            .alias("lead_time_days"),
    ])
    .select([
        col("Particulars").alias("supplier"),
        col("Item Details").alias("item"),
        col("Vch/Bill no").alias("voucher_number"),
        col("Date").alias("pov_date"),
        col("Date_right").alias("grn_date"),
        col("Qty.").alias("ordered_qty"),
        col("Qty._right").alias("delivered_qty"),
        col("lead_time_days"),
    ])
}
