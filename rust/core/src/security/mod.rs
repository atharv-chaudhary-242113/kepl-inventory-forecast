// rust/core/src/security/mod.rs
//! Security boundary enforcement.
//! Implements the mitigations specified in THREAT_MODEL.md, isolating the engine
//! from malicious inputs, path traversal, UNC injections, and tampering.

pub mod path_validation;
pub mod schema_validation;
pub mod workbook_validation;
