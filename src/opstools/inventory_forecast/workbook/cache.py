"""Dashboard cache model and serialization.

The dashboard cache stores materialized analytical datasets that can be
written to and reconstructed from the Dashboard_Cache worksheet.

This cache is not a runtime cache. It is a workbook persistence layer
used to avoid recomputing expensive dashboard aggregations after a
workbook has been exported.

The workbook schema intentionally leaves Dashboard_Cache unconstrained.
This module therefore owns the serialization contract.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

_DATASET_COLUMN = "__dataset__"


@dataclass(frozen=True, slots=True)
class CacheDataset:
    """Named dashboard dataset.

    Parameters
    ----------
    name:
        Stable dataset identifier.

    data:
        Materialized dataframe.
    """

    name: str
    data: pl.DataFrame

    def __post_init__(self) -> None:
        """Validation for name and data."""
        if not self.name.strip():
            raise ValueError("dataset name cannot be empty")

        if _DATASET_COLUMN in self.data.columns:
            raise ValueError(f"column '{_DATASET_COLUMN}' is reserved")


@dataclass(frozen=True, slots=True)
class DashboardCache:
    """Collection of dashboard datasets."""

    datasets: tuple[CacheDataset, ...]

    def __post_init__(self) -> None:
        """Validation for datasets."""
        names = [dataset.name for dataset in self.datasets]

        if len(names) != len(set(names)):
            raise ValueError("duplicate dataset names detected")

    def get(self, name: str) -> pl.DataFrame:
        """Retrieve a dataset by name."""
        for dataset in self.datasets:
            if dataset.name == name:
                return dataset.data

        raise KeyError(name)

    def contains(self, name: str) -> bool:
        """Check whether a dataset exists."""
        return any(dataset.name == name for dataset in self.datasets)

    @property
    def names(self) -> tuple[str, ...]:
        """Dataset names."""
        return tuple(dataset.name for dataset in self.datasets)


def build_dashboard_cache(
    **datasets: pl.DataFrame,
) -> DashboardCache:
    """Construct a DashboardCache from named dataframes.

    Example:
    -------
    build_dashboard_cache(
        monthly_spend=spend_df,
        supplier_summary=supplier_df,
    )
    """
    return DashboardCache(
        datasets=tuple(
            CacheDataset(
                name=name,
                data=data.clone(),
            )
            for name, data in datasets.items()
        )
    )


def to_dataframe(
    cache: DashboardCache,
) -> pl.DataFrame:
    """Serialize DashboardCache into a worksheet dataframe."""
    if not cache.datasets:
        return pl.DataFrame(
            schema={
                _DATASET_COLUMN: pl.String,
            }
        )

    frames: list[pl.DataFrame] = []

    for dataset in cache.datasets:
        frames.append(
            dataset.data.with_columns(pl.lit(dataset.name).alias(_DATASET_COLUMN))
        )

    return pl.concat(
        frames,
        how="diagonal_relaxed",
    )


def from_dataframe(
    dataframe: pl.DataFrame,
) -> DashboardCache:
    """Reconstruct DashboardCache from worksheet data."""
    if dataframe.is_empty():
        return DashboardCache(datasets=())

    if _DATASET_COLUMN not in dataframe.columns:
        raise ValueError(
            f"dashboard cache worksheet missing '{_DATASET_COLUMN}' column"
        )

    datasets: list[CacheDataset] = []

    names = dataframe.get_column(_DATASET_COLUMN).unique().sort().to_list()

    for name in names:
        dataset_frame = dataframe.filter(pl.col(_DATASET_COLUMN) == name).drop(
            _DATASET_COLUMN
        )

        drop_cols = [
            col
            for col in dataset_frame.columns
            if dataset_frame.get_column(col).null_count() == dataset_frame.height
        ]

        if drop_cols:
            dataset_frame = dataset_frame.drop(drop_cols)

        datasets.append(
            CacheDataset(
                name=name,
                data=dataset_frame,
            )
        )

    return DashboardCache(datasets=tuple(datasets))
