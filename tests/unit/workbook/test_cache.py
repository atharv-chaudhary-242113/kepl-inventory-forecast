from __future__ import annotations

import polars as pl
import pytest

from opstools.inventory_forecast.workbook.cache import (
    # pyrefly: ignore [missing-module-attribute]
    CacheDataset,
    # pyrefly: ignore [missing-module-attribute]
    DashboardCache,
    # pyrefly: ignore [missing-module-attribute]
    build_dashboard_cache,
    # pyrefly: ignore [missing-module-attribute]
    from_dataframe,
    # pyrefly: ignore [missing-module-attribute]
    to_dataframe,
)


def test_cache_dataset_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="dataset name cannot be empty"):
        CacheDataset(
            name="   ",
            data=pl.DataFrame(),
        )


def test_cache_dataset_rejects_reserved_column() -> None:
    with pytest.raises(ValueError, match="reserved"):
        CacheDataset(
            name="test",
            data=pl.DataFrame({"__dataset__": [1]}),
        )


def test_dashboard_cache_rejects_duplicate_names() -> None:
    dataset = CacheDataset(
        name="a",
        data=pl.DataFrame({"x": [1]}),
    )

    with pytest.raises(
        ValueError,
        match="duplicate dataset names",
    ):
        DashboardCache(
            datasets=(dataset, dataset),
        )


def test_contains_and_get() -> None:
    dataframe = pl.DataFrame({"x": [1]})

    cache = DashboardCache(
        datasets=(
            CacheDataset(
                name="sales",
                data=dataframe,
            ),
        )
    )

    assert cache.contains("sales")
    assert not cache.contains("missing")

    result = cache.get("sales")

    assert result.equals(dataframe)


def test_get_unknown_dataset_raises() -> None:
    cache = DashboardCache(datasets=())

    with pytest.raises(KeyError):
        cache.get("missing")


def test_names_property() -> None:
    cache = DashboardCache(
        datasets=(
            CacheDataset(
                name="a",
                data=pl.DataFrame(),
            ),
            CacheDataset(
                name="b",
                data=pl.DataFrame(),
            ),
        )
    )

    assert cache.names == ("a", "b")


def test_build_dashboard_cache_clones_frames() -> None:
    source = pl.DataFrame({"x": [1]})

    cache = build_dashboard_cache(sales=source)

    assert cache.contains("sales")


def test_to_dataframe_empty_cache() -> None:
    dataframe = to_dataframe(DashboardCache(datasets=()))

    assert dataframe.columns == ["__dataset__"]
    assert dataframe.is_empty()


def test_to_dataframe_serializes_multiple_datasets() -> None:
    cache = build_dashboard_cache(
        sales=pl.DataFrame({"x": [1]}),
        spend=pl.DataFrame({"y": [2]}),
    )

    dataframe = to_dataframe(cache)

    assert "__dataset__" in dataframe.columns
    assert dataframe.height == 2


def test_from_dataframe_empty_frame() -> None:
    cache = from_dataframe(pl.DataFrame(schema={"__dataset__": pl.String}))

    assert cache.datasets == ()


def test_from_dataframe_requires_dataset_column() -> None:
    with pytest.raises(
        ValueError,
        match="missing '__dataset__'",
    ):
        from_dataframe(pl.DataFrame({"x": [1]}))


def test_round_trip_cache_serialization() -> None:
    original = build_dashboard_cache(
        sales=pl.DataFrame({"item": ["A"], "qty": [10]}),
        spend=pl.DataFrame({"amount": [100]}),
    )

    reconstructed = from_dataframe(to_dataframe(original))

    assert reconstructed.names == original.names

    for name in original.names:
        assert reconstructed.get(name).equals(original.get(name))
