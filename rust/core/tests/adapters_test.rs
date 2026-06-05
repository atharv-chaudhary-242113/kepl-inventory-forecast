// tests/adapters_test.rs
use kepl_core::adapters::{frames_to_demand_series, sbc_frame_to_class_map};
use kepl_core::classification::sbc::DemandClass;
use kepl_core::domain::item::ItemId;
use kepl_core::domain::supplier::SupplierId;
use polars::prelude::*;

#[test]
fn demand_series_groups_and_sorts_by_period() {
    let df = df!(
        "supplier" => &["ABC", "ABC"],
        "item" => &["Wire", "Wire"],
        "period" => &["2025-02-01", "2025-01-01"], // out of order on purpose
        "demand_quantity" => &[5.0, 3.0],
        "demand_value" => &[50.0, 30.0],
    )
    .unwrap();

    let series = frames_to_demand_series(&df).unwrap();
    assert_eq!(series.len(), 1); // one item
    assert_eq!(series[0].records.len(), 2);
    // sorted ascending → Jan before Feb
    assert!(series[0].records[0].period_start < series[0].records[1].period_start);
}

#[test]
fn itemid_keys_match_across_both_adapters() {
    // The whole pipeline hinges on these two producing identical ItemId keys.
    let demand = df!(
        "supplier" => &["ABC"], "item" => &["Wire"],
        "period" => &["2025-01-01"], "demand_quantity" => &[3.0], "demand_value" => &[30.0],
    )
    .unwrap();
    let sbc = df!(
        "supplier" => &["ABC"], "item" => &["Wire"], "demand_class" => &["Smooth"],
    )
    .unwrap();

    let series = frames_to_demand_series(&demand).unwrap();
    let map = sbc_frame_to_class_map(&sbc).unwrap();

    let key = ItemId::new(SupplierId::new("ABC"), "Wire".to_string());
    assert_eq!(map.get(&key), Some(&DemandClass::Smooth));
    assert_eq!(series[0].item, key); // requires ItemId: PartialEq (it derives it)
}

#[test]
fn unknown_demand_class_is_rejected() {
    let sbc = df!(
        "supplier" => &["ABC"], "item" => &["Wire"], "demand_class" => &["Bogus"],
    )
    .unwrap();
    assert!(sbc_frame_to_class_map(&sbc).is_err());
}
