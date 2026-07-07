"""Management Visualization Dashboard Builder.

This script ingests the strictly reconciled Data Understanding workbook and
generates a standalone, interactive HTML dashboard using Plotly. It requires
zero server infrastructure to view and translates raw procurement and baseline
diagnostics into C-suite ready visual aggregates.
"""

import argparse
import logging
import sys
from pathlib import Path

import plotly.express as px
import polars as pl


def setup_observability(verbose: bool) -> logging.Logger:
    """Configure console observability for the dashboard builder."""
    logger = logging.getLogger("opstools.dashboard")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] - %(message)s", datefmt="%H:%M:%S"
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def build_inventory_donut(df: pl.DataFrame) -> str:
    """Generate a Donut chart of Baseline Inventory distributed by ABC Class."""
    if df.is_empty():
        return "<div>No Baseline Inventory data available.</div>"

    # CRITICAL FIX: Cast to Float to prevent Plotly from counting strings as 1
    df_clean = df.with_columns(
        pl.col("Total_Physical_Quantity").cast(pl.Float64, strict=False)
    ).to_pandas()

    fig = px.pie(
        df_clean,
        names="abc_class",
        values="Total_Physical_Quantity",
        hole=0.4,
        title="Physical Inventory Distribution by Value Class (ABC)",
        color="abc_class",
        color_discrete_map={
            "A": "#E74C3C",  # Red - High Value
            "B": "#F39C12",  # Orange - Medium Value
            "C": "#3498DB",  # Blue - Low Value
            "OTHER (No Purchase History)": "#95A5A6",  # Grey - Dead/Unclassified
        },
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(margin={"t": 40, "b": 0, "l": 0, "r": 0})

    return fig.to_html(full_html=False, include_plotlyjs=False)


def build_spend_trend(df: pl.DataFrame) -> str:
    """Generate a Bar chart tracking total monthly procurement spend."""
    if df.is_empty():
        return "<div>No Historical Demand data available.</div>"

    # CRITICAL FIX: Cast spend data to Float
    df_clean = df.with_columns(pl.col("Total_Spend").cast(pl.Float64, strict=False))

    monthly_spend = (
        df_clean.group_by("Demand_Month")
        .agg(pl.col("Total_Spend").sum())
        .sort("Demand_Month")
    ).to_pandas()

    fig = px.bar(
        monthly_spend,
        x="Demand_Month",
        y="Total_Spend",
        title="Historical Procurement Spend Over Time",
        labels={"Demand_Month": "Month", "Total_Spend": "Total Spend (Currency)"},
        color_discrete_sequence=["#2C3E50"],
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        yaxis={"tickformat": ",.0f"},
        margin={"t": 40, "b": 0, "l": 0, "r": 0},
    )

    return fig.to_html(full_html=False, include_plotlyjs=False)


def build_supplier_matrix(df: pl.DataFrame) -> str:
    """Generate a Scatter plot identifying high-risk vs reliable suppliers."""
    if df.is_empty():
        return "<div>No Lead Time data available.</div>"

    # CRITICAL FIX: Cast to Float to prevent continuous color scale JS crash
    df_clean = df.with_columns(
        [
            pl.col("Avg_Lead_Time_Days").cast(pl.Float64, strict=False),
            pl.col("Completed_Orders_Count").cast(pl.Float64, strict=False),
        ]
    )

    supplier_perf = (
        df_clean.group_by("supplier")
        .agg(
            pl.col("Avg_Lead_Time_Days").mean().round(1).alias("Mean_Lead_Time"),
            pl.col("Completed_Orders_Count").sum().alias("Total_Orders"),
        )
        .filter(pl.col("Total_Orders") > 0)
    ).to_pandas()

    fig = px.scatter(
        supplier_perf,
        x="Mean_Lead_Time",
        y="Total_Orders",
        hover_name="supplier",
        size="Total_Orders",
        title="Supplier Performance Matrix (Lead Time vs Order Volume)",
        labels={
            "Mean_Lead_Time": "Average Lead Time (Days) → [Lower is Better]",
            "Total_Orders": "Total Completed Orders → [Higher Dependency]",
        },
        color="Mean_Lead_Time",
        color_continuous_scale="RdYlGn_r",  # Green (Fast) to Red (Slow)
    )
    fig.update_layout(margin={"t": 40, "b": 0, "l": 0, "r": 0})

    return fig.to_html(full_html=False, include_plotlyjs=False)


def assemble_html_dashboard(
    donut_html: str, trend_html: str, matrix_html: str, output_file: Path
) -> None:
    """Wrap the generated Plotly divs in a styled, responsive CSS grid."""
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>KEPL Procurement & Inventory Insights</title>
        <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
        <style>
            :root {{
                --bg-color: #f4f7f6;
                --card-bg: #ffffff;
                --header-bg: #1a252f;
                --text-main: #333333;
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg-color);
                color: var(--text-main);
                margin: 0;
                padding: 20px;
            }}
            .header {{
                background-color: var(--header-bg);
                color: white;
                padding: 25px 30px;
                border-radius: 10px;
                margin-bottom: 25px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }}
            .header h1 {{ margin: 0 0 5px 0; font-size: 24px; }}
            .header p {{ margin: 0; color: #bdc3c7; font-size: 14px; }}

            .dashboard-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
            }}
            .card {{
                background: var(--card-bg);
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }}
            .full-width {{
                grid-column: span 2;
            }}

            @media (max-width: 1000px) {{
                .dashboard-grid {{ grid-template-columns: 1fr; }}
                .full-width {{ grid-column: span 1; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>KEPL Data Understanding Briefing</h1>
            <p>Interactive Management Dashboard • Automatically generated from ERP Ingestion Layer</p>
        </div>

        <div class="dashboard-grid">
            <div class="card">
                {donut_html}
            </div>
            <div class="card">
                {trend_html}
            </div>
            <div class="card full-width">
                {matrix_html}
            </div>
        </div>
    </body>
    </html>
    """  # noqa: E501

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_template)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Interactive Plotly Dashboard."
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        required=True,
        help="Path to the compiled data_understanding.xlsx file.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Path to save the resulting dashboard.html",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable stdout logging."
    )

    args = parser.parse_args()
    logger = setup_observability(args.verbose)

    if not args.file.exists():
        logger.error(f"Input workbook not found: {args.file}")
        sys.exit(1)

    logger.info(f"Reading diagnostic workbook: {args.file}")

    try:
        df_baseline = pl.read_excel(args.file, sheet_name="Baseline_Inventory_Metrics")
        df_demand = pl.read_excel(args.file, sheet_name="Historical_Demand")
        df_lead_time = pl.read_excel(args.file, sheet_name="Lead_Time_Analysis")
    except Exception as e:
        logger.error(f"Failed to read workbook sheets: {e}")
        sys.exit(1)

    logger.info("Building Top Left Panel: Baseline Inventory Distribution")
    donut_html = build_inventory_donut(df_baseline)

    logger.info("Building Top Right Panel: Historical Spend Trend")
    trend_html = build_spend_trend(df_demand)

    logger.info("Building Bottom Panel: Supplier Risk Matrix")
    matrix_html = build_supplier_matrix(df_lead_time)

    logger.info(f"Assembling interactive HTML payload to {args.output}")
    assemble_html_dashboard(donut_html, trend_html, matrix_html, args.output)

    logger.info("Success. Open the HTML file in any web browser to view the dashboard.")


if __name__ == "__main__":
    main()
