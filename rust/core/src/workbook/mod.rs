// rust/core-engine/src/workbook/mod.rs
pub mod export_model;
pub mod metadata;
pub mod schema;

use crate::error::KeplError;
use crate::workbook::export_model::WorkbookExportPayload;
use polars::prelude::*;
use polars_excel_writer::PolarsExcelWriter;
use std::path::Path;

pub fn sanitize_dataframe_for_export(df: DataFrame) -> Result<DataFrame, KeplError> {
    let mut exprs = Vec::new();

    // Iterate safely over the schema instead of extracting raw column vectors
    for field in df.schema().iter_fields() {
        if field.dtype == DataType::String {
            exprs.push(
                col(field.name().as_str())
                    .str()
                    .replace_all(lit(r"^[=+\-@]"), lit("'"), false)
                    .alias(field.name().as_str()),
            );
        } else {
            exprs.push(col(field.name().as_str()));
        }
    }

    df.lazy()
        .select(&exprs)
        .collect()
        .map_err(|e| KeplError::Export(format!("Sanitization query failed: {}", e)))
}

pub fn export_workbook(
    payload: WorkbookExportPayload,
    output_path: &Path,
) -> Result<(), KeplError> {
    let mut excel_writer = PolarsExcelWriter::new();

    let sanitized_metadata = sanitize_dataframe_for_export(payload.metadata)?;
    excel_writer
        .write_dataframe(&sanitized_metadata)
        .map_err(|e| KeplError::IO(e.to_string()))?;

    let sanitized_demand = sanitize_dataframe_for_export(payload.demand_history)?;
    excel_writer
        .write_dataframe(&sanitized_demand)
        .map_err(|e| KeplError::IO(e.to_string()))?;

    let sanitized_forecasts = sanitize_dataframe_for_export(payload.forecasts)?;
    excel_writer
        .write_dataframe(&sanitized_forecasts)
        .map_err(|e| KeplError::IO(e.to_string()))?;

    excel_writer
        .save(output_path)
        .map_err(|e| KeplError::IO(e.to_string()))?;

    Ok(())
}
