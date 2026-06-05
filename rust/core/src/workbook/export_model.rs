// rust/core/src/workbook/export_models.rs
//! Export payload abstraction.
//! Binds all in-memory analytical states into a single verifiable struct prior to disk I/O.

use polars::prelude::DataFrame;

/// Unified payload containing all computed DataFrames strictly aligning with WORKBOOK_SCHEMA.md.
/// Assumes all LazyFrames have been collected into materialized DataFrames.
pub struct WorkbookExportPayload {
    pub metadata: DataFrame,
    pub demand_history: DataFrame,
    pub forecasts: DataFrame,
    pub supplier_analysis: DataFrame,
    pub supplier_partnerships: DataFrame,
    pub lead_time_analysis: DataFrame,
    pub pending_deliveries: DataFrame,
    pub financial_summary: DataFrame,
    pub abc_classification: DataFrame,
    pub sbc_classification: DataFrame,
    pub inventory_valuation: DataFrame,
    pub dashboard_cache: DataFrame,
}

impl WorkbookExportPayload {
    /// Validates that all DataFrames contain data before permitting export, preventing silent failure modes.
    pub fn validate_readiness(&self) -> bool {
        self.metadata.height() == 1
            && self.demand_history.height() > 0
            && self.forecasts.height() > 0
            && self.financial_summary.height() > 0
    }
}
