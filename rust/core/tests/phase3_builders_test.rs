// tests/phase3_builders_test.rs
// Coverage for Phase-3 Increment A schema-aligned builders.
use kepl_core::analytics::fulfillment::build_fill_rate;
use kepl_core::analytics::inventory_analysis::valuate_inventory;
use kepl_core::analytics::lead_time::compute_lead_time;
use kepl_core::analytics::partnership_detection::detect_partnerships;
use kepl_core::analytics::pending_delivery::compute_pending_deliveries;
use kepl_core::analytics::price_analysis::build_price_variance;
use kepl_core::analytics::sourcing::build_sourcing_risk;
use kepl_core::classification::abc::build_abc_classification;
use kepl_core::finance::costing::build_financial_summary;
use kepl_core::forecasting::demand_reconstruction::reconstruct_demand;
use polars::prelude::*;

// Minimal procurement frame carrying the columns demand_projection reads.
fn proc_frame(dates: &[&str], qtys: &[f64]) -> LazyFrame {
    df!(
        "Particulars" => vec!["ABC"; dates.len()],
        "Item Details" => vec!["Wire"; dates.len()],
        "Date" => dates,
        "Qty." => qtys,
        "Amount" => qtys.iter().map(|q| q * 10.0).collect::<Vec<f64>>(),
    )
    .unwrap()
    .lazy()
}

#[test]
fn demand_history_collapses_to_monthly_periods() {
    // B.12: two GRN receipts in Jan must merge into ONE "2025-01-01" period with summed qty.
    let grn = proc_frame(&["2025-01-05", "2025-01-20"], &[3.0, 7.0]);
    let pv = proc_frame(&["2025-02-10"], &[5.0]);
    let stock = proc_frame(&["2025-02-10"], &[1.0]); // unused by reconstruct_demand

    let out = reconstruct_demand(grn, pv, stock)
        .unwrap()
        .collect()
        .unwrap();

    // Jan rows collapsed, Feb separate → exactly 2 monthly rows.
    assert_eq!(out.height(), 2);

    let periods = out.column("period").unwrap().str().unwrap();
    assert_eq!(periods.get(0), Some("2025-01-01")); // truncated to first-of-month
    assert_eq!(periods.get(1), Some("2025-02-01"));

    // 3 + 7 summed within the Jan bucket proves the monthly group_by works.
    let qty = out.column("demand_quantity").unwrap().f64().unwrap();
    assert_eq!(qty.get(0), Some(10.0));
}

#[test]
fn abc_classification_aggregates_and_aliases_to_schema() {
    // (ABC, Wire) appears twice and must aggregate to annual_value 100 before classification.
    let pv = df!(
        "Particulars" => &["ABC", "ABC", "XYZ"],
        "Item Details" => &["Wire", "Wire", "Pipe"],
        "Amount" => &[60.0, 40.0, 10.0],
    )
    .unwrap()
    .lazy();

    let out = build_abc_classification(pv).collect().unwrap();

    // Every WORKBOOK_SCHEMA column for ABC_Classification must be present and named exactly.
    for c in [
        "supplier",
        "item",
        "annual_value",
        "cumulative_percentage",
        "abc_class",
    ] {
        assert!(out.column(c).is_ok(), "missing schema column: {c}");
    }

    // Two distinct (supplier, item) groups → the duplicate Wire rows were aggregated, not kept.
    assert_eq!(out.height(), 2);
}

#[test]
fn partnerships_are_deduped_to_canonical_pairs() {
    // B.13: Alpha and Beta share 3 items. The symmetric self-join would emit (Alpha,Beta) AND
    // (Beta,Alpha); the a < b filter must leave exactly one canonical row.
    let pv = df!(
        "Particulars" => &["Beta", "Beta", "Beta", "Alpha", "Alpha", "Alpha"],
        "Item Details" => &["I1", "I2", "I3", "I1", "I2", "I3"],
    )
    .unwrap()
    .lazy();

    let out = detect_partnerships(pv).collect().unwrap();

    assert_eq!(out.height(), 1); // no mirror duplicate survives

    let a = out
        .column("supplier_a")
        .unwrap()
        .str()
        .unwrap()
        .get(0)
        .unwrap();
    let b = out
        .column("supplier_b")
        .unwrap()
        .str()
        .unwrap()
        .get(0)
        .unwrap();
    assert!(
        a < b,
        "pair must be lexicographically ordered (Alpha before Beta)"
    );
}

#[test]
fn financial_summary_aggregates_and_adds_freight() {
    let pv = df!(
        "Particulars" => &["ABC", "ABC"],
        "Item Details" => &["Wire", "Wire"],
        "Qty." => &[4.0, 6.0],
        "Amount" => &[40.0, 60.0],
    )
    .unwrap()
    .lazy();

    let out = build_financial_summary(pv).collect().unwrap();
    assert_eq!(out.height(), 1); // two PV lines for one item → aggregated to one row

    assert_eq!(
        out.column("quantity").unwrap().f64().unwrap().get(0),
        Some(10.0)
    );
    assert_eq!(
        out.column("total_cost").unwrap().f64().unwrap().get(0),
        Some(100.0)
    );
    assert_eq!(
        out.column("unit_cost").unwrap().f64().unwrap().get(0),
        Some(10.0)
    ); // 100/10
    // total_spend = base + 18% freight = 118 (f64 path, B.7 deferred to Phase-7)
    let spend = out
        .column("total_spend")
        .unwrap()
        .f64()
        .unwrap()
        .get(0)
        .unwrap();
    assert!((spend - 118.0).abs() < 1e-9);
}

#[test]
fn inventory_valuation_works_without_a_date_column() {
    // B.11 proof: the stock frame has NO Date column and valuation still succeeds.
    let stock = df!(
        "Item Details" => &["Wire", "Pipe"],
        "Qty." => &[10.0, 5.0],
        "Price" => &[2.0, 3.0],
    )
    .unwrap()
    .lazy();

    let out = valuate_inventory(stock, "2025-03-31").collect().unwrap();

    let val = out.column("inventory_value").unwrap().f64().unwrap();
    assert_eq!(val.get(0), Some(20.0)); // 10 * 2
    assert_eq!(val.get(1), Some(15.0)); // 5 * 3

    let snap = out.column("snapshot_date").unwrap().str().unwrap();
    assert_eq!(snap.get(0), Some("2025-03-31")); // stamped literal, not a row column
}

#[test]
fn pending_deliveries_carry_voucher_and_filter_open_orders() {
    // POV: ordered 10 Wire on Jan 1 under voucher V1. GRN: only 4 delivered on Jan 10.
    let pov = df!(
        "Particulars" => &["ABC"], "Item Details" => &["Wire"], "Vch/Bill no" => &["V1"],
        "Date" => &["2025-01-01"], "Qty." => &[10.0], "Unit" => &["nos"],
        "Price" => &[5.0], "Amount" => &[50.0],
    )
    .unwrap()
    .lazy();
    let grn = df!(
        "Particulars" => &["ABC"], "Item Details" => &["Wire"], "Vch/Bill no" => &["G1"],
        "Date" => &["2025-01-10"], "Qty." => &[4.0], "Unit" => &["nos"],
        "Price" => &[5.0], "Amount" => &[20.0],
    )
    .unwrap()
    .lazy();

    let pending = compute_pending_deliveries(compute_lead_time(pov, grn))
        .collect()
        .unwrap();

    assert_eq!(pending.height(), 1); // 10 - 4 = 6 pending > 0
    assert_eq!(
        pending
            .column("voucher_number")
            .unwrap()
            .str()
            .unwrap()
            .get(0),
        Some("V1") // carried from POV through lead_time, not the GRN's G1
    );
    assert_eq!(
        pending.column("pending_qty").unwrap().f64().unwrap().get(0),
        Some(6.0)
    );
    assert!(pending.column("order_date").is_ok()); // aliased from the parsed pov_date
}

#[test]
fn price_variance_captures_cross_supplier_spread() {
    // Same item, two suppliers: ₹10 vs ₹20 per unit → spread 10, relative spread 100%.
    let pv = df!(
        "Particulars" => &["A", "B"],
        "Item Details" => &["Wire", "Wire"],
        "Qty." => &[1.0, 1.0],
        "Amount" => &[10.0, 20.0],
    )
    .unwrap()
    .lazy();

    let out = build_price_variance(pv).collect().unwrap();
    assert_eq!(out.height(), 1);
    assert_eq!(
        out.column("min_unit_cost").unwrap().f64().unwrap().get(0),
        Some(10.0)
    );
    assert_eq!(
        out.column("max_unit_cost").unwrap().f64().unwrap().get(0),
        Some(20.0)
    );
    assert_eq!(
        out.column("price_spread").unwrap().f64().unwrap().get(0),
        Some(10.0)
    );
    let pct = out
        .column("price_spread_pct")
        .unwrap()
        .f64()
        .unwrap()
        .get(0)
        .unwrap();
    assert!((pct - 1.0).abs() < 1e-9); // priciest source is 100% over the cheapest
    assert_eq!(
        out.column("supplier_count").unwrap().u32().unwrap().get(0),
        Some(2)
    );
}

#[test]
fn sourcing_risk_flags_single_source_items() {
    // Wire from two suppliers, Pipe from one → Pipe must be flagged single-source.
    let pv = df!(
        "Particulars" => &["A", "B", "A"],
        "Item Details" => &["Wire", "Wire", "Pipe"],
        "Amount" => &[10.0, 20.0, 5.0],
    )
    .unwrap()
    .lazy();

    // Sort by item so row order is deterministic: Pipe (0) before Wire (1).
    let out = build_sourcing_risk(pv)
        .sort(vec!["item"], SortMultipleOptions::default())
        .collect()
        .unwrap();

    assert_eq!(out.height(), 2);
    let risk = out.column("sourcing_risk").unwrap().str().unwrap();
    assert_eq!(risk.get(0), Some("Single-Source")); // Pipe
    assert_eq!(risk.get(1), Some("Dual-Source")); // Wire
    assert_eq!(
        out.column("supplier_count").unwrap().u32().unwrap().get(0),
        Some(1)
    );
}

#[test]
fn fill_rate_measures_under_delivery() {
    // Ordered 10, received 7 → 0.7 fill rate.
    let pov = df!("Particulars" => &["A"], "Qty." => &[10.0])
        .unwrap()
        .lazy();
    let grn = df!("Particulars" => &["A"], "Qty." => &[7.0])
        .unwrap()
        .lazy();

    let out = build_fill_rate(pov, grn).collect().unwrap();
    assert_eq!(
        out.column("total_ordered").unwrap().f64().unwrap().get(0),
        Some(10.0)
    );
    assert_eq!(
        out.column("total_received").unwrap().f64().unwrap().get(0),
        Some(7.0)
    );
    let fr = out
        .column("fill_rate")
        .unwrap()
        .f64()
        .unwrap()
        .get(0)
        .unwrap();
    assert!((fr - 0.7).abs() < 1e-9);
}
