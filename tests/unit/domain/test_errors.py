"""Unit tests for the domain error hierarchy."""

import pytest

from opstools.inventory_forecast.domain.errors import (
    ForecastError,
    InventoryForecastError,
    SchemaError,
    ValidationError,
    WorkbookVersionError,
)


@pytest.mark.parametrize(
    "subclass",
    [SchemaError, ValidationError, WorkbookVersionError, ForecastError],
)
def test_all_domain_errors_inherit_base(subclass):
    # API_CONTRACT.md: anything raised across a boundary must be catchable as
    # the single base type, so services can translate uniformly.
    assert issubclass(subclass, InventoryForecastError)


def test_base_is_an_exception():
    assert issubclass(InventoryForecastError, Exception)


def test_subclass_is_catchable_as_base():
    with pytest.raises(InventoryForecastError):
        raise SchemaError("header row not found in pov_2024.xlsx")
