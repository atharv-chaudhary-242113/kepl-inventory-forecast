"""Data Understanding & Diagnostic Ingestion Pipeline.

This script executes Phase 1 (Ingestion) in an isolated, highly observable
environment. It strictly follows procurement domain logic:
1. Establishes the Master Item Universe exclusively from Purchase Vouchers (PV),
   treating PVs as the absolute source of truth for all
   transactions (prices, quantities).
2. Reconstructs the Procurement Lifecycle by linking PVs backward to GRNs (Delivery)
   and POVs (Demand Signal) to determine Lead Times and Historical Demand. Any order
   not present in the PV ledger is inherently dropped/treated as cancelled.
3. Calculates ABC classifications across the validated PV universe.
4. Ingests Closing Stock purely to map physical counts against
   the established ABC classes.

Outputs a purely structural workbook containing zero downstream analytics, formatted
specifically for Business Intelligence readability in Excel.
"""

import argparse
import ast
import datetime
import logging
import sys
from decimal import Decimal
from pathlib import Path

import polars as pl
import xlsxwriter

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.domain import SourceKind
from opstools.inventory_forecast.engine.classification import build_abc_classification
from opstools.inventory_forecast.ingestion.normalize import normalize_join_keys
from opstools.inventory_forecast.ingestion.reader import read_source


def setup_observability(log_file: Path, verbose: bool) -> logging.Logger:
    """Configure file-based observability and tracing strategy."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("opstools")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if verbose:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def expand_exceptions(exceptions_df: pl.DataFrame) -> pl.DataFrame:
    """Unpack JSON-like 'Full Record' strings into distinct columns."""
    if exceptions_df.height == 0:
        return pl.DataFrame(
            {"File Path": [], "Sheet & Row": [], "Reason": [], "Raw Content": []}
        )

    expanded_rows = []
    # Limit raw exception output to 100 rows to prevent massive tedious files
    for row in exceptions_df.head(100).iter_rows(named=True):
        sheet_row = f"Sheet1 / Row {row['Row Number']}"
        base_dict = {
            "File Path": row["File Name"],
            "Sheet & Row": sheet_row,
            "Reason": row["Reason"],
        }

        try:
            record_content = ast.literal_eval(row["Full Record"])
            if isinstance(record_content, dict):
                for k, v in record_content.items():
                    base_dict[f"Content: {k}"] = v
            else:
                base_dict["Content: Unparsed Raw"] = str(row["Full Record"])
        except (ValueError, SyntaxError):
            base_dict["Content: Unparsed Raw"] = str(row["Full Record"])

        expanded_rows.append(base_dict)

    return pl.DataFrame(expanded_rows)


def ingest_ledger(
    files: list[Path], kind: SourceKind, logger: logging.Logger
) -> tuple[pl.LazyFrame | None, list[pl.DataFrame]]:
    """Ingest, aggregate, and normalize a specific category of ERP logs."""
    if not files:
        logger.warning(f"No source files found for {kind.name}.")
        return None, []

    frames = []
    exceptions = []
    for file in files:
        logger.info(f"Ingesting {kind.name} log: {file.name}")
        valid_lazy, exc = read_source(file, kind)
        frames.append(valid_lazy.collect())
        exceptions.append(exc)

    full_df = pl.concat(frames).lazy()
    keys = ["item", "supplier"] if kind != SourceKind.CLOSING_STOCK else ["item"]
    return normalize_join_keys(full_df, keys), exceptions


def run_data_understanding(  # noqa: D103
    input_dir: Path, output_file: Path, log_file: Path, verbose: bool = False
) -> None:
    setup_observability(log_file, verbose)
    script_logger = logging.getLogger("opstools.data_understanding")

    script_logger.info(f"Scanning {input_dir} recursively for source files...")
    supported_extensions = {".xlsx", ".xls", ".xlsm", ".csv"}
    all_files = [
        f
        for f in input_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]

    # Strictly separate the transactional layers
    pv_files = [
        f for f in all_files if "PV" in f.name.upper() and "POV" not in f.name.upper()
    ]
    pov_files = [f for f in all_files if "POV" in f.name.upper()]
    grn_files = [f for f in all_files if "GRN" in f.name.upper()]
    cs_files = [
        f for f in all_files if "CLOSINGSTOCK" in f.name.replace(" ", "").upper()
    ]

    script_logger.info(
        f"Found {len(pv_files)} PVs, "
        f"{len(grn_files)} GRNs, "
        f"{len(pov_files)} POVs, "
        f"and {len(cs_files)} Stock files."
    )

    # =========================================================================
    # STEP 1: INGEST ALL SOURCES
    # =========================================================================
    pv_full, pv_exc = ingest_ledger(pv_files, SourceKind.PV, script_logger)
    pov_full, pov_exc = ingest_ledger(pov_files, SourceKind.POV, script_logger)
    grn_full, grn_exc = ingest_ledger(grn_files, SourceKind.GRN, script_logger)
    cs_full, cs_exc = ingest_ledger(cs_files, SourceKind.CLOSING_STOCK, script_logger)

    if pv_full is None:
        script_logger.error(
            "No PV files available. Cannot establish source of truth. Exiting."
        )
        return

    # Generate Sheet 1: Master Catalog (All Unique Items Established strictly by PV)
    master_catalog = (
        pv_full.select(["supplier", "item"])
        .unique()
        .drop_nulls()
        .sort(["supplier", "item"])
    ).collect()

    # =========================================================================
    # STEP 2: PROCUREMENT LIFECYCLE RECONCILIATION
    # =========================================================================
    script_logger.info(
        "Reconciling Procurement Lifecycle (PV backward to GRN and POV)..."
    )

    # 1. PV is the Absolute Source of Truth (Contains Real Qty & Price)
    pv_clean = (
        pv_full.filter(pl.col("date").is_not_null())
        .sort("date")
        .select(["supplier", "item", "date", "qty", "price", "amount", "voucher"])
        .rename(
            {
                "date": "pv_date",
                "voucher": "pv_voucher",
                "qty": "actual_qty",
                "price": "actual_price",
                "amount": "actual_amount",
            }
        )
        .collect()
    )

    # 2. GRN (Discard qty/price, keep only dates for delivery tracing)
    if grn_full is not None:
        grn_clean = (
            grn_full.filter(pl.col("date").is_not_null())
            .sort("date")
            .select(["supplier", "item", "date", "voucher"])
            .rename({"date": "grn_date", "voucher": "grn_voucher"})
            .collect()
        )
    else:
        grn_clean = pl.DataFrame()

    # 3. POV (Discard qty/price, keep only dates for demand tracing)
    if pov_full is not None:
        pov_clean = (
            pov_full.filter(pl.col("date").is_not_null())
            .sort("date")
            .select(["supplier", "item", "date", "voucher"])
            .rename({"date": "pov_date", "voucher": "pov_voucher"})
            .collect()
        )
    else:
        pov_clean = pl.DataFrame()

    lifecycle = pv_clean
    if not grn_clean.is_empty():
        lifecycle = lifecycle.join_asof(
            grn_clean,
            left_on="pv_date",
            right_on="grn_date",
            by=["supplier", "item"],
            strategy="backward",
        )
    else:
        lifecycle = lifecycle.with_columns(
            pl.lit(None).cast(pl.Date).alias("grn_date"),
            pl.lit(None).cast(pl.Utf8).alias("grn_voucher"),
        )

    if not pov_clean.is_empty():
        lifecycle = lifecycle.join_asof(
            pov_clean,
            left_on="pv_date",
            right_on="pov_date",
            by=["supplier", "item"],
            strategy="backward",
        )
    else:
        lifecycle = lifecycle.with_columns(
            pl.lit(None).cast(pl.Date).alias("pov_date"),
            pl.lit(None).cast(pl.Utf8).alias("pov_voucher"),
        )

    lifecycle = lifecycle.with_columns(
        (pl.col("grn_date") - pl.col("pov_date"))
        .dt.total_days()
        .alias("lead_time_days")
    )

    # =========================================================================
    # STEP 3: DEMAND & LEAD TIME EXTRACTIONS
    # =========================================================================
    lead_time_analysis = (
        lifecycle.filter(pl.col("lead_time_days").is_not_null())
        .group_by(["supplier", "item"])
        .agg(
            pl.col("lead_time_days").mean().alias("Avg_Lead_Time_Days"),
            pl.col("lead_time_days").min().alias("Min_Lead_Time"),
            pl.col("lead_time_days").max().alias("Max_Lead_Time"),
            pl.col("pv_voucher").count().alias("Completed_Orders_Count"),
        )
        .sort("Avg_Lead_Time_Days", descending=True)
    )

    demand_history = (
        lifecycle.filter(pl.col("pov_date").is_not_null())
        .with_columns(pl.col("pov_date").dt.strftime("%Y-%m").alias("Demand_Month"))
        .group_by(["item", "Demand_Month"])
        .agg(
            pl.col("actual_qty").sum().alias("Total_Fulfilled_Demand"),
            pl.col("actual_amount").sum().alias("Total_Spend"),
        )
        .sort(["item", "Demand_Month"])
    )

    # =========================================================================
    # STEP 4: ABC CLASSIFICATION & BASELINE INVENTORY
    # =========================================================================
    script_logger.info("Calculating ABC Categories across the Item Universe...")
    settings = Settings()
    abc_df = build_abc_classification(pv_full, settings).collect()
    item_master_abc = (
        abc_df.sort("annual_value", descending=True)
        .group_by("item")
        .agg(pl.col("abc_class").first())
    )

    if cs_full is not None:
        mapped_stock = (
            cs_full.collect()
            .join(item_master_abc, on="item", how="left")
            .with_columns(pl.col("abc_class").fill_null("OTHER (No Purchase History)"))
        )

        total_stock_qty = mapped_stock.select(pl.col("qty").sum()).item()
        if total_stock_qty == 0:
            total_stock_qty = 1

        baseline_inventory = (
            mapped_stock.group_by("abc_class")
            .agg(
                pl.col("item").n_unique().alias("Unique_Items_Found"),
                pl.col("qty").sum().alias("Total_Physical_Quantity"),
            )
            .with_columns(
                # Fixed: Removed (* 100) and explicit rounding.
                # Leaving it as a pure float fraction allows Excel to format it cleanly.
                (pl.col("Total_Physical_Quantity") / total_stock_qty).alias(
                    "Percentage_of_Total_Stock"
                )
            )
            .sort("abc_class")
        )
    else:
        baseline_inventory = pl.DataFrame()

    # =========================================================================
    # STEP 5: OUTPUT GENERATION (WITH STRICT EXCEL FORMATTING)
    # =========================================================================
    all_exceptions = pv_exc + pov_exc + grn_exc + cs_exc
    exceptions_sheet = (
        expand_exceptions(pl.concat(all_exceptions))
        if all_exceptions
        else pl.DataFrame()
    )

    script_logger.info(f"Writing diagnostic insights to {output_file}...")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with xlsxwriter.Workbook(output_file) as workbook:
        header_format = workbook.add_format(
            {"bold": True, "bg_color": "#2C3E50", "font_color": "white", "border": 1}
        )

        # Pre-define rigorous cell formats for xlsxwriter
        fmt_date = workbook.add_format({"num_format": "yyyy-mm-dd"})
        fmt_pct = workbook.add_format({"num_format": "0.00%"})
        fmt_currency = workbook.add_format({"num_format": "#,##0.00"})
        fmt_float = workbook.add_format({"num_format": "#,##0.00"})
        fmt_int = workbook.add_format({"num_format": "#,##0"})

        sheets = {
            "Master_Supplier_Item_Catalog": master_catalog,
            "Historical_Demand": demand_history,
            "Lead_Time_Analysis": lead_time_analysis,
            "Baseline_Inventory_Metrics": baseline_inventory,
            "Procurement_Lifecycle_Sample": lifecycle.head(100),
            "Ingestion_Exceptions": exceptions_sheet,
            "File_Manifest": pl.DataFrame(
                {
                    "File Scanned": [
                        f.name for f in pv_files + pov_files + grn_files + cs_files
                    ],
                }
            ),
        }

        for sheet_name, df in sheets.items():
            worksheet = workbook.add_worksheet(sheet_name)

            # Map column formatting rules dynamically based on names
            col_formats = []
            for col_name in df.columns:
                name_lower = col_name.lower()
                if "percent" in name_lower:
                    col_formats.append(fmt_pct)
                elif any(
                    x in name_lower
                    for x in ["price", "amount", "spend", "value", "cost"]
                ):
                    col_formats.append(fmt_currency)
                elif any(x in name_lower for x in ["qty", "quantity", "days", "time"]):
                    col_formats.append(fmt_float)
                elif any(x in name_lower for x in ["count", "unique"]):
                    col_formats.append(fmt_int)
                elif "date" in name_lower:
                    col_formats.append(fmt_date)
                else:
                    col_formats.append(None)

            # Write Header
            for col_num, column_name in enumerate(df.columns):
                worksheet.write(0, col_num, column_name, header_format)

            # Write Rows and apply strict typing
            for row_num, row_data in enumerate(df.iter_rows()):
                for col_num, cell_value in enumerate(row_data):
                    fmt = col_formats[col_num]

                    # Convert Polars/Python Decimals to pure floats so
                    # Excel treats them as numbers
                    if isinstance(cell_value, Decimal):
                        cell_value = float(cell_value)

                    # Route dates strictly to the date handler to
                    # prevent integer serialization (e.g., 45333)
                    if isinstance(cell_value, (datetime.date, datetime.datetime)):
                        worksheet.write_datetime(
                            row_num + 1, col_num, cell_value, fmt or fmt_date
                        )
                    else:
                        worksheet.write(row_num + 1, col_num, cell_value, fmt)

            worksheet.autofit()

    script_logger.info("Data Understanding pipeline complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Isolated Data Understanding diagnostic engine."
    )
    parser.add_argument(
        "-i", "--input-dir", type=Path, required=True, help="Path to raw ERP inputs."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Path for analytical spreadsheet.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable stdout logging."
    )

    args = parser.parse_args()
    log_path = args.output.parent / "pipeline_trace.log"

    run_data_understanding(args.input_dir, args.output, log_path, args.verbose)


if __name__ == "__main__":
    main()
