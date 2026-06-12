"""Dataset contract validation.

Validation runs after normalization and before business logic execution.

The goal is to fail early with actionable error messages whenever an ERP export
violates the canonical business contracts defined in domain/contracts.py.

Validation collects all violations before raising so users can correct every
problem in a single iteration rather than discovering errors one at a time.
"""

from collections.abc import Sequence

import polars as pl

from opstools.inventory_forecast.domain.contracts import (
    CLOSING_STOCK_NON_NULL_COLUMNS,
    CLOSING_STOCK_REQUIRED_COLUMNS,
    TRANSACTION_NON_NULL_COLUMNS,
    TRANSACTION_REQUIRED_COLUMNS,
)
from opstools.inventory_forecast.domain.errors import InventoryForecastError


def validate_transaction_dataset(
    frame: pl.LazyFrame,
    dataset_name: str,
) -> None:
    """Validate a canonical POV, GRN, or PV dataset.

    Args:
        frame:
            Canonical normalized dataset.

        dataset_name:
            Human-readable dataset name used in validation messages.

    Raises:
        InventoryForecastError:
            If one or more contract violations are detected.
    """
    violations: list[str] = []

    violations.extend(
        _missing_columns(
            frame=frame,
            required_columns=TRANSACTION_REQUIRED_COLUMNS,
            dataset_name=dataset_name,
        )
    )

    violations.extend(
        _null_columns(
            frame=frame,
            columns=TRANSACTION_NON_NULL_COLUMNS,
            dataset_name=dataset_name,
        )
    )

    _raise_if_invalid(violations)


def validate_closing_stock(
    frame: pl.LazyFrame,
    dataset_name: str = "Closing Stock",
) -> None:
    """Validate a canonical Closing Stock dataset.

    Args:
        frame:
            Canonical normalized Closing Stock dataset.

        dataset_name:
            Dataset label used in validation messages.

    Raises:
        InventoryForecastError:
            If one or more contract violations are detected.
    """
    violations: list[str] = []

    violations.extend(
        _missing_columns(
            frame=frame,
            required_columns=CLOSING_STOCK_REQUIRED_COLUMNS,
            dataset_name=dataset_name,
        )
    )

    violations.extend(
        _null_columns(
            frame=frame,
            columns=CLOSING_STOCK_NON_NULL_COLUMNS,
            dataset_name=dataset_name,
        )
    )

    _raise_if_invalid(violations)


def _missing_columns(
    frame: pl.LazyFrame,
    required_columns: Sequence[str],
    dataset_name: str,
) -> list[str]:
    """Return violations for missing required columns."""
    available = set(frame.collect_schema().names())

    return [
        (f"{dataset_name}: missing required column '{column}'.")
        for column in required_columns
        if column not in available
    ]


def _null_columns(
    frame: pl.LazyFrame,
    columns: Sequence[str],
    dataset_name: str,
) -> list[str]:
    """Return violations for required columns containing null values."""
    available = set(frame.collect_schema().names())

    columns_to_check = [column for column in columns if column in available]

    if not columns_to_check:
        return []

    null_counts = (
        frame.select(
            [
                pl.col(column).is_null().sum().alias(column)
                for column in columns_to_check
            ]
        )
        .collect()
        .row(0, named=True)
    )

    violations: list[str] = []

    for column, null_count in null_counts.items():
        if null_count > 0:
            violations.append(
                f"{dataset_name}: column '{column}' contains "
                f"{null_count} null value(s)."
            )

    return violations


def _raise_if_invalid(
    violations: Sequence[str],
) -> None:
    """Raise a single exception containing all validation failures."""
    if not violations:
        return

    message = "\n".join(
        [
            "Dataset validation failed:",
            *violations,
        ]
    )

    raise InventoryForecastError(message)
