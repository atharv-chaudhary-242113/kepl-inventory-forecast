"""Entry point for headless workbook generation.

Executes the inventory analytics pipeline and generates the single
source-of-truth Excel workbook for the Business Intelligence platform.
Designed for automated runs, cron jobs, and CI/CD pipelines.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.domain.models import SourceSet
from opstools.inventory_forecast.services.pipeline_service import execute_pipeline
from opstools.inventory_forecast.services.state import PipelineConfig, PipelineState

logger = logging.getLogger(__name__)

# Hardcoded fallback version if not installed as a package
__version__ = "2.0.0"


def _discover_files(input_dir: Path, pattern: str) -> tuple[Path, ...]:
    """Discover source files matching a pattern in the input directory.

    Args:
        input_dir: The directory containing ERP extracts.
        pattern: The substring to match in the filename.

    Returns:
        A sorted tuple of matching file paths.
    """
    files = []
    for p in input_dir.rglob("*"):
        if (
            p.is_file()
            and p.suffix.lower() in (".csv", ".xlsx")
            and pattern.lower() in p.name.lower()
        ):
            files.append(p)

    return tuple(sorted(files))


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate the KEPL Inventory Forecast BI Workbook."
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing the raw ERP extracts (.csv or .xlsx).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Path where the output Excel workbook will be written.",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=12,
        help="Forecast horizon in months (default: 12).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    input_dir: Path = args.input_dir
    if not input_dir.is_dir():
        logger.error("Input directory does not exist: %s", input_dir)
        return 1

    logger.info("Discovering ERP source files in %s", input_dir)

    # Simple heuristic mapping for Business Intelligence ingestion
    source_set = SourceSet(
        pov=_discover_files(input_dir, "pov"),
        grn=_discover_files(input_dir, "grn"),
        pv=_discover_files(input_dir, "pv"),
        closing_stock=_discover_files(input_dir, "stock"),
    )

    total_files = len(source_set.all_paths)
    if total_files == 0:
        logger.error("No valid ERP source files found in %s", input_dir)
        return 1

    logger.info("Found %d source files.", total_files)

    config = PipelineConfig(
        source_set=source_set,
        output_workbook_path=args.output,
        forecast_horizon=args.horizon,
        application_version=__version__,
    )

    state = PipelineState(config=config)

    try:
        execute_pipeline(state)
    except (OSError, ValueError, RuntimeError):
        # Exception is already caught and logged in execute_pipeline
        return 1

    if not state.is_successful:
        logger.error("Pipeline failed to complete successfully.")
        if state.error:
            logger.error("Terminal Error: %s", state.error)
        return 1

    logger.info(
        "Success! BI Workbook generated at %s in %.2f seconds.",
        args.output,
        state.processing_time_seconds,
    )
    logger.info(
        "Metrics: %d suppliers, %d items, %d records processed.",
        state.total_suppliers,
        state.total_items,
        state.total_records,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
