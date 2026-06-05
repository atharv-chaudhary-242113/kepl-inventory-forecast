use kepl_core::finance::freight::{ASSUMED_FREIGHT_RATE, calculate_freight};

use rust_decimal_macros::dec;

#[test]
fn freight_rate_is_18_percent() {
    assert_eq!(ASSUMED_FREIGHT_RATE, dec!(0.18));
}

#[test]
fn freight_calculation_is_correct() {
    let freight = calculate_freight(dec!(1000));

    assert_eq!(freight, dec!(180.00));
}
