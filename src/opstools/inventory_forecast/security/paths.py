"""Filesystem security controls for untrusted, user-supplied paths.

This is the very front of the ingestion trust boundary (ARCHITECTURE.md sec 4.8,
Constitution Rule 7): every external path is validated here *before* the file is
opened. The controls mirror THREAT_MODEL.md "UNC Path Injection", "Path
Traversal", "Arbitrary File Access", and "ZIP Bombs". We fail closed and prefer
an allowlist over a blocklist.
"""

from pathlib import Path

from opstools.inventory_forecast.domain.errors import DataValidationError, SecurityError

# 50 MB ceiling on any single source file. A workbook far larger than a real ERP
# export is the cheapest signal of a ZIP/decompression bomb or a memory-exhaustion
# attempt (THREAT_MODEL.md "ZIP Bombs" / "Memory Exhaustion"), so we reject it
# before Polars/calamine ever allocates against it.
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024

# Allowlist, not blocklist (Security Principles): only these source formats may be
# read. `.csv`, `.xls`, `.xlsx` are the accepted inputs per INPUT_SCHEMA.md;
# `.xlsm` is allowed because a macro-enabled workbook is still only ever *read*
# as data (we never execute its macros).
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".xls", ".xlsx", ".xlsm"})


# noinspection GrazieInspection
def validate_local_path(path: Path) -> None:
    """Reject any path that is not a safe, local, allowlisted source file.

    Raises:
        SecurityError: the path is a UNC/SMB share, contains a traversal
            sequence, is an ambiguous drive-relative path, or carries an
            extension outside ``ALLOWED_EXTENSIONS``.
    """
    # `as_posix()` collapses both separators so the `//` UNC test is OS-agnostic;
    # a Windows UNC path (\\server\share) also surfaces as a leading `//` here.
    text = path.as_posix()

    # 1. UNC / SMB shares — these can leak NetNTLM hashes or enable SMB relay if
    #    Excel/Polars is pointed at them (THREAT_MODEL.md "UNC Path Injection").
    if text.startswith("//") or str(path).startswith("\\\\"):
        msg = f"UNC and network-share paths are not permitted: {path}"
        raise SecurityError(msg)

    # 2. Path traversal — a `..` component lets a crafted path escape the
    #    application-controlled directory (THREAT_MODEL.md "Path Traversal").
    #    We test components rather than substring-match so a legitimate file
    #    named "..report.xlsx" is not falsely rejected.
    if any(part == ".." for part in path.parts):
        msg = f"Path traversal sequences ('..') are not permitted: {path}"
        raise SecurityError(msg)

    # 3. Ambiguous drive-relative paths on Windows ("C:report.xlsx" means "the
    #    current dir on drive C", which is non-deterministic). A real absolute
    #    path keeps its colon only inside the drive component, so flag a colon
    #    that appears in a path we could not resolve as absolute.
    if not path.is_absolute() and ":" in text:
        msg = f"Ambiguous drive-relative paths are not permitted: {path}"
        raise SecurityError(msg)

    # 4. Extension allowlist. `suffix` is the final extension only; we lower-case
    #    it so "REPORT.XLSX" is accepted.
    extension = path.suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        msg = (
            f"Unsupported source extension '{extension or '(none)'}' "
            f"for {path}; allowed: {allowed}"
        )
        raise SecurityError(msg)


def enforce_file_size_limits(path: Path) -> None:
    """Confirm the file exists and is within ``MAX_FILE_SIZE_BYTES``.

    Raises:
        DataValidationError: the path does not point at an existing regular file.
        SecurityError: the file exceeds the maximum permitted size.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        # Missing/unreadable file is bad *input*, not an attack, so it is a
        # DataValidationError; we surface the OS reason for an actionable message.
        msg = f"Source file is not readable: {path} ({exc.strerror or exc})"
        raise DataValidationError(msg) from exc

    if not path.is_file():
        msg = f"Source path is not a regular file: {path}"
        raise DataValidationError(msg)

    if size > MAX_FILE_SIZE_BYTES:
        msg = (
            f"File size {size} bytes exceeds the maximum of "
            f"{MAX_FILE_SIZE_BYTES} bytes: {path}"
        )
        raise SecurityError(msg)
