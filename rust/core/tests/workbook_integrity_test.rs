use kepl_core::security::workbook_validation::verify_workbook_integrity;
use std::path::Path;

#[test]
fn accepts_matching_hash() {
    let result = verify_workbook_integrity(Path::new("dummy.xlsx"), "abc123", "abc123");

    assert!(result.is_ok());
}

#[test]
fn rejects_mismatched_hash() {
    let result = verify_workbook_integrity(Path::new("dummy.xlsx"), "abc123", "xyz999");

    assert!(result.is_err());
}
