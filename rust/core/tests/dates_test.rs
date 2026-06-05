use chrono::Datelike;
use kepl_core::utils::dates::parse_erp_date;

#[test]
fn parses_iso_date() {
    let date = parse_erp_date("2025-01-15").unwrap();

    assert_eq!(date.year(), 2025);
    assert_eq!(date.month(), 1);
    assert_eq!(date.day(), 15);
}

#[test]
fn parses_indian_date() {
    let date = parse_erp_date("15/01/2025").unwrap();

    assert_eq!(date.year(), 2025);
    assert_eq!(date.month(), 1);
    assert_eq!(date.day(), 15);
}

#[test]
fn rejects_invalid_date() {
    assert!(parse_erp_date("not-a-date").is_err());
}
