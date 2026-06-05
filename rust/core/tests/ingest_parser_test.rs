use kepl_core::ingest::parser::IngestionPipeline;
use kepl_core::ingest::parser::detect_header_row;
use polars::prelude::*;

#[test]
fn exact_column_names_are_accepted() {
    let mut df = df!(
        "Date" => &["2025-01-01"],
        "Vch/Bill no" => &["PO001"],
        "Particulars" => &["ABC"],
        "Item Details" => &["Copper Wire"],
        "Qty." => &[10.0],
        "Unit" => &["Nos"],
        "Price" => &[100.0],
        "Amount" => &[1000.0]
    )
    .unwrap();

    let result = IngestionPipeline::rename_columns_fuzzy(
        &mut df,
        &[
            "Date",
            "Vch/Bill no",
            "Particulars",
            "Item Details",
            "Qty.",
            "Unit",
            "Price",
            "Amount",
        ],
    );

    assert!(result.is_ok());
}

#[test]
fn case_insensitive_matching_works() {
    let mut df = df!(
        "date" => &["2025-01-01"],
        "vch/bill no" => &["PO001"],
        "particulars" => &["ABC"],
        "item details" => &["Copper Wire"],
        "qty." => &[10.0],
        "unit" => &["Nos"],
        "price" => &[100.0],
        "amount" => &[1000.0]
    )
    .unwrap();

    let result = IngestionPipeline::rename_columns_fuzzy(
        &mut df,
        &[
            "Date",
            "Vch/Bill no",
            "Particulars",
            "Item Details",
            "Qty.",
            "Unit",
            "Price",
            "Amount",
        ],
    );

    assert!(result.is_ok());

    assert!(df.column("Date").is_ok());
    assert!(df.column("Particulars").is_ok());
}

#[test]
fn whitespace_insensitive_matching_works() {
    let mut df = df!(
        " Date " => &["2025-01-01"],
        " Vch/Bill no " => &["PO001"],
        " Particulars " => &["ABC"],
        " Item Details " => &["Copper Wire"],
        " Qty. " => &[10.0],
        " Unit " => &["Nos"],
        " Price " => &[100.0],
        " Amount " => &[1000.0]
    )
    .unwrap();

    let result = IngestionPipeline::rename_columns_fuzzy(
        &mut df,
        &[
            "Date",
            "Vch/Bill no",
            "Particulars",
            "Item Details",
            "Qty.",
            "Unit",
            "Price",
            "Amount",
        ],
    );

    assert!(result.is_ok());
}

#[test]
fn missing_required_column_is_rejected() {
    let mut df = df!(
        "Date" => &["2025-01-01"],
        "Particulars" => &["ABC"]
    )
    .unwrap();

    let result = IngestionPipeline::rename_columns_fuzzy(
        &mut df,
        &["Date", "Vch/Bill no", "Particulars", "Item Details"],
    );

    assert!(result.is_err());
}

#[test]
fn header_after_metadata_rows_is_found() {
    let grid = vec![
        vec!["KEPL Pvt Ltd".into(), "".into()], // company row
        vec!["Purchase Order Voucher".into(), "".into()], // title row
        vec!["".into(), "".into()],             // blank separator
        vec!["Date".into(), "Particulars".into()], // real header at index 3
        vec!["2025-01-01".into(), "ABC Electricals".into()],
    ];
    assert_eq!(detect_header_row(&grid, &["Date", "Particulars"]), Some(3));
}

#[test]
fn no_matching_header_returns_none() {
    let grid = vec![vec!["foo".into(), "bar".into()]];
    assert_eq!(detect_header_row(&grid, &["Date", "Particulars"]), None);
}

#[test]
fn header_detection_is_case_and_space_insensitive() {
    let grid = vec![vec![" DATE ".into(), "particulars".into()]];
    assert_eq!(detect_header_row(&grid, &["Date", "Particulars"]), Some(0));
}
