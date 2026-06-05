use thiserror::Error;

#[derive(Debug, Error)]
pub enum KeplError {
    #[error("IO error: {0}")]
    IO(String),

    #[error("Validation error: {0}")]
    Validation(String),

    #[error("Ingestion error: {0}")]
    Ingestion(String),

    #[error("Analytics error: {0}")]
    Analytics(String),

    #[error("Forecasting error: {0}")]
    Forecasting(String),

    #[error("Export error: {0}")]
    Export(String),

    #[error("Computation error: {0}")]
    Computation(String),

    #[error("Security error: {0}")]
    Security(String),

    #[error("Integrity error: {0}")]
    Integrity(String),

    #[error("Schema downgrade detected. Current version: {current}, workbook version: {found}")]
    SchemaDowngrade { current: String, found: String },

    #[error("Internal error: {0}")]
    Internal(String),
}

impl From<std::io::Error> for KeplError {
    fn from(value: std::io::Error) -> Self {
        Self::IO(value.to_string())
    }
}

impl From<polars::error::PolarsError> for KeplError {
    fn from(value: polars::error::PolarsError) -> Self {
        Self::Computation(value.to_string())
    }
}
