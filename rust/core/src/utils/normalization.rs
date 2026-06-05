// rust/core-engine/src/utils/normalization.rs
//! String and text normalization utilities.
//! Ensures canonical matching integrity for item and supplier identifiers.

use polars::prelude::*;

/// Generates a Polars expression to sanitize string columns.
/// Strips leading/trailing whitespace and enforces uppercase standardization
/// to prevent case-sensitive join mismatches during demand reconstruction.
pub fn canonical_string_expr(column_name: &str) -> Expr {
    col(column_name)
        .str()
        .strip_chars(lit(Null {}))
        .str()
        .to_uppercase()
}
