"""Domain error hierarchy.

Every recoverable failure crossing a layer boundary is an instance of
`InventoryForecastError` or one of its subclasses (API_CONTRACT.md). Raisers
attach an actionable message naming the offending file, column, or value
(CODING_STANDARDS.md). Programmer errors (broken invariants) are *not* modelled
here — they fail fast as ordinary exceptions.
"""


class InventoryForecastError(Exception):
    """Base class for all domain errors raised by the application."""


# ======================================================================================
# Data & Validation
# ======================================================================================


class DataValidationError(InventoryForecastError):
    """Raised when business data fails validation."""


class MissingColumnError(DataValidationError):
    """Raised when a required column is missing."""


class InvalidSchemaError(DataValidationError):
    """Raised when an input dataset violates schema requirements."""


class DuplicateRecordError(DataValidationError):
    """Raised when duplicate records are detected where uniqueness is required."""


# ======================================================================================
# Forecasting
# ======================================================================================


class ForecastingError(InventoryForecastError):
    """Base forecasting exception."""


class InsufficientHistoryError(ForecastingError):
    """Raised when a series lacks enough observations."""


class ClassificationError(ForecastingError):
    """Raised when demand classification cannot be determined."""


class ModelSelectionError(ForecastingError):
    """Raised when no forecast model can be selected."""


class BacktestingError(ForecastingError):
    """Raised when forecast evaluation fails."""


# ======================================================================================
# Supplier Analytics
# ======================================================================================


class SupplierAnalyticsError(InventoryForecastError):
    """Base supplier analytics exception."""


class LeadTimeError(SupplierAnalyticsError):
    """Raised when lead-time calculations fail."""


class FillRateError(SupplierAnalyticsError):
    """Raised when fill-rate calculations fail."""


# ======================================================================================
# Inventory Analytics
# ======================================================================================


class InventoryAnalyticsError(InventoryForecastError):
    """Base inventory analytics exception."""


class ReorderCalculationError(InventoryAnalyticsError):
    """Raised when reorder recommendations cannot be produced."""


class InventoryHealthError(InventoryAnalyticsError):
    """Raised when inventory health cannot be evaluated."""


class SourcingRiskError(InventoryAnalyticsError):
    """Raised when sourcing-risk analysis fails."""


# ======================================================================================
# Security
# ======================================================================================


class SecurityError(InventoryForecastError):
    """An untrusted path or file violates a THREAT_MODEL.md control.

    Raised by the ``security`` layer for UNC/SMB paths, traversal sequences,
    ambiguous drive-relative paths, disallowed extensions, and oversized files.
    Distinct from DataValidationError so callers can treat a *security*
    rejection (a possible attack) differently from a merely malformed *value*.
    """


# ======================================================================================
# Workbook Generation
# ======================================================================================


class WorkbookError(InventoryForecastError):
    """Base workbook exception."""


class WorksheetGenerationError(WorkbookError):
    """Raised when a worksheet cannot be generated."""


class DashboardGenerationError(WorkbookError):
    """Raised when a dashboard cannot be generated."""


class WorksheetMetaDataError(WorkbookError):
    """Raised when a worksheet's metadata cannot be read."""
