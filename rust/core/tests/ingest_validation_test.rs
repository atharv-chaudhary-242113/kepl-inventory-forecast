use kepl_core::ingest::validation::{canonicalize_report, normalize_supplier_expr};

use polars::prelude::*;

#[test]
fn supplier_normalization_removes_branch_suffix() {
    let df = df!(
        "Particulars" => &["ABC Electricals (Noida)"],
        "Item Details" => &["Copper Wire"]
    )
    .unwrap();

    let result = df
        .lazy()
        .with_column(normalize_supplier_expr("Particulars").alias("normalized"))
        .collect()
        .unwrap();

    let supplier = result
        .column("normalized")
        .unwrap()
        .str()
        .unwrap()
        .get(0)
        .unwrap();

    assert_eq!(supplier, "ABC Electricals");
}

#[test]
fn canonicalize_removes_empty_separator_rows() {
    let df = df!(
        "Particulars" => &[Some("ABC"), None, None],
        "Item Details" => &[Some("Item A"), None, Some("Item B")]
    )
    .unwrap();

    let result = canonicalize_report(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 2);
}

#[test]
fn canonicalize_forward_fills_supplier() {
    let df = df!(
        "Particulars" => &[Some("ABC"), None],
        "Item Details" => &[Some("Item A"), Some("Item B")]
    )
    .unwrap();

    let result = canonicalize_report(df.lazy()).collect().unwrap();

    let suppliers = result.column("Particulars").unwrap().str().unwrap();

    assert_eq!(suppliers.get(0), Some("ABC"));
    assert_eq!(suppliers.get(1), Some("ABC"));
}
