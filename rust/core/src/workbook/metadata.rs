// rust/core/src/workbook/metadata.rs
//! Workbook metadata generation.
//! Enforces authenticity, auditability, and hashing controls dictated by THREAT_MODEL.md.

use super::schema::SCHEMA_VERSION;
use crate::error::KeplError;
use chrono::Utc;
use polars::prelude::*;

/// Defines the runtime execution statistics required for workbook auditability.
pub struct GenerationContext {
    pub application_version: String,
    pub source_hash: String,
    pub forecast_horizon: u32,
    pub total_suppliers: u32,
    pub total_items: u32,
    pub total_records: u32,
    pub processing_time_seconds: f64,
}

/// Constructs the single-row Metadata DataFrame enforcing schema versioning and cryptographic origin tracing.
pub fn build_metadata_sheet(context: GenerationContext) -> Result<DataFrame, KeplError> {
    let generated_at = Utc::now().to_rfc3339();

    df!(
        "schema_version" => &[SCHEMA_VERSION],
        "application_version" => &[context.application_version.as_str()],
        "generated_at" => &[generated_at.as_str()],
        "source_hash" => &[context.source_hash.as_str()],
        "output_hash" => &["PENDING"],
        "forecast_horizon" => &[context.forecast_horizon],
        "total_suppliers" => &[context.total_suppliers],
        "total_items" => &[context.total_items],
        "total_records" => &[context.total_records],
        "processing_time_seconds" => &[context.processing_time_seconds],
    )
    .map_err(|e| KeplError::Export(format!("Failed to build metadata dataframe: {}", e)))
}
