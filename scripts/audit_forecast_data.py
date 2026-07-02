"""Audit demand history before forecasting.

Purpose
-------
Identify data-quality and forecasting-readiness issues before
running the forecasting engine.

This script answers:

- How many SKUs exist?
- How many observations per SKU?
- Which SKUs have insufficient history?
- Which SBC classes dominate?
- Which SKUs are likely to fail ETS/Theta?

Run
---
python scripts/audit_forecast_data.py --pov data/POV.xlsx
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from opstools.inventory_forecast.domain import SourceKind
from opstools.inventory_forecast.engine.classification import classify_sbc
from opstools.inventory_forecast.engine.demand import reconstruct_demand
from opstools.inventory_forecast.ingestion import read_source


def load_demand(
    pov_path: Path,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Load demand history."""
    supported_extensions = {
        ".csv",
        ".xls",
        ".xlsx",
        ".xlsm",
    }

    dataframes: list[pl.DataFrame] = []
    exceptions_list: list[pl.DataFrame] = []

    if pov_path.is_dir():
        files = sorted(
            path
            for path in pov_path.iterdir()
            if path.is_file() and path.suffix.lower() in supported_extensions
        )
    else:
        files = [pov_path]

    if not files:
        msg = f"No supported input files found in '{pov_path}'."
        raise FileNotFoundError(msg)

    for file_path in files:
        lazy_frame, exceptions = read_source(
            file_path,
            SourceKind.POV,
        )

        dataframes.append(
            reconstruct_demand(
                lazy_frame,
            ).collect()
        )

        if exceptions.height > 0:
            exceptions_list.append(exceptions)

    demand = pl.concat(
        dataframes,
        how="vertical_relaxed",
    )

    if exceptions_list:
        all_exceptions = pl.concat(
            exceptions_list,
            how="vertical_relaxed",
        )
    else:
        all_exceptions = pl.DataFrame(
            schema={
                "File Name": pl.Utf8,
                "Row Number": pl.Int64,
                "Reason": pl.Utf8,
                "Offending Value": pl.Utf8,
                "Full Record": pl.Utf8,
            }
        )

    return demand, all_exceptions


def build_observation_profile(
    demand: pl.DataFrame,
) -> pl.DataFrame:
    """Count observations per supplier-item."""
    return (
        demand.group_by(
            [
                "supplier",
                "item",
            ]
        )
        .agg(pl.len().alias("observation_count"))
        .sort("observation_count")
    )


def build_bucket_summary(
    profile: pl.DataFrame,
) -> pl.DataFrame:
    """Bucket observation counts."""
    return (
        profile.with_columns(
            pl.when(pl.col("observation_count") == 1)
            .then(pl.lit("1"))
            .when(pl.col("observation_count") <= 3)
            .then(pl.lit("2-3"))
            .when(pl.col("observation_count") <= 5)
            .then(pl.lit("4-5"))
            .when(pl.col("observation_count") <= 11)
            .then(pl.lit("6-11"))
            .when(pl.col("observation_count") <= 23)
            .then(pl.lit("12-23"))
            .otherwise(pl.lit("24+"))
            .alias("bucket")
        )
        .group_by("bucket")
        .agg(pl.len().alias("sku_count"))
        .sort("bucket")
    )


def build_sbc_summary(
    demand: pl.DataFrame,
) -> pl.DataFrame:
    """Summarize SBC distribution."""
    sbc = classify_sbc(demand.lazy()).collect()

    return (
        sbc.group_by("demand_class")
        .agg(pl.len().alias("sku_count"))
        .sort(
            "sku_count",
            descending=True,
        )
    )


def print_portfolio_summary(
    profile: pl.DataFrame,
) -> None:
    """Print high-level portfolio statistics."""
    total = profile.height

    tiny_1 = profile.filter(pl.col("observation_count") == 1).height

    tiny_3 = profile.filter(pl.col("observation_count") <= 3).height

    tiny_6 = profile.filter(pl.col("observation_count") <= 6).height

    print()
    print("=" * 60)
    print("PORTFOLIO SUMMARY")
    print("=" * 60)

    print(f"Total SKUs: {total}")

    print(f"1 observation: {tiny_1}")

    print(f"<=3 observations: {tiny_3}")

    print(f"<=6 observations: {tiny_6}")

    print()


def build_sbc_frame(
    demand: pl.DataFrame,
) -> pl.DataFrame:
    """Return SKU classifications."""
    return classify_sbc(demand.lazy()).collect()


def main() -> int:
    """Execute audit."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--pov",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    demand, exceptions = load_demand(
        args.pov,
    )

    sbc = build_sbc_frame(
        demand,
    )

    sbc_summary = (
        sbc.group_by("demand_class")
        .agg(pl.len().alias("sku_count"))
        .sort(
            "sku_count",
            descending=True,
        )
    )

    profile = build_observation_profile(
        demand,
    )
    classification_audit = profile.join(
        sbc.select(
            [
                "supplier",
                "item",
                "demand_class",
            ]
        ),
        on=[
            "supplier",
            "item",
        ],
        how="inner",
    )
    (
        classification_audit.filter(pl.col("observation_count") == 1).group_by(
            "demand_class"
        )
    ).agg(pl.len())

    classification_breakdown = (
        classification_audit.with_columns(
            pl.when(pl.col("observation_count") == 1)
            .then(pl.lit("1"))
            .when(pl.col("observation_count") <= 3)
            .then(pl.lit("2-3"))
            .when(pl.col("observation_count") <= 5)
            .then(pl.lit("4-5"))
            .when(pl.col("observation_count") <= 11)
            .then(pl.lit("6-11"))
            .otherwise(pl.lit("12+"))
            .alias("obs_bucket")
        )
        .group_by(
            [
                "demand_class",
                "obs_bucket",
            ]
        )
        .agg(pl.len().alias("sku_count"))
        .sort(
            [
                "demand_class",
                "obs_bucket",
            ]
        )
    )

    buckets = build_bucket_summary(
        profile,
    )

    print_portfolio_summary(
        profile,
    )

    print("OBSERVATION BUCKETS")
    print(buckets)

    print()

    print("SBC DISTRIBUTION")
    print(sbc_summary)

    print()

    print("SHORTEST SERIES")
    print(profile.head(50))

    print()
    print("CLASSIFICATION VS OBSERVATIONS")
    print(classification_breakdown)

    print()

    print("=" * 60)
    print("DATA QUALITY")
    print("=" * 60)

    print(f"Rejected Records: {exceptions.height}")

    if exceptions.height > 0:
        print()
        print("REJECTION REASONS")
        print(
            exceptions.group_by("Reason")
            .agg(pl.len().alias("count"))
            .sort("count", descending=True)
        )

        print()
        print("FIRST 20 REJECTED RECORDS")
        print(exceptions.head(20))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
