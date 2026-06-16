"""Domain enumerations shared across all layers.

Pure value types with no I/O and no dependency on other project modules.
StrEnum members compare equal to their string value, which keeps them ergonomic
when read from / written to Polars frames and Excel cells.
"""

from __future__ import annotations

from enum import StrEnum

# ======================================================================================
# Data sources
# ======================================================================================


class SourceKind(StrEnum):
    """The four ERP export types the pipeline ingests.

    Each value corresponds to a required source file
    used during ingestion and validation.
    """

    POV = "pov"
    GRN = "grn"
    PV = "pv"
    CLOSING_STOCK = "closing_stock"


# ======================================================================================
# Inventory Classification
# ======================================================================================


class AbcClass(StrEnum):
    """ABC inventory classification.

    Based on cumulative inventory value contribution.

    Categories:
        A:
            Highest-value inventory items.

        B:
            Medium-value inventory items.

        C:
            Lowest-value inventory items.
    """

    A = "A"
    B = "B"
    C = "C"


class SbcClass(StrEnum):
    """Syntetos-Boylan-Croston demand classification.

    Used to characterize demand behavior and guide
    forecast model selection.

    Categories:
        SMOOTH:
            Frequent demand, low variability.

        ERRATIC:
            Frequent demand, high variability.

        INTERMITTENT:
            Infrequent demand, low variability.

        LUMPY:
            Infrequent demand, high variability.
    """

    SMOOTH = "smooth"
    ERRATIC = "erratic"
    INTERMITTENT = "intermittent"
    LUMPY = "lumpy"


# ======================================================================================
# Forecasting
# ======================================================================================


class ForecastGranularity(StrEnum):
    """Forecast aggregation frequency.

    Determines the temporal resolution used for
    demand aggregation and forecast generation.
    """

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class ForecastModel(StrEnum):
    """Supported forecasting algorithms.

    Represents the forecasting models available
    to the forecasting subsystem.
    """

    NAIVE = "naive"
    SEASONAL_NAIVE = "seasonal_naive"
    AUTO_ETS = "auto_ets"
    THETA = "theta"
    CROSTON_SBA = "croston_sba"
    TSB = "tsb"
    ADIDA = "adida"


class ForecastStatus(StrEnum):
    """Forecast execution outcome.

    Tracks the lifecycle state of forecast generation.
    """

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    FALLBACK = "fallback"


# ======================================================================================
# Supplier Analytics
# ======================================================================================


class FulfillmentStatus(StrEnum):
    """Purchase-order fulfillment state.

    Represents delivery completion status for
    supplier orders.
    """

    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETE = "complete"


class SupplierDependencyLevel(StrEnum):
    """Supplier concentration classification.

    Measures how dependent an item is on a small
    number of suppliers.
    """

    DIVERSIFIED = "diversified"
    MODERATE = "moderate"
    CONCENTRATED = "concentrated"
    SINGLE_SOURCE = "single_source"


# ======================================================================================
# Risk & Health
# ======================================================================================


class RiskLevel(StrEnum):
    """Generic business risk classification.

    Used to communicate risk severity across
    multiple analytics modules.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InventoryStatus(StrEnum):
    """Inventory health classification.

    Represents the operational condition of
    inventory items.
    """

    HEALTHY = "healthy"
    LOW_STOCK = "low_stock"
    OVERSTOCKED = "overstocked"
    DEAD_STOCK = "dead_stock"
    OBSOLETE = "obsolete"


# ======================================================================================
# Trend Analysis
# ======================================================================================


class TrendDirection(StrEnum):
    """Direction of change over time.

    Used when evaluating trends in demand,
    pricing, inventory, or supplier performance.
    """

    UP = "up"
    DOWN = "down"
    FLAT = "flat"


# ======================================================================================
# Worksheet Metadata
# ======================================================================================


class WorksheetName(StrEnum):
    """Name of the worksheet."""

    METADATA = "Metadata"
    DEMAND_HISTORY = "Demand_History"
    FORECASTS = "Forecasts"
    SUPPLIER_ANALYSIS = "Supplier_Analysis"
    SUPPLIER_PARTNERSHIPS = "Supplier_Partnerships"
    LEAD_TIME_ANALYSIS = "Lead_Time_Analysis"
    PENDING_DELIVERIES = "Pending_Deliveries"
    FINANCIAL_SUMMARY = "Financial_Summary"
    ABC_CLASSIFICATION = "ABC_Classification"
    SBC_CLASSIFICATION = "SBC_Classification"
    INVENTORY_VALUATION = "Inventory_Valuation"
    DASHBOARD_CACHE = "Dashboard_Cache"
