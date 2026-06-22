"""Unit tests for the security path/size guards (THREAT_MODEL.md controls)."""

from pathlib import Path

import pytest

from opstools.inventory_forecast.domain import DataValidationError, SecurityError
from opstools.inventory_forecast.security import paths


@pytest.mark.parametrize("ext", [".csv", ".xls", ".xlsx", ".xlsm"])
def test_allowlisted_extensions_accepted(ext):
    # A plain local relative path with an allowed extension must pass.
    paths.validate_local_path(Path(f"export{ext}"))


def test_allowlisted_extension_matching_is_case_insensitive():
    paths.validate_local_path(Path("REPORT.XLSX"))


def test_unc_forward_slash_rejected():
    with pytest.raises(SecurityError):
        paths.validate_local_path(Path("//server/share/report.xlsx"))


def test_unc_backslash_rejected():
    # Windows-style UNC. We build the string explicitly so the test is meaningful
    # even on a POSIX test host where Path would not otherwise flag it.
    with pytest.raises(SecurityError):
        paths.validate_local_path(Path("\\\\server\\share\\report.xlsx"))


def test_path_traversal_rejected():
    with pytest.raises(SecurityError):
        paths.validate_local_path(Path("../secret/report.xlsx"))


def test_dotdot_inside_filename_is_not_path_traversal():
    paths.validate_local_path(Path("..report.xlsx"))


def test_drive_relative_path_rejected():
    # "C:report.xlsx" is drive-relative (non-absolute but colon-bearing) on every
    # platform, so it is ambiguous and must be rejected.
    with pytest.raises(SecurityError):
        paths.validate_local_path(Path("C:report.xlsx"))


def test_unsupported_extension_rejected():
    with pytest.raises(SecurityError):
        paths.validate_local_path(Path("report.txt"))


def test_missing_extension_rejected():
    with pytest.raises(SecurityError):
        paths.validate_local_path(Path("report"))


def test_size_limit_accepts_small_file(tmp_path):
    target = tmp_path / "ok.csv"
    target.write_text("a,b,c\n1,2,3\n")
    paths.enforce_file_size_limits(target)  # under the limit -> no raise


def test_size_limit_rejects_oversized_file(tmp_path, monkeypatch):
    # Shrink the ceiling rather than writing 50 MB, then exceed it cheaply.
    monkeypatch.setattr(paths, "MAX_FILE_SIZE_BYTES", 4)
    target = tmp_path / "big.csv"
    target.write_text("0123456789")  # 10 bytes > 4
    with pytest.raises(SecurityError):
        paths.enforce_file_size_limits(target)


def test_size_limit_missing_file_is_data_validation_error(tmp_path):
    with pytest.raises(DataValidationError):
        paths.enforce_file_size_limits(tmp_path / "nope.csv")


def test_size_limit_directory_is_data_validation_error(tmp_path):
    with pytest.raises(DataValidationError):
        paths.enforce_file_size_limits(tmp_path)
