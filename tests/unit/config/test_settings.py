"""Unit tests for the runtime Settings model."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from opstools.inventory_forecast.config.settings import Settings
from opstools.inventory_forecast.domain.enums import ForecastGranularity


def test_defaults_match_documented_values():
    s = Settings()
    assert s.forecast_horizon == 12
    assert s.forecast_granularity is ForecastGranularity.MONTHLY
    assert s.service_z == pytest.approx(1.65)
    assert s.default_lead_time_days == 30
    assert s.freight_rate == Decimal("0.18")
    assert s.abc_a_threshold == pytest.approx(0.80)
    assert s.abc_b_threshold == pytest.approx(0.95)
    assert s.enable_supplier_risk is True
    assert s.enable_partnerships is True


def test_custom_settings_are_preserved():
    s = Settings(
        forecast_horizon=6,
        forecast_granularity=ForecastGranularity.QUARTERLY,
        service_z=2.0,
        default_lead_time_days=45,
        freight_rate=Decimal("0.05"),
        abc_a_threshold=0.7,
        abc_b_threshold=0.9,
        enable_supplier_risk=False,
        enable_partnerships=False,
    )

    assert s.forecast_horizon == 6
    assert s.forecast_granularity is ForecastGranularity.QUARTERLY
    assert s.service_z == pytest.approx(2.0)
    assert s.default_lead_time_days == 45
    assert s.freight_rate == Decimal("0.05")
    assert s.abc_a_threshold == pytest.approx(0.7)
    assert s.abc_b_threshold == pytest.approx(0.9)
    assert s.enable_supplier_risk is False
    assert s.enable_partnerships is False


def test_horizon_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(forecast_horizon=0)


def test_service_z_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(service_z=0.0)


def test_default_lead_time_days_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(default_lead_time_days=0)


def test_freight_rate_may_not_be_negative():
    with pytest.raises(ValidationError):
        Settings(freight_rate=Decimal("-0.01"))


def test_abc_thresholds_must_be_inside_unit_interval():
    with pytest.raises(ValidationError):
        Settings(abc_a_threshold=0.0)

    with pytest.raises(ValidationError):
        Settings(abc_b_threshold=1.0)


def test_abc_thresholds_must_be_ordered():
    with pytest.raises(ValidationError):
        Settings(abc_a_threshold=0.9, abc_b_threshold=0.8)


def test_settings_are_frozen():
    s = Settings()
    with pytest.raises(ValidationError):
        s.forecast_horizon = 24
