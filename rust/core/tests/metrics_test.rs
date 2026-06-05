use kepl_core::utils::metrics::safe_divide_expr;
use polars::prelude::*;

#[test]
fn safe_divide_expression_builds() {
    let expr = safe_divide_expr(col("sales"), col("qty"), 0.0);

    let debug = format!("{expr:?}");

    assert!(!debug.is_empty());
}
