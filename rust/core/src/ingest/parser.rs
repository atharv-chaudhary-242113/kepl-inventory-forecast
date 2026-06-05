// rust/core/src/ingest/parser.rs
use super::validation::{canonicalize_report, enforce_domain_constraints};
use crate::error::KeplError;
use crate::security::path_validation::{enforce_file_size_limits, validate_file_path};

use calamine::{Reader, open_workbook_auto};
use polars::prelude::*;
use std::path::Path;

pub struct IngestionPipeline;

pub fn detect_header_row(grid: &[Vec<String>], expected_columns: &[&str]) -> Option<usize> {
    let normalize = |s: &str| s.to_lowercase().replace(' ', "");
    let expected_norm: Vec<String> = expected_columns.iter().map(|c| normalize(c)).collect();

    grid.iter()
        .enumerate()
        .map(|(i, row)| {
            let hits = row
                .iter()
                .filter(|cell| expected_norm.contains(&normalize(cell)))
                .count();
            (i, hits)
        })
        .max_by_key(|&(_, hits)| hits)
        .filter(|&(_, hits)| hits > 0)
        .map(|(i, _)| i)
}

impl IngestionPipeline {
    /// Main entry point. Loads a file, applies fuzzy column mapping,
    /// and runs canonicalization checks.
    pub fn process_file(
        file_path: &Path,
        expected_columns: &[&str],
    ) -> Result<LazyFrame, KeplError> {
        validate_file_path(file_path)?;
        enforce_file_size_limits(file_path)?;

        let path_str = file_path.to_str().unwrap_or("");

        let mut df = if path_str.ends_with(".xlsx") || path_str.ends_with(".xls") {
            Self::load_excel(file_path, expected_columns)?
        } else if path_str.ends_with(".csv") {
            CsvReadOptions::default()
                .with_has_header(true)
                .try_into_reader_with_file_path(Some(file_path.into()))
                .map_err(|e| KeplError::IO(e.to_string()))?
                .finish()
                .map_err(|e| KeplError::IO(e.to_string()))?
        } else {
            return Err(KeplError::Validation("Unsupported file format".into()));
        };

        Self::rename_columns_fuzzy(&mut df, expected_columns)?;

        // Convert to LazyFrame and apply domain validation pipeline
        let lf = df.lazy().with_columns(vec![
            col("Qty.").cast(DataType::Float64),
            col("Price").cast(DataType::Float64),
            col("Amount").cast(DataType::Float64),
        ]);
        let canonicalized = canonicalize_report(lf);
        Ok(enforce_domain_constraints(canonicalized))
    }

    /// Loads Excel using calamine and converts it to a Polars DataFrame
    fn load_excel(file_path: &Path, expected_columns: &[&str]) -> Result<DataFrame, KeplError> {
        let mut workbook = open_workbook_auto(file_path)
            .map_err(|e| KeplError::IO(format!("Failed to open Excel: {}", e)))?;

        let sheet_names = workbook.sheet_names().to_owned();
        let first_sheet = sheet_names
            .first()
            .ok_or_else(|| KeplError::Validation("Excel file is empty".into()))?;

        let range = workbook
            .worksheet_range(first_sheet)
            .ok_or_else(|| KeplError::IO("Worksheet not found".into()))?
            .map_err(|e| KeplError::IO(e.to_string()))?;

        //  1. Flatten every cell to a trimmed String.
        //     WHY: ERP sheets mix numbers/dates/text in one grid. We normalize to text and
        //     let Polars cast the domain columns later (Step 3). Excel stores dates as float
        //     serials, so we use calamine's `dates` feature to recover ISO-8601 instead of
        //     leaking serials like "45000" downstream (THREAT_MODEL.md data rule).
        let grid: Vec<Vec<String>> = range
            .rows()
            .map(|row| {
                row.iter()
                    .map(|cell| {
                        if let Some(dt) = cell.as_datetime() {
                            dt.format("%Y-%m-%d").to_string()
                        } else {
                            cell.to_string().trim().to_string()
                        }
                    })
                    .collect()
            })
            .collect();

        if grid.is_empty() {
            return Err(KeplError::Validation("Excel sheet contains no rows".into()));
        }

        //  2. Dynamic header detection (INPUT_SCHEMA.md).
        //     WHY: the header is NOT guaranteed to be row 0 - reports prepend company name,
        //     title, date-range and blank rows. Pick the row matching the most expected
        //     columns (case/whitespace-insensitive).

        let header_idx = detect_header_row(&grid, expected_columns).ok_or_else(|| {
            KeplError::Validation("Could not locate a valid header row in Excel sheet".into())
        })?;

        //  3. Build one String column per header cell, from the rows BELOW the header.
        let header: Vec<String> = grid[header_idx].clone();

        let height = grid.len().saturating_sub(header_idx + 1);
        let mut columns: Vec<Column> = Vec::with_capacity(header.len());

        for (c, name) in header.iter().enumerate() {
            let values: Vec<String> = grid[header_idx + 1..]
                .iter()
                .map(|row| row.get(c).cloned().unwrap_or_default())
                .collect();
            columns.push(Column::new(name.as_str().into(), values));
        }
        DataFrame::new(height, columns).map_err(|e| KeplError::Computation(e.to_string()))
    }

    /// Maps ERP headers to canonical schemas using whitespace/case-insensitive matching
    pub fn rename_columns_fuzzy(
        df: &mut DataFrame,
        expected_columns: &[&str],
    ) -> Result<(), KeplError> {
        let existing_cols = df.get_column_names();
        let mut rename_map = std::collections::HashMap::new();

        for &expected in expected_columns {
            let canonical_lower = expected.to_lowercase().replace(" ", "");

            let matched_col = existing_cols
                .iter()
                .find(|&&existing| existing.to_lowercase().replace(" ", "") == canonical_lower);

            match matched_col {
                Some(&actual_name) => {
                    rename_map.insert(actual_name.to_string(), expected.to_string());
                }
                None => {
                    return Err(KeplError::Validation(format!(
                        "Missing required column: '{}'",
                        expected
                    )));
                }
            }
        }

        // Apply renames
        for (old_name, new_name) in rename_map {
            df.rename(&old_name, new_name.into())
                .map_err(|e| KeplError::Computation(e.to_string()))?;
        }

        Ok(())
    }
}
