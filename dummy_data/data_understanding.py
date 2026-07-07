import argparse
import json
import logging
import sys
from pathlib import Path

import polars as pl
import xlsxwriter


# --- Core Definitions ---
class SourceKind:
    POV = "POV"
    GRN = "GRN"
    PV = "PV"
    STOCK = "CLOSING_STOCK"


EXCEPTIONS_SCHEMA = {
    "File Path": pl.Utf8,
    "Sheet and Row": pl.Utf8,
    "Reason": pl.Utf8,
    "Raw Data": pl.Utf8,
}


# --- Observability ---
def setup_logger(output_path: Path) -> logging.Logger:
    """Configures persistent file-level logging and console output."""
    logger = logging.getLogger("data_understanding")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(module)s:%(funcName)s:%(lineno)d] - %(message)s"
    )

    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File Handler
    log_file = output_path.parent / "pipeline_trace.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


# --- File Discovery ---
def discover_files(input_dir: Path, logger: logging.Logger) -> dict[str, list[Path]]:
    """Recursively scans the input directory for recognized ERP source files."""
    files = {
        SourceKind.POV: [],
        SourceKind.GRN: [],
        SourceKind.PV: [],
        SourceKind.STOCK: [],
    }

    if not input_dir.exists() or not input_dir.is_dir():
        logger.error(f"Input directory not found: {input_dir}")
        return files

    for path in input_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in [".csv", ".xlsx", ".xls"]:
            name = path.name.lower()
            if "pov" in name:
                files[SourceKind.POV].append(path)
            elif "grn" in name:
                files[SourceKind.GRN].append(path)
            elif "pv" in name:
                files[SourceKind.PV].append(path)
            elif "stock" in name:
                files[SourceKind.STOCK].append(path)

    total = sum(len(v) for v in files.values())
    logger.info(f"Discovered {total} recognized source files in {input_dir}")
    return files


# --- Ingestion & Validation ---
def ingest_file(
    path: Path, kind: str, logger: logging.Logger
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Reads a source file, applies basic mapping, and separates data faults into an exceptions frame."""
    logger.debug(f"Ingesting {path.name} as {kind}")
    try:
        if path.suffix.lower() == ".csv":
            df = pl.read_csv(
                path, infer_schema_length=10000, null_values=["NA", "N/A", ""]
            )
        else:
            df = pl.read_excel(path)
    except Exception as e:
        logger.error(f"System Fault reading {path.name}: {e!s}")
        return pl.DataFrame(), pl.DataFrame(schema=EXCEPTIONS_SCHEMA)

    # Standardize headers (ERP mapping)
    rename_map = {
        "Particulars": "Supplier_Name",
        "Item Details": "Item_Code",
        "Vch/Bill No": "Vch_No",
        "Qty.": "Qty",
    }

    for old_col, new_col in rename_map.items():
        if old_col in df.columns:
            df = df.rename({old_col: new_col})

    required = ["Date", "Supplier_Name", "Item_Code", "Qty", "Price", "Amount"]
    missing = [col for col in required if col not in df.columns]

    if missing:
        logger.warning(
            f"{path.name} is missing required columns: {missing}. Skipping file."
        )
        return pl.DataFrame(), pl.DataFrame(schema=EXCEPTIONS_SCHEMA)

    df = df.with_columns(pl.lit(path.name).alias("__file_name"))
    df = df.with_row_index("__row_number")

    # --- Error-Collecting Validation ---
    exceptions = []
    valid_indices = []

    for row in df.iter_rows(named=True):
        row_num = row["__row_number"] + 2  # Excel 1-indexing + header
        float(row.get("Qty", 0) or 0)
        price = float(row.get("Price", 0) or 0)

        is_valid = True
        reason = ""

        # Rule: Price cannot be negative. (Qty CAN be negative for stock desyncs)
        if price < 0:
            is_valid = False
            reason = f"Negative value '{price}' in Price"

        if is_valid:
            valid_indices.append(row["__row_number"])
        else:
            exceptions.append(
                {
                    "File Path": path.name,
                    "Sheet and Row": f"Sheet1: Row {row_num}",
                    "Reason": reason,
                    "Raw Data": str(row),
                }
            )

    exc_df = (
        pl.DataFrame(exceptions, schema=EXCEPTIONS_SCHEMA)
        if exceptions
        else pl.DataFrame(schema=EXCEPTIONS_SCHEMA)
    )

    if valid_indices:
        valid_df = df.filter(pl.col("__row_number").is_in(valid_indices))
    else:
        valid_df = df.clear()

    # Text Normalization on valid data
    valid_df = valid_df.with_columns(
        [
            pl.col("Supplier_Name").str.strip_chars().str.to_uppercase(),
            pl.col("Item_Code").str.strip_chars().str.to_uppercase(),
        ]
    )

    return valid_df.drop(["__file_name", "__row_number"]), exc_df


# --- Logic & Auditing ---
def _audit_lead_times(
    lead_time_df: pl.DataFrame, ref_json_path: Path, logger: logging.Logger
) -> pl.DataFrame:
    """Reverse-engineers the calculated lead times and cross-references them against
    the deterministic ledger generated by the dummy data engine.
    """
    if not ref_json_path.exists():
        logger.info(
            f"No reference JSON found at {ref_json_path}. Skipping dummy lead time audit."
        )
        return pl.DataFrame(schema=EXCEPTIONS_SCHEMA)

    logger.info("Auditing calculated lead times against reference JSON baseline...")
    with open(ref_json_path) as f:
        reference_data = json.load(f)

    audit_exceptions = []

    for row in lead_time_df.iter_rows(named=True):
        supplier = row["Supplier_Name"]
        item = row["Item_Code"]
        calc_lt = row["Avg_Lead_Time_Days"]

        key = f"{supplier}_{item}"

        if key in reference_data:
            expected_lt = float(reference_data[key])
            # We enforce exact precision since dummy lead times are strict deterministic integers
            if abs(calc_lt - expected_lt) > 0.01:
                audit_exceptions.append(
                    {
                        "File Path": ref_json_path.name,
                        "Sheet and Row": "Lead_Time_Analysis (Engine Output)",
                        "Reason": f"Audit Failure: Expected {expected_lt} days, Engine computed {calc_lt} days.",
                        "Raw Data": f"Supplier: {supplier} | Item: {item}",
                    }
                )
        else:
            audit_exceptions.append(
                {
                    "File Path": ref_json_path.name,
                    "Sheet and Row": "Lead_Time_Analysis (Engine Output)",
                    "Reason": "Ghost Entity: Engine computed a lead time for a pair that does not exist in the reference JSON.",
                    "Raw Data": f"Supplier: {supplier} | Item: {item}",
                }
            )

    # Validate that we didn't miss any pairs that *should* have been caught by the engine
    computed_keys = {
        f"{r['Supplier_Name']}_{r['Item_Code']}"
        for r in lead_time_df.iter_rows(named=True)
    }
    for ref_key, expected_lt in reference_data.items():
        if ref_key not in computed_keys:
            supplier, item = ref_key.split("_", 1)
            audit_exceptions.append(
                {
                    "File Path": ref_json_path.name,
                    "Sheet and Row": "Reference JSON Baseline",
                    "Reason": f"Data Drop: Engine failed to compute a lead time for this pair. Expected {expected_lt} days.",
                    "Raw Data": f"Supplier: {supplier} | Item: {item}",
                }
            )

    if audit_exceptions:
        logger.warning(
            f"Lead Time Audit complete: Found {len(audit_exceptions)} engine discrepancies."
        )
    else:
        logger.info(
            "Lead Time Audit complete: Engine perfectly reconstructed 100% of reference lead times."
        )

    return pl.DataFrame(audit_exceptions, schema=EXCEPTIONS_SCHEMA)


# --- Engine Computations ---
def build_analytics(
    data: dict[str, pl.DataFrame], reference_json: Path, logger: logging.Logger
) -> tuple[dict[str, pl.DataFrame], pl.DataFrame]:
    """Computes all required diagnostic dataframes and runs the reference audit."""
    sheets = {}

    # 1. Catalog
    pv_df = data.get(SourceKind.PV, pl.DataFrame())
    if not pv_df.is_empty():
        sheets["Master_Catalog"] = (
            pv_df.select(["Supplier_Name", "Item_Code"])
            .unique()
            .sort(["Supplier_Name", "Item_Code"])
        )
    else:
        sheets["Master_Catalog"] = pl.DataFrame()

    # 2. Lifecycle & Lead Times
    pov_df = data.get(SourceKind.POV, pl.DataFrame())
    grn_df = data.get(SourceKind.GRN, pl.DataFrame())

    audit_exceptions_df = pl.DataFrame(schema=EXCEPTIONS_SCHEMA)

    if not pv_df.is_empty() and not pov_df.is_empty() and not grn_df.is_empty():
        # Clean schemas for joining
        pv_clean = pv_df.select(
            [
                pl.col("Date").alias("PV_Date"),
                pl.col("Supplier_Name"),
                pl.col("Item_Code"),
                pl.col("Qty").alias("PV_Qty"),
                pl.col("Amount").alias("PV_Amount"),
            ]
        )
        grn_clean = grn_df.select(
            [
                pl.col("Date").alias("GRN_Date"),
                pl.col("Supplier_Name"),
                pl.col("Item_Code"),
            ]
        )
        pov_clean = pov_df.select(
            [
                pl.col("Date").alias("POV_Date"),
                pl.col("Supplier_Name"),
                pl.col("Item_Code"),
            ]
        )

        # Link chronologically (In dummy data, GRN date = PV date. POV date = GRN - Lead Time)
        lifecycle = pv_clean.join(
            grn_clean, on=["Supplier_Name", "Item_Code"], how="left"
        )
        lifecycle = lifecycle.join(
            pov_clean, on=["Supplier_Name", "Item_Code"], how="left"
        )

        # Physical Constraints: Drop permutations where POV happened AFTER GRN
        lifecycle = lifecycle.filter(
            (pl.col("POV_Date") <= pl.col("GRN_Date"))
            & (pl.col("GRN_Date") <= pl.col("PV_Date"))
        ).with_columns(
            (pl.col("GRN_Date") - pl.col("POV_Date"))
            .dt.total_days()
            .alias("Lead_Time_Days")
        )

        # Deduplicate legitimate cycles
        lifecycle = lifecycle.unique(
            subset=["Supplier_Name", "Item_Code", "POV_Date", "GRN_Date", "PV_Date"]
        )

        sheets["Procurement_Lifecycle"] = lifecycle.head(
            100
        )  # Truncate for readability

        # Aggregate Lead Times
        lt_analysis = (
            lifecycle.group_by(["Supplier_Name", "Item_Code"])
            .agg(
                [
                    pl.col("Lead_Time_Days")
                    .mean()
                    .round(2)
                    .alias("Avg_Lead_Time_Days"),
                    pl.len().alias("Completed_Cycles"),
                ]
            )
            .sort(["Supplier_Name", "Item_Code"])
        )

        sheets["Lead_Time_Analysis"] = lt_analysis

        # Execute Audit!
        audit_exceptions_df = _audit_lead_times(lt_analysis, reference_json, logger)

    else:
        sheets["Procurement_Lifecycle"] = pl.DataFrame()
        sheets["Lead_Time_Analysis"] = pl.DataFrame()

    # 3. Baseline Inventory (Classification Simulation)
    stock_df = data.get(SourceKind.STOCK, pl.DataFrame())
    if not stock_df.is_empty() and not pv_df.is_empty():
        # Define Universe
        universe = pv_df.group_by("Item_Code").agg(
            pl.col("Amount").sum().alias("Total_Spend")
        )
        universe = universe.sort("Total_Spend", descending=True)

        # Pareto Distribution
        universe = universe.with_columns(
            (pl.col("Total_Spend").cum_sum() / pl.col("Total_Spend").sum()).alias(
                "Cum_Pct"
            )
        ).with_columns(
            pl.when(pl.col("Cum_Pct") <= 0.80)
            .then(pl.lit("A"))
            .when(pl.col("Cum_Pct") <= 0.95)
            .then(pl.lit("B"))
            .otherwise(pl.lit("C"))
            .alias("ABC_Class")
        )

        # Map stock
        stock_agg = stock_df.group_by("Item_Code").agg(
            pl.col("Qty").sum().alias("Physical_Stock")
        )
        mapped_stock = stock_agg.join(
            universe.select(["Item_Code", "ABC_Class"]), on="Item_Code", how="left"
        )

        mapped_stock = mapped_stock.with_columns(
            pl.col("ABC_Class").fill_null("UNCLASSIFIED (Dead Stock)")
        )

        metrics = (
            mapped_stock.group_by("ABC_Class")
            .agg(
                [
                    pl.len().alias("Unique_SKUs"),
                    pl.col("Physical_Stock").sum().alias("Total_Units"),
                ]
            )
            .sort("ABC_Class")
        )

        sheets["Baseline_Metrics"] = metrics
    else:
        sheets["Baseline_Metrics"] = pl.DataFrame()

    return sheets, audit_exceptions_df


# --- Workbook Writer ---
def write_workbook(
    output_path: Path,
    sheets: dict[str, pl.DataFrame],
    exceptions_df: pl.DataFrame,
    logger: logging.Logger,
) -> None:
    """Writes formatting-aware data to the final Excel workbook."""
    logger.info(f"Writing diagnostic workbook to {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with xlsxwriter.Workbook(str(output_path)) as workbook:
        header_format = workbook.add_format(
            {"bold": True, "bg_color": "#D9D9D9", "border": 1}
        )
        num_format = workbook.add_format({"num_format": "#,##0.00"})
        date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})
        error_format = workbook.add_format(
            {"bg_color": "#FFC7CE", "font_color": "#9C0006"}
        )

        # Write Analytics Sheets
        for sheet_name, df in sheets.items():
            worksheet = workbook.add_worksheet(sheet_name)
            if df.is_empty():
                worksheet.write(0, 0, "No data generated for this view.")
                continue

            # Headers
            for col_num, col_name in enumerate(df.columns):
                worksheet.write(0, col_num, col_name, header_format)
                worksheet.set_column(col_num, col_num, max(len(col_name) + 5, 15))

            # Data
            for row_num, row_data in enumerate(df.iter_rows()):
                for col_num, value in enumerate(row_data):
                    col_name = df.columns[col_num]

                    if "Date" in col_name and value is not None:
                        worksheet.write_datetime(
                            row_num + 1, col_num, value, date_format
                        )
                    elif isinstance(value, (int, float)):
                        worksheet.write_number(row_num + 1, col_num, value, num_format)
                    else:
                        worksheet.write(
                            row_num + 1,
                            col_num,
                            str(value) if value is not None else "",
                        )

        # Write Exceptions Sheet
        ws_exc = workbook.add_worksheet("Ingestion_Exceptions")
        if exceptions_df.is_empty():
            ws_exc.write(0, 0, "No exceptions found.")
        else:
            for col_num, col_name in enumerate(exceptions_df.columns):
                ws_exc.write(0, col_num, col_name, header_format)
                ws_exc.set_column(col_num, col_num, 25)

            for row_num, row_data in enumerate(
                exceptions_df.head(500).iter_rows()
            ):  # Cap at 500 for readability
                for col_num, value in enumerate(row_data):
                    if "Reason" in exceptions_df.columns[col_num]:
                        ws_exc.write(row_num + 1, col_num, str(value), error_format)
                    else:
                        ws_exc.write(row_num + 1, col_num, str(value))


def main() -> None:
    parser = argparse.ArgumentParser(description="KEPL Data Understanding Pipeline")
    parser.add_argument(
        "-i",
        "--input-dir",
        type=str,
        required=True,
        help="Directory containing ERP data",
    )
    parser.add_argument(
        "-o", "--output", type=str, required=True, help="Path for output Excel workbook"
    )
    parser.add_argument(
        "-r",
        "--reference-json",
        type=str,
        default="dummy_data/reference_lead_times.json",
        help="Path to reference dummy lead times for auditing",
    )
    args = parser.parse_args()

    input_path = Path(args.input_dir)
    output_path = Path(args.output)
    reference_path = Path(args.reference_json)

    logger = setup_logger(output_path)
    logger.info("Initializing Data Understanding Phase...")

    source_map = discover_files(input_path, logger)

    # 1. Ingestion Phase
    ingested_data = {}
    all_exceptions = []

    for kind, paths in source_map.items():
        dfs = []
        for path in paths:
            valid_df, exc_df = ingest_file(path, kind, logger)
            if not valid_df.is_empty():
                dfs.append(valid_df)
            if not exc_df.is_empty():
                all_exceptions.append(exc_df)

        if dfs:
            ingested_data[kind] = pl.concat(dfs, how="vertical_relaxed")
        else:
            ingested_data[kind] = pl.DataFrame()

    # 2. Analytics & Audit Engine
    sheets, audit_exceptions = build_analytics(ingested_data, reference_path, logger)

    if not audit_exceptions.is_empty():
        all_exceptions.append(audit_exceptions)

    global_exceptions = (
        pl.concat(all_exceptions, how="vertical_relaxed")
        if all_exceptions
        else pl.DataFrame(schema=EXCEPTIONS_SCHEMA)
    )

    # 3. Workbook Construction
    write_workbook(output_path, sheets, global_exceptions, logger)
    logger.info("Data Understanding pipeline complete.")


if __name__ == "__main__":
    sys.exit(main())
