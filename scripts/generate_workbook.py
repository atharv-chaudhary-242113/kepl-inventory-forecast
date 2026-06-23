"""CLI entry point to execute the pipeline offline before the UI is built."""

import argparse
from datetime import date
from pathlib import Path

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.services import PipelineProgress
from opstools.inventory_forecast.services.pipeline_service import PipelineService
from opstools.inventory_forecast.services.state import PipelineRequest


def _progress_handler(progress: PipelineProgress) -> None:
    """Terminal callback for pipeline progress."""
    print(
        f"[{progress.percent_complete:3d}%] {progress.stage.name}: {progress.message}"
    )


def main() -> int:
    """Execute the offline workbook generation pipeline."""
    parser = argparse.ArgumentParser(description="Run the KEPL pipeline offline.")
    parser.add_argument("--pov", type=Path, required=True, help="Path to POV")
    parser.add_argument("--grn", type=Path, required=True, help="Path to GRN")
    parser.add_argument("--pv", type=Path, required=True, help="Path to PV")
    parser.add_argument("--stock", type=Path, required=True, help="Path to Stock")
    parser.add_argument("--out", type=Path, required=True, help="Output path (.xlsx)")
    parser.add_argument("--snapshot", type=date.fromisoformat, required=True)

    args = parser.parse_args()

    for input_file in [args.pov, args.grn, args.pv, args.stock]:
        if not input_file.exists():
            print(f"Error: Input file not found: {input_file}")
            return 1

    request = PipelineRequest(
        pov_path=args.pov,
        grn_path=args.grn,
        pv_path=args.pv,
        closing_stock_path=args.stock,
        output_path=args.out,
        snapshot_date=args.snapshot,
    )

    settings = Settings()
    print(f"Starting KEPL Pipeline run targeting: {args.out}\n")

    try:
        result = PipelineService.run_pipeline(
            request=request, settings=settings, progress_callback=_progress_handler
        )

        meta = result.metadata
        print(f"\nSuccess! Workbook exported in {meta.processing_time_seconds:.2f}s.")
        return 0

    except Exception as e:
        print(f"\nPipeline execution failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
