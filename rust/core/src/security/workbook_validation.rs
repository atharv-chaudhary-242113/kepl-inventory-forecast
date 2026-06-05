// rust/core/src/security/workbook_validation.rs
//! Workbook authenticity and cryptographic integrity validation.
//! Mitigates silent data corruption and malicious workbook tampering.

use crate::error::KeplError;
use std::path::Path;

/// Verifies the structural and cryptographic integrity of a loaded workbook.
/// Fulfills the "Detect modifications" mandate from THREAT_MODEL.md.
pub fn verify_workbook_integrity(
    _workbook_path: &Path,
    declared_hash: &str,
    computed_hash: &str,
) -> Result<(), KeplError> {
    // 1. Validate hash presence
    if declared_hash.trim().is_empty() || declared_hash == "PENDING" {
        return Err(KeplError::Integrity(
            "Workbook metadata lacks a finalized integrity hash.".into(),
        ));
    }

    // 2. Constant-time string comparison to prevent timing attacks during hash verification.
    if !constant_time_eq(declared_hash.as_bytes(), computed_hash.as_bytes()) {
        return Err(KeplError::Integrity(
            "Workbook cryptographic hash mismatch. Tampering or corruption detected.".into(),
        ));
    }

    Ok(())
}

/// Executes a constant-time equality check on two byte slices.
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }

    let mut result = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        result |= x ^ y;
    }

    result == 0
}
