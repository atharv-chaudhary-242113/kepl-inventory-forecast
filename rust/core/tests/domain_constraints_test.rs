use kepl_core::ingest::validation::enforce_domain_constraints;

use polars::prelude::*;

#[test]
fn negative_quantity_is_removed() {
    let df = df!(
        "Qty." => &[10.0, -5.0],
        "Price" => &[1.0, 1.0],
        "Amount" => &[10.0, 5.0]
    )
    .unwrap();

    let result = enforce_domain_constraints(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 1);
}

#[test]
fn negative_price_is_removed() {
    let df = df!(
        "Qty." => &[10.0],
        "Price" => &[-1.0],
        "Amount" => &[10.0]
    )
    .unwrap();

    let result = enforce_domain_constraints(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 0);
}

#[test]
fn valid_rows_survive_constraints() {
    let df = df!(
        "Qty." => &[10.0],
        "Price" => &[5.0],
        "Amount" => &[50.0]
    )
    .unwrap();

    let result = enforce_domain_constraints(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 1);
}
