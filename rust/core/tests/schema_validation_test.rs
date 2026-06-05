use kepl_core::security::schema_validation::validate_schema_version;

#[test]
fn accepts_current_version() {
    assert!(validate_schema_version("1.0.0").is_ok());
}

#[test]
fn accepts_higher_version() {
    assert!(validate_schema_version("2.0.0").is_ok());
}

#[test]
fn rejects_lower_version() {
    assert!(validate_schema_version("0.9.0").is_err());
}
