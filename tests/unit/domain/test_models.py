"""Unit tests for domain models."""

from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError  # Pydantic's, not our domain ValidationError

from opstools.inventory_forecast.domain import (
    DemandCharacteristics,
    DemandObservation,
    ForecastMetrics,
    ForecastModel,
    ForecastRequest,
    ForecastResult,
    ForecastStatus,
    InventoryHealthReport,
    InventoryStatus,
    ReplenishmentRecommendation,
    RiskLevel,
    SbcClass,
    SourceKind,
    SourceSet,
    SupplierDependencyLevel,
    SupplierRisk,
    WorkbookMeta,
)


def test_source_set_iter_with_kind_pairs_paths_to_kinds():
    sources = SourceSet(
        pov=(Path("pov_2024.xlsx"),),
        grn=(Path("grn_2024.xlsx"),),
        pv=(Path("pv_2024.xlsx"),),
        closing_stock=(Path("stock_2024.xlsx"),),
    )
    pairs = list(sources.iter_with_kind())
    assert pairs == [
        (Path("pov_2024.xlsx"), SourceKind.POV),
        (Path("grn_2024.xlsx"), SourceKind.GRN),
        (Path("pv_2024.xlsx"), SourceKind.PV),
        (Path("stock_2024.xlsx"), SourceKind.CLOSING_STOCK),
    ]
    assert sources.all_paths == tuple(p for p, _ in pairs)


def test_source_set_is_frozen():
    sources = SourceSet()
    with pytest.raises(ValidationError):
        sources.pov = (Path("x.xlsx"),)  # frozen model => assignment rejected


def test_empty_source_set_yields_no_paths():
    sources = SourceSet()

    assert list(sources.iter_with_kind()) == []
    assert sources.all_paths == ()


def test_workbook_meta_holds_documented_fields():
    meta = WorkbookMeta(
        schema_version="1.0.0",
        application_version="0.1.0",
        generated_at=datetime.now(),
        forecast_horizon=12,
        total_suppliers=3,
        total_items=42,
        total_records=1000,
        processing_time_seconds=4.2,
    )
    assert meta.forecast_horizon == 12
    assert meta.total_items == 42


def test_workbook_meta_rejects_nonpositive_horizon():
    with pytest.raises(ValidationError):
        WorkbookMeta(
            schema_version="1.0.0",
            application_version="0.1.0",
            generated_at=datetime(2026, 1, 1),
            forecast_horizon=0,
            total_suppliers=3,
            total_items=42,
            total_records=1000,
            processing_time_seconds=4.2,
        )


def test_workbook_meta_rejects_negative_counts():
    with pytest.raises(ValidationError):
        WorkbookMeta(
            schema_version="1.0.0",
            application_version="0.1.0",
            generated_at=datetime(2026, 1, 1),
            forecast_horizon=12,
            total_suppliers=-1,
            total_items=42,
            total_records=1000,
            processing_time_seconds=4.2,
        )


def test_demand_characteristics_rejects_nonpositive_history_length():
    with pytest.raises(ValueError, match="history_length"):
        DemandCharacteristics(
            item_id="A",
            history_length=0,
            mean_demand=1,
            std_demand=1,
            adi=1,
            cv2=1,
            zero_demand_ratio=0.2,
            demand_class=SbcClass.SMOOTH,
        )


def test_demand_characteristics_rejects_negative_adi():
    with pytest.raises(ValueError, match="adi"):
        DemandCharacteristics(
            item_id="A",
            history_length=1,
            mean_demand=1,
            std_demand=1,
            adi=-1,
            cv2=1,
            zero_demand_ratio=0.2,
            demand_class=SbcClass.SMOOTH,
        )


def test_demand_characteristics_rejects_negative_cv2():
    with pytest.raises(ValueError, match="cv2"):
        DemandCharacteristics(
            item_id="A",
            history_length=1,
            mean_demand=1,
            std_demand=1,
            adi=1,
            cv2=-1,
            zero_demand_ratio=0.2,
            demand_class=SbcClass.SMOOTH,
        )


def test_demand_characteristics_rejects_invalid_zero_ratio():
    with pytest.raises(ValueError, match="zero_demand_ratio"):
        DemandCharacteristics(
            item_id="A",
            history_length=1,
            mean_demand=1,
            std_demand=1,
            adi=1,
            cv2=1,
            zero_demand_ratio=1.5,
            demand_class=SbcClass.SMOOTH,
        )


def test_demand_observation_rejects_negative_quantity():
    with pytest.raises(ValueError, match="quantity"):
        DemandObservation(
            item_id="A",
            observation_date=date(2026, 1, 1),
            quantity=-1,
        )


def test_forecast_request_rejects_nonpositive_horizon():
    with pytest.raises(ValueError, match="horizon"):
        ForecastRequest(
            item_id="A",
            horizon=0,
            seasonality=12,
            service_level=0.95,
        )


def test_forecast_request_rejects_nonpositive_seasonality():
    with pytest.raises(ValueError, match="seasonality"):
        ForecastRequest(
            item_id="A",
            horizon=12,
            seasonality=0,
            service_level=0.95,
        )


def test_forecast_request_rejects_invalid_service_level():
    with pytest.raises(ValueError, match="service_level"):
        ForecastRequest(
            item_id="A",
            horizon=12,
            seasonality=12,
            service_level=1.5,
        )


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("MASE", {"mase": -1}),
        ("RMSSE", {"rmsse": -1}),
        ("MAE", {"mae": -1}),
        ("RMSE", {"rmse": -1}),
        ("Observation count", {"observation_count": 0}),
    ],
)
def test_forecast_metrics_reject_invalid_values(field, kwargs):
    payload = {
        "mase": 1,
        "rmsse": 1,
        "bias": 0,
        "mae": 1,
        "rmse": 1,
        "observation_count": 10,
    }

    payload.update(kwargs)

    with pytest.raises(ValueError, match=field):
        ForecastMetrics(**payload)


def _metrics():
    return ForecastMetrics(
        mase=1,
        rmsse=1,
        bias=0,
        mae=1,
        rmse=1,
        observation_count=10,
    )


def test_forecast_result_rejects_empty_forecasts():
    with pytest.raises(ValueError, match="forecast_values"):
        ForecastResult(
            item_id="A",
            demand_class=SbcClass.SMOOTH,
            selected_model=ForecastModel.NAIVE,
            forecast_values=(),
            lower_bound=(),
            upper_bound=(),
            metrics=_metrics(),
            status=ForecastStatus.SUCCESS,
            generated_at=datetime.now(),
        )


def test_forecast_result_rejects_lower_bound_length_mismatch():
    with pytest.raises(ValueError, match="lower_bound"):
        ForecastResult(
            item_id="A",
            demand_class=SbcClass.SMOOTH,
            selected_model=ForecastModel.NAIVE,
            forecast_values=(1, 2),
            lower_bound=(1,),
            upper_bound=(1, 2),
            metrics=_metrics(),
            status=ForecastStatus.SUCCESS,
            generated_at=datetime.now(),
        )


def test_forecast_result_rejects_upper_bound_length_mismatch():
    with pytest.raises(ValueError, match="upper_bound"):
        ForecastResult(
            item_id="A",
            demand_class=SbcClass.SMOOTH,
            selected_model=ForecastModel.NAIVE,
            forecast_values=(1, 2),
            lower_bound=(1, 2),
            upper_bound=(1,),
            metrics=_metrics(),
            status=ForecastStatus.SUCCESS,
            generated_at=datetime.now(),
        )


def test_supplier_risk_requires_positive_supplier_count():
    with pytest.raises(ValueError, match="supplier_count"):
        SupplierRisk(
            supplier_id="S1",
            item_id="A",
            dependency_level=SupplierDependencyLevel.SINGLE_SOURCE,
            risk_level=RiskLevel.HIGH,
            supplier_count=0,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"baseline_stock_level": -1},
        {"estimate_stock_level": -1},
        {"replenishment_quantity": -1},
    ],
)
def test_replenishment_rejects_negative_values(kwargs):
    payload = {
        "item_id": "A",
        "baseline_stock_level": 1,
        "estimate_stock_level": 1,
        "replenishment_quantity": 1,
    }

    payload.update(kwargs)

    with pytest.raises(ValueError):
        ReplenishmentRecommendation(**payload)


def test_inventory_health_rejects_negative_months_of_cover():
    with pytest.raises(ValueError, match="months_of_cover"):
        InventoryHealthReport(
            item_id="A",
            status=InventoryStatus.HEALTHY,
            months_of_cover=-1,
            excess_inventory_value=0,
        )


def test_inventory_health_rejects_negative_excess_inventory():
    with pytest.raises(ValueError, match="excess_inventory_value"):
        InventoryHealthReport(
            item_id="A",
            status=InventoryStatus.HEALTHY,
            months_of_cover=1,
            excess_inventory_value=-1,
        )
