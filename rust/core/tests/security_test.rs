use std::fs::File;
use std::path::PathBuf;

use kepl_core::security::path_validation::{enforce_file_size_limits, validate_file_path};

#[test]
fn validates_normal_file() {
    let path = PathBuf::from("test_file.xlsx");

    File::create(&path).unwrap();

    let result = validate_file_path(&path);

    assert!(result.is_ok());

    std::fs::remove_file(path).unwrap();
}

#[test]
fn rejects_wrong_extension() {
    let path = PathBuf::from("bad.txt");

    File::create(&path).unwrap();

    let result = validate_file_path(&path);

    assert!(result.is_err());

    std::fs::remove_file(path).unwrap();
}

#[test]
fn file_size_check_runs() {
    let path = PathBuf::from("size_test.xlsx");

    File::create(&path).unwrap();

    let result = enforce_file_size_limits(&path);

    assert!(result.is_ok());

    std::fs::remove_file(path).unwrap();
}
