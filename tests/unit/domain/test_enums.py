"""Unit tests for domain enums."""

from opstools.inventory_forecast.domain.enums import (
    AbcClass,
    ForecastGranularity,
    ForecastModel,
    ForecastStatus,
    FulfillmentStatus,
    InventoryStatus,
    RiskLevel,
    SbcClass,
    SourceKind,
    SupplierDependencyLevel,
    TrendDirection,
)


def test_enum_string_values():
    assert SourceKind.POV == "pov"
    assert SourceKind.GRN == "grn"
    assert SourceKind.PV == "pv"
    assert SourceKind.CLOSING_STOCK == "closing_stock"
    assert AbcClass.A == "A"
    assert AbcClass.B == "B"
    assert AbcClass.C == "C"
    assert SbcClass.SMOOTH == "smooth"
    assert SbcClass.ERRATIC == "erratic"
    assert SbcClass.INTERMITTENT == "intermittent"
    assert SbcClass.LUMPY == "lumpy"
    assert ForecastGranularity.MONTHLY == "monthly"
    assert ForecastGranularity.QUARTERLY == "quarterly"
    assert ForecastModel.NAIVE == "naive"
    assert ForecastModel.SEASONAL_NAIVE == "seasonal_naive"
    assert ForecastModel.AUTO_ETS == "auto_ets"
    assert ForecastModel.THETA == "theta"
    assert ForecastModel.CROSTON_SBA == "croston_sba"
    assert ForecastModel.TSB == "tsb"
    assert ForecastModel.ADIDA == "adida"
    assert ForecastStatus.PENDING == "pending"
    assert ForecastStatus.SUCCESS == "success"
    assert ForecastStatus.FAILED == "failed"
    assert ForecastStatus.FALLBACK == "fallback"
    assert FulfillmentStatus.PENDING == "pending"
    assert FulfillmentStatus.PARTIAL == "partial"
    assert FulfillmentStatus.COMPLETE == "complete"
    assert SupplierDependencyLevel.DIVERSIFIED == "diversified"
    assert SupplierDependencyLevel.MODERATE == "moderate"
    assert SupplierDependencyLevel.CONCENTRATED == "concentrated"
    assert SupplierDependencyLevel.SINGLE_SOURCE == "single_source"
    assert RiskLevel.LOW == "low"
    assert RiskLevel.MEDIUM == "medium"
    assert RiskLevel.HIGH == "high"
    assert RiskLevel.CRITICAL == "critical"
    assert InventoryStatus.HEALTHY == "healthy"
    assert InventoryStatus.LOW_STOCK == "low_stock"
    assert InventoryStatus.OVERSTOCKED == "overstocked"
    assert InventoryStatus.DEAD_STOCK == "dead_stock"
    assert InventoryStatus.OBSOLETE == "obsolete"
    assert TrendDirection.UP == "up"
    assert TrendDirection.DOWN == "down"
    assert TrendDirection.FLAT == "flat"
