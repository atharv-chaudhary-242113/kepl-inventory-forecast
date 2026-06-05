// rust/core/src/workbook/schema.rs
//! Canonical workbook schema definitions.
//! Strictly mirrors the sheet names established in WORKBOOK_SCHEMA.md.

pub const SHEET_METADATA: &str = "Metadata";
pub const SHEET_DEMAND_HISTORY: &str = "Demand_History";
pub const SHEET_FORECASTS: &str = "Forecasts";
pub const SHEET_SUPPLIER_ANALYSIS: &str = "Supplier_Analysis";
pub const SHEET_SUPPLIER_PARTNERSHIPS: &str = "Supplier_Partnerships";
pub const SHEET_LEAD_TIME_ANALYSIS: &str = "Lead_Time_Analysis";
pub const SHEET_PENDING_DELIVERIES: &str = "Pending_Deliveries";
pub const SHEET_FINANCIAL_SUMMARY: &str = "Financial_Summary";
pub const SHEET_ABC_CLASSIFICATION: &str = "ABC_Classification";
pub const SHEET_SBC_CLASSIFICATION: &str = "SBC_Classification";
pub const SHEET_INVENTORY_VALUATION: &str = "Inventory_Valuation";
pub const SHEET_DASHBOARD_CACHE: &str = "Dashboard_Cache";

pub const SCHEMA_VERSION: &str = "1.0.0";
