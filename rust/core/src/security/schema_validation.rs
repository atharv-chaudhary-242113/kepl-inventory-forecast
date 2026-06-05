// rust/core/src/security/schema_validation.rs
//! Schema downgrade and compatibility enforcement.
//! Protects the engine from legacy parser abuse.

use crate::error::KeplError;

/// Defines the minimum acceptable schema version for workbook processing.
const MINIMUM_SUPPORTED_SCHEMA: &str = "1.0.0";

/// Validates the declared workbook schema version against the minimum supported threshold.
/// Prevents downgrade attacks designed to bypass newly introduced validation rules.
pub fn validate_schema_version(declared_version: &str) -> Result<(), KeplError> {
    let parsed_declared = parse_semantic_version(declared_version)?;
    let parsed_minimum = parse_semantic_version(MINIMUM_SUPPORTED_SCHEMA)?;

    if parsed_declared < parsed_minimum {
        return Err(KeplError::SchemaDowngrade {
            current: format!(">= {}", MINIMUM_SUPPORTED_SCHEMA),
            found: declared_version.to_string(),
        });
    }

    Ok(())
}

/// Simplistic semantic version parser for structural comparison.
/// Assumes standard MAJOR.MINOR.PATCH format.
fn parse_semantic_version(version: &str) -> Result<(u32, u32, u32), KeplError> {
    let parts: Vec<&str> = version.split('.').collect();
    if parts.len() != 3 {
        return Err(KeplError::Validation(
            "Invalid schema version format. Expected MAJOR.MINOR.PATCH".into(),
        ));
    }

    let major = parts[0]
        .parse::<u32>()
        .map_err(|_| KeplError::Validation("Invalid Major version".into()))?;
    let minor = parts[1]
        .parse::<u32>()
        .map_err(|_| KeplError::Validation("Invalid Minor version".into()))?;
    let patch = parts[2]
        .parse::<u32>()
        .map_err(|_| KeplError::Validation("Invalid Patch version".into()))?;

    Ok((major, minor, patch))
}
