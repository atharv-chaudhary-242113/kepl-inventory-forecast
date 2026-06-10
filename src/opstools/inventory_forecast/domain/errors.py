"""Domain error hierarchy.

Every recoverable failure crossing a layer boundary is an instance of
`InventoryForecastError` or one of its subclasses (API_CONTRACT.md). Raisers
attach an actionable message naming the offending file, column, or value
(CODING_STANDARDS.md). Programmer errors (broken invariants) are *not* modelled
here — they fail fast as ordinary exceptions.

Note the base is `InventoryForecastError`, not the older `KeplError`: the
package is `opstools.inventory_forecast`, so the `Kepl` prefix is dropped to
keep the name aligned with the namespace.
"""


class InventoryForecastError(Exception):
    """Base class for all domain errors raised by the application."""


class SchemaError(InventoryForecastError):
    """A required column is missing, or no header row could be located."""


class ValidationError(InventoryForecastError):
    """A value violates a domain constraint (negative qty/price/amount, etc.)."""


class WorkbookVersionError(InventoryForecastError):
    """A workbook's schema version is unsupported by this application version."""


class ForecastError(InventoryForecastError):
    """Forecasting failed for a series and could not produce a result."""
