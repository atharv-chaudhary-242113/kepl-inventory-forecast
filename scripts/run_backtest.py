"""CLI entry point to execute a temporal holdout backtest.

Validates the accuracy of the forecasting engine using actual historical data.
"""

import argparse
from datetime import date
from pathlib import Path

import polars as pl

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.domain import SourceKind
from opstools.inventory_forecast.engine.classification import classify_sbc
from opstools.inventory_forecast.engine.demand import reconstruct_demand
from opstools.inventory_forecast.engine.forecasting import forecast_demand
from opstools.inventory_forecast.ingestion import read_source
from opstools.inventory_forecast.validation.evaluator import BacktestEvaluator
from opstools.inventory_forecast.validation.report import (
    export_validation_report,
)
from opstools.inventory_forecast.validation.rolling_origin import (
    run_rolling_origin,
)


def forecast_adapter(demand: pl.DataFrame, cfg: Settings) -> pl.DataFrame:
    """Adapts the core engine's LazyFrame signature for the Evaluator.

    The Evaluator orchestrates strictly collected DataFrames to ensure state
    separation, while the core engine uses LazyFrames for query optimization.
    """
    demand_lf = demand.lazy()

    # Generate the required SBC classification dynamically from the sterile past
    sbc_lf = classify_sbc(demand_lf, cfg)

    # Execute the actual forecasting engine graph
    forecast_lf = forecast_demand(
        demand=demand_lf, sbc=sbc_lf, horizon=cfg.forecast_horizon, cfg=cfg
    )

    return forecast_lf.collect()


def main() -> int:
    """Execute the holdout backtest and generate the validation report."""
    parser = argparse.ArgumentParser(description="Run Layer 3 temporal backtest.")
    parser.add_argument("--pov", type=Path, required=True)
    parser.add_argument("--grn", type=Path, required=True)
    parser.add_argument("--pv", type=Path, required=True)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, required=True, help="Path for validation_report.xlsx"
    )
    parser.add_argument(
        "--cutoff", type=date.fromisoformat, required=True, help="YYYY-MM-DD split date"
    )
    parser.add_argument(
        "--rolling",
        action="store_true",
        help=("Run rolling-origin validation using multiple temporal cutoffs."),
    )

    args = parser.parse_args()

    print("Loading raw ERP exports...")
    pov = read_source(args.pov, SourceKind.POV)
    grn = read_source(args.grn, SourceKind.GRN)
    pv = read_source(args.pv, SourceKind.PV)
    stock = read_source(args.stock, SourceKind.CLOSING_STOCK)

    print("\nClosing Stock Date Range:")

    print(
        stock.select(
            pl.col("date").min().alias("min_date"),
            pl.col("date").max().alias("max_date"),
        )
    )

    settings = Settings()

    print(f"Applying strict temporal mask at cutoff {args.cutoff}...")
    train_pov = pov.filter(pl.col("date") < args.cutoff)
    train_grn = grn.filter(pl.col("date") < args.cutoff)
    train_pv = pv.filter(pl.col("date") < args.cutoff)
    train_stock = stock.filter(pl.col("date") < args.cutoff)

    if train_stock.is_empty():
        raise ValueError(
            "Closing Stock became empty after temporal masking. "
            "This usually indicates the stock file is a snapshot "
            "rather than a historical series. "
            "Backtest cannot continue safely."
        )

    print("Reconstructing demand...")
    # Explicitly call .collect() to convert LazyFrames to DataFrames for the Evaluator
    train_demand = reconstruct_demand(
        pov=train_pov, grn=train_grn, pv=train_pv, stock=train_stock, cfg=settings
    ).collect()

    full_demand = reconstruct_demand(
        pov=pov, grn=grn, pv=pv, stock=stock, cfg=settings
    ).collect()

    test_demand = full_demand.filter(pl.col("date") >= args.cutoff)

    print("Running holdout evaluation...")
    evaluator = BacktestEvaluator(forecast_callback=forecast_adapter, settings=settings)

    try:
        metrics, timeseries = evaluator.evaluate(
            train_demand=train_demand, test_demand=test_demand
        )

        print("Generating audit artifact...")
        export_validation_report(
            output_path=args.out,
            metrics=metrics,
            timeseries=timeseries,
            cutoff_date=str(args.cutoff),
        )

        print(f"Validation complete! Report saved to: {args.out}")
        return 0
    except ValueError as e:
        print(f"Backtest Configuration Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
