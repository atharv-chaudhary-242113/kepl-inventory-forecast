use kepl_core::ingest::validation::{canonicalize_report, enforce_domain_constraints};

use polars::prelude::*;

#[test]
fn supplier_hierarchy_is_forward_filled() {
    let df = df!(
        "Particulars" => &[
            Some("ABC Electricals"),
            None,
            None,
            Some("XYZ Traders"),
            None
        ],
        "Item Details" => &[
            Some("Copper Wire 2.5mm"),
            Some("Copper Wire 4mm"),
            Some("Copper Wire 6mm"),
            Some("PVC Tape"),
            Some("Cable Tie")
        ]
    )
    .unwrap();

    let result = canonicalize_report(df.lazy()).collect().unwrap();

    let suppliers = result.column("Particulars").unwrap().str().unwrap();

    assert_eq!(suppliers.get(0), Some("ABC Electricals"));
    assert_eq!(suppliers.get(1), Some("ABC Electricals"));
    assert_eq!(suppliers.get(2), Some("ABC Electricals"));
    assert_eq!(suppliers.get(3), Some("XYZ Traders"));
    assert_eq!(suppliers.get(4), Some("XYZ Traders"));
}

#[test]
fn separator_rows_are_removed() {
    let df = df!(
        "Particulars" => &[
            Some("ABC Electricals"),
            None,
            None
        ],
        "Item Details" => &[
            Some("Copper Wire"),
            None,
            Some("PVC Tape")
        ]
    )
    .unwrap();

    let result = canonicalize_report(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 2);
}

#[test]
fn supplier_branches_are_normalized() {
    let df = df!(
        "Particulars" => &[
            Some("ABC Electricals (Noida)"),
            Some("ABC Electricals (Delhi)")
        ],
        "Item Details" => &[
            Some("Copper Wire"),
            Some("PVC Tape")
        ]
    )
    .unwrap();

    let result = canonicalize_report(df.lazy()).collect().unwrap();

    let suppliers = result.column("Particulars").unwrap().str().unwrap();

    assert_eq!(suppliers.get(0), Some("ABC Electricals"));
    assert_eq!(suppliers.get(1), Some("ABC Electricals"));
}

#[test]
fn negative_quantities_are_rejected() {
    let df = df!(
        "Qty." => &[10.0, -5.0],
        "Price" => &[100.0, 100.0],
        "Amount" => &[1000.0, 500.0]
    )
    .unwrap();

    let result = enforce_domain_constraints(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 1);
}

#[test]
fn negative_prices_are_rejected() {
    let df = df!(
        "Qty." => &[10.0],
        "Price" => &[-100.0],
        "Amount" => &[1000.0]
    )
    .unwrap();

    let result = enforce_domain_constraints(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 0);
}

#[test]
fn negative_amounts_are_rejected() {
    let df = df!(
        "Qty." => &[10.0],
        "Price" => &[100.0],
        "Amount" => &[-1000.0]
    )
    .unwrap();

    let result = enforce_domain_constraints(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 0);
}

#[test]
fn valid_procurement_rows_survive_validation() {
    let df = df!(
        "Qty." => &[10.0],
        "Price" => &[100.0],
        "Amount" => &[1000.0]
    )
    .unwrap();

    let result = enforce_domain_constraints(df.lazy()).collect().unwrap();

    assert_eq!(result.height(), 1);
}
