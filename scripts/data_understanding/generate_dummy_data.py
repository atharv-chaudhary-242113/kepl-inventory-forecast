import json
import os
from datetime import datetime, timedelta

import numpy as np
import polars as pl

# --- Configuration & Paths ---
BASE_DIR = "dummy_data"
PATHS = {
    "pov": os.path.join(BASE_DIR, "dummy_POVs"),
    "pv": os.path.join(BASE_DIR, "dummy_PVs"),
    "grn": os.path.join(BASE_DIR, "dummy_GRNSs"),
    "stock": os.path.join(BASE_DIR, "dummy_Closing-Stocks"),
}

# --- Domain Constants ---
ITEMS = [f"ITEM-{str(i).zfill(3)}" for i in range(1, 151)]
SUPPLIERS = [f"SUPPLIER-{chr(65 + i)}" for i in range(15)]
START_DATE = datetime(2024, 4, 1)
END_DATE = datetime(2026, 3, 31)


def _setup_directories() -> None:
    """Ensure all target directories exist."""
    for path in PATHS.values():
        os.makedirs(path, exist_ok=True)


def _generate_catalog_and_lead_times() -> tuple[pl.DataFrame, dict]:
    """Generates a deterministic catalog of Supplier-Item pairs with locked base prices
    and pre-planned lead times to allow reverse-engineering validation.
    """
    np.random.seed(42)
    records = []
    lead_times_dict = {}

    for item in ITEMS:
        # Assign 1 to 3 suppliers per item
        item_suppliers = np.random.choice(
            SUPPLIERS, size=np.random.randint(1, 4), replace=False
        )
        base_price = round(np.random.uniform(10.0, 5000.0), 2)

        for sup in item_suppliers:
            lead_time = int(np.random.randint(5, 45))
            lead_times_dict[f"{sup}_{item}"] = lead_time

            records.append(
                {
                    "Supplier Name": sup,
                    "Item Code": item,
                    "Base Price": base_price,
                    "Lead Time": lead_time,
                }
            )

    catalog_df = pl.DataFrame(records)

    # Save the reference dictionary for engine validation
    with open(os.path.join(BASE_DIR, "reference_lead_times.json"), "w") as f:
        json.dump(lead_times_dict, f, indent=4)

    return catalog_df, lead_times_dict


def _generate_pv_truth(
    catalog_df: pl.DataFrame, num_transactions: int = 5000
) -> pl.DataFrame:
    """Generates the absolute source of truth: Purchase Vouchers."""
    np.random.seed(100)

    # Randomly sample from our valid catalog pairs
    indices = np.random.randint(0, catalog_df.height, size=num_transactions)
    sampled_catalog = catalog_df[indices]

    # Generate random dates within the 2-year window
    date_range_days = (END_DATE - START_DATE).days
    random_days = np.random.randint(0, date_range_days, size=num_transactions)
    dates = [START_DATE + timedelta(days=int(d)) for d in random_days]

    # Generate variance in Qty and Price
    qtys = np.random.randint(10, 1000, size=num_transactions)
    price_variance = np.random.uniform(0.95, 1.05, size=num_transactions)  # 5% variance

    pv_df = (
        sampled_catalog.with_columns(
            [
                pl.Series("Date", dates),
                pl.Series("Qty.", qtys, dtype=pl.Float64),
                (pl.col("Base Price") * pl.Series("variance", price_variance))
                .round(2)
                .alias("Price"),
            ]
        )
        .with_columns((pl.col("Qty.") * pl.col("Price")).round(2).alias("Amount"))
        .sort("Date")
    )

    return pv_df.select(
        ["Date", "Supplier Name", "Item Code", "Qty.", "Price", "Amount", "Lead Time"]
    )


def _split_and_save_transactional_data(pv_df: pl.DataFrame) -> None:
    """Derives POV and GRN from the PV truth using pre-planned lead times,
    maps them to RAW ERP headers, splits them by financial year, and writes to disk.
    """
    # 1. Derive lifecycle dates
    lifecycle_df = pv_df.with_columns(
        [
            pl.col("Date").alias("PV_Date"),
            pl.col("Date").alias("GRN_Date"),
            (pl.col("Date") - pl.duration(days=pl.col("Lead Time"))).alias("POV_Date"),
        ]
    )

    # Split boundaries
    fy25_start = datetime(2024, 4, 1)
    fy26_start = datetime(2025, 4, 1)
    fy27_start = datetime(2026, 4, 1)

    datasets = {
        "pv": ("PV_Date", PATHS["pv"], "dummy_pv"),
        "grn": ("GRN_Date", PATHS["grn"], "dummy_grn"),
        "pov": ("POV_Date", PATHS["pov"], "dummy_pov"),
    }

    for _kind, (date_col, folder, prefix) in datasets.items():
        # Map specific lifecycle date to "Date" and add mandatory ERP schema columns
        export_df = lifecycle_df.with_columns(
            [
                pl.col(date_col).alias("Date"),
                pl.lit("NOS").alias("Unit"),
                pl.Series(
                    "Vch/Bill No",
                    [
                        f"{prefix.upper()}-{i + 10000}"
                        for i in range(lifecycle_df.height)
                    ],
                ),
            ]
        )

        # Rename internal identifiers to match raw ERP columns exactly
        export_df = export_df.rename(
            {"Supplier Name": "Particulars", "Item Code": "Item Details"}
        )

        # Order the schema precisely for the ingestion layer
        export_cols = [
            "Date",
            "Vch/Bill No",
            "Particulars",
            "Item Details",
            "Unit",
            "Qty.",
            "Price",
            "Amount",
        ]
        export_df = export_df.select(export_cols)

        # FY 2024-2025
        df_24_25 = export_df.filter(
            (pl.col("Date") >= fy25_start) & (pl.col("Date") < fy26_start)
        )
        df_24_25.write_excel(os.path.join(folder, f"{prefix}_2024-2025.xlsx"))

        # FY 2025-2026
        df_25_26 = export_df.filter(
            (pl.col("Date") >= fy26_start) & (pl.col("Date") < fy27_start)
        )
        df_25_26.write_excel(os.path.join(folder, f"{prefix}_2025-2026.xlsx"))


def _generate_closing_stock(pv_df: pl.DataFrame) -> None:
    """Generates closing stock for specific snapshot dates.
    Applies raw ERP schemas for Closing Stock specifically.
    """
    snapshot_dates = [
        ("01-April-2025", datetime(2025, 4, 1)),
        ("03-June-2025", datetime(2025, 6, 3)),
        ("05-August-2025", datetime(2025, 8, 5)),
    ]

    np.random.seed(200)

    for label, cutoff_date in snapshot_dates:
        # Calculate strictly historical purchases up to the cutoff date
        historical_purchases = pv_df.filter(pl.col("Date") <= cutoff_date)

        if historical_purchases.height == 0:
            continue

        # Aggregate total historical Qty and average Price per item
        stock_df = historical_purchases.group_by("Item Code").agg(
            [
                pl.col("Qty.").sum().alias("Total_Purchased_Qty"),
                pl.col("Price").mean().round(2).alias("Price"),
            ]
        )

        # Apply the 8% - 17% constraint
        multipliers = np.random.uniform(0.08, 0.17, size=stock_df.height)
        stock_df = stock_df.with_columns(
            [pl.Series("Multiplier", multipliers)]
        ).with_columns(
            (pl.col("Total_Purchased_Qty") * pl.col("Multiplier"))
            .round(0)
            .alias("Qty.")
        )

        # Drop 20% of items to simulate zero-stock
        mask = np.random.rand(stock_df.height) > 0.20
        stock_df = stock_df.filter(pl.Series(mask))

        # Rename and append columns to match ERP schema exactly
        final_stock = (
            stock_df.with_columns(
                [
                    (pl.col("Qty.") * pl.col("Price")).round(2).alias("Amount"),
                    pl.lit("NOS").alias("Unit"),
                ]
            )
            .rename({"Item Code": "Item Details"})
            .filter(pl.col("Qty.") > 0)
            .select(["Item Details", "Unit", "Qty.", "Price", "Amount"])
            .sort("Item Details")
        )

        filepath = os.path.join(PATHS["stock"], f"dummy_closing-stock_{label}.xlsx")
        final_stock.write_excel(filepath)


def main() -> None:
    print("Initializing dummy data generation...")
    _setup_directories()

    print("1. Generating Master Catalog & Lead Time Ledger...")
    catalog_df, _ = _generate_catalog_and_lead_times()

    print("2. Generating Purchase Vouchers (The Absolute Truth)...")
    pv_df = _generate_pv_truth(catalog_df, num_transactions=8000)

    print(
        "3. Reverse-engineering POV and GRN, formatting raw ERP headers, & Splitting by FY..."
    )
    _split_and_save_transactional_data(pv_df)

    print("4. Calculating Volumetric Closing Stocks with raw ERP headers...")
    _generate_closing_stock(pv_df)

    print(f"\nSuccess. All files written to '{BASE_DIR}'.")
    print(
        "The files now strictly adhere to the raw ERP schema required by your ingestion layer."
    )


if __name__ == "__main__":
    main()
