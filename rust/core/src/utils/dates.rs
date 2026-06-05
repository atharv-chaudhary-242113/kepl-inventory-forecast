// rust/core-engine/src/utils/dates.rs
//! Date parsing and normalization utility.
//! Centralizes ERP date parsing logic to enforce ISO-8601 internal standardization
//! and mitigate the Date Parsing Errors identified in THREAT_MODEL.md.

use chrono::{NaiveDate, ParseError};
use polars::prelude::*;

/// Parses a string into a chronologically valid NaiveDate, attempting common Indian ERP formats.
pub fn parse_erp_date(date_str: &str) -> Result<NaiveDate, ParseError> {
    let formats = [
        "%Y-%m-%d", // Standard ISO-8601
        "%d-%m-%Y", // Common Indian DD-MM-YYYY
        "%d/%m/%Y", // Common Indian DD/MM/YYYY
        "%d-%b-%y", // DD-MMM-YY (e.g., 01-Jan-24)
        "%m/%d/%Y", // US Format fallback
    ];

    for format in formats {
        if let Ok(parsed) = NaiveDate::parse_from_str(date_str, format) {
            return Ok(parsed);
        }
    }

    // Strict fallback triggering structured error propagation
    NaiveDate::parse_from_str(date_str, "%Y-%m-%d")
}

/// Generates a Polars expression to execute optimized string-to-date casting across DataFrames.
pub fn parse_date_expr(column_name: &str, format: &str) -> Expr {
    col(column_name).str().strptime(
        DataType::Date,
        StrptimeOptions {
            format: Some(format.into()),
            strict: false,
            exact: true,
            cache: true,
        },
        col(column_name).fill_null(lit("NULL")),
    )
}
