// rust/core/src/security/path_validation.rs
//! File system security controls.
//! Prevents Path Traversal, UNC Path Injection, and ZIP Bombs.

use crate::error::KeplError;
use std::path::{Component, Path};

const MAX_WORKBOOK_SIZE_BYTES: u64 = 50 * 1024 * 1024; // 50 MB limit to prevent ZIP/Memory Bombs

/// Validates target file paths against directory traversal and network share execution vectors.
pub fn validate_file_path(path: &Path) -> Result<(), KeplError> {
    let path_str = path.to_str().unwrap_or("");

    // 1. Prevent UNC Path / SMB Relay Attacks
    if path_str.starts_with(r"\\") || path_str.starts_with("//") {
        return Err(KeplError::Security(
            "UNC and network share paths are strictly prohibited.".into(),
        ));
    }

    // 2. Prevent Path Traversal
    for component in path.components() {
        if let Component::ParentDir = component {
            return Err(KeplError::Security(
                "Path traversal sequences (..) are prohibited.".into(),
            ));
        }
    }

    // 3. Prevent ambiguous drive-relative paths
    if !path.is_absolute() && path_str.contains(':') {
        return Err(KeplError::Security(
            "Ambiguous drive-relative paths are prohibited.".into(),
        ));
    }

    // 4. Restrict allowed workbook formats
    const ALLOWED_EXTENSIONS: &[&str] = &["xlsx", "xlsm", "xls", "csv"];

    let extension = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_ascii_lowercase())
        .ok_or_else(|| {
            KeplError::Security("Workbook file must contain a valid extension.".into())
        })?;

    if !ALLOWED_EXTENSIONS.contains(&extension.as_str()) {
        return Err(KeplError::Security(format!(
            "Unsupported workbook extension: {}",
            extension
        )));
    }

    Ok(())
}

/// Enforces maximum file size constraints before loading to mitigate ZIP bombs and memory exhaustion.
pub fn enforce_file_size_limits(path: &Path) -> Result<(), KeplError> {
    let metadata = std::fs::metadata(path).map_err(|e| KeplError::IO(e.to_string()))?;

    if metadata.len() > MAX_WORKBOOK_SIZE_BYTES {
        return Err(KeplError::Security(format!(
            "File size {} exceeds the maximum permissible limit of {} bytes.",
            metadata.len(),
            MAX_WORKBOOK_SIZE_BYTES
        )));
    }

    Ok(())
}
