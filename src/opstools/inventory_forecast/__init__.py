"""KEPL Inventory Forecast — offline procurement & inventory analytics.

Package root for the pure-Python engine build. The outer `opstools`
directory is a PEP 420 namespace package and deliberately has no
`__init__.py`; this package (`opstools.inventory_forecast`) is the real
distribution root declared in pyproject.toml.
"""

from importlib.metadata import PackageNotFoundError, version

# Read the version from installed metadata rather than hard-coding it here,
# so there is one source of truth (pyproject.toml). The Metadata sheet
# (WORKBOOK_SCHEMA.md) will reuse this value as application_version.
try:
    __version__ = version("inventory-forecast")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
