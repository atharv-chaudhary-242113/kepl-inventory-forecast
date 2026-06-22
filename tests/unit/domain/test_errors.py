"""Unit tests for the domain error hierarchy."""

import pytest

from opstools.inventory_forecast.domain import (
    DataValidationError,
    ForecastingError,
    InvalidSchemaError,
    InventoryForecastError,
    MissingColumnError,
    WorkbookError,
)


@pytest.mark.parametrize(
    "subclass",
    [
        DataValidationError,
        ForecastingError,
        InvalidSchemaError,
        MissingColumnError,
        WorkbookError,
    ],
)
def test_all_domain_errors_inherit_base(subclass):
    # API_CONTRACT.md: anything raised across a boundary must be catchable as
    # the single base type, so services can translate uniformly.
    assert issubclass(subclass, InventoryForecastError)


def test_specific_errors_inherit_their_category_base():
    assert issubclass(MissingColumnError, DataValidationError)
    assert issubclass(InvalidSchemaError, DataValidationError)
    assert issubclass(ForecastingError, InventoryForecastError)
    assert issubclass(WorkbookError, InventoryForecastError)


def test_base_is_an_exception():
    assert issubclass(InventoryForecastError, Exception)


def test_subclass_is_catchable_as_base():
    with pytest.raises(InventoryForecastError):
        raise InvalidSchemaError("header row not found in pov_2024.xlsx")
