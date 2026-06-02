# KEPL Inventory Forecaster

A native Rust + Python procurement analytics engine with a PySide6 desktop GUI.  
It ingests ERP exports (POV, GRN, PV, Stock), runs inventory math and demand forecasting fully in Rust, and renders interactive analysis dashboards in Qt.

---

## 1. Architecture

The project is split into three main layers.

- **Rust core (`coreengine`)**
    - Ingestion of `.xlsx` / `.csv` into strongly typed `TransactionRow` structures using `calamine` and `csv`.
    - Financial aggregation with strict `rust_decimal` fixed‑point math (no IEEE754 drift).
    - SBC (Syntetos–Boylan) classification (`Smooth`, `Erratic`, `Intermittent`, `Lumpy`) using ADI and \(CV^2\).
    - Forecasting engines:
        - Random Forest for **Smooth** series via `smartcore`.
        - GLM with IRLS for **Erratic** demand via `ndarray`.
        - TSB for **Intermittent/Lumpy** demand.
    - Inventory metrics: lead time, pending quantity, unordered quantity, trend factor derived from POV, GRN and stock snapshots.

- **Rust → Python bindings (`keplcore`)**
    - Exports a single FFI function `process_multiledger(pov_paths, grn_paths, stock_paths)` using `pyo3`.
    - Parallel ingestion and analytics with `rayon` inside `py.allow_threads`, returning a packed Python dictionary:
        - `abc_data`
        - `historical_data`
        - `supplier_data`
        - placeholders: `lead_time_data`, `top10_trends`, `sbc_data`.

- **Python GUI (`gui/`)**
    - PySide6 application with:
        - File selection and validation per dataset group (POV, GRN, PV, Stock) with per‑extension size caps.
        - Results view with tabs:
            - **Historical Data**
            - **Data Analyzed**
            - **Supplier Risk**
    - Matplotlib‑based dashboard widgets:
        - ABC Pareto chart (`ParetoChartWidget`).
        - Treemap of ABC classes (`TreemapChartWidget`).
        - Top‑10 SKU trends line chart (`Top10LineWidget`).
        - Forecast comparison (Historical vs RF/GLM/TSB).
        - Lead‑time box/whisker chart.
        - SBC scatter matrix and supplier clusters.

The GUI is launched via `gui.py` / `rungui.py` and imports the compiled `keplcore` extension.

---

## 2. Features

- **ERP‑friendly ingestion**
    - Handles padding and messy headers by normalizing column names, then dynamically mapping indices.
    - Supports `.xlsx`, `.xls`, `.csv` with configurable per‑file size limits.
    - Vendor deduplication to enforce consistent supplier keys.

- **Robust inventory analytics**
    - FIFO mapping of GRNs to POVs to estimate lead time.
    - Demand inferred from stock snapshots and GRNs across time.
    - Computed metrics per SKU: total demand, lead time days, pending quantity, unordered quantity, trend factor.

- **Forecasting**
    - Routing of each SKU’s demand history to the correct engine based on SBC category.
    - Random Forest, GLM‑IRLS and TSB engines, each returning forecast vectors plus error metrics.

- **Visual dashboards**
    - ABC Pareto bar + cumulative curve with configurable A/B/C thresholds.
    - Treemap for ABC class distribution.
    - Top‑10 SKU trend lines.
    - Forecast comparison chart overlaying RF/GLM/TSB.
    - Supplier risk clustering and SBC quadrant scatterplots.

---

## 3. Installation

### 3.1 Prerequisites

- Python 3.12 (to match `abi3-py312` build).
- Rust toolchain (edition 2021) with Cargo.
- `maturin` for building the Python extension:
  ```bash
  pip install maturin
  ```
- System packages for Qt and OpenGL (varies by OS).

### 3.2 Clone and setup

```bash
git clone <your-repo-url>
cd kepl-procurement-engine
```

Create and activate a virtualenv, then install Python dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

pip install -e .[dev]
```

Build and install the Rust core as a Python extension:

```bash
cd bindings
maturin develop --release
cd ..
```

This produces and installs the `keplcore` extension that the GUI imports.

---

## 4. Running the GUI

From the project root (with virtualenv active and extension built):

```bash
python gui.py
# or
python rungui.py
```

The application boots as **“KEPL Procurement Engine”** and opens the main window maximized.

**Workflow:**

1. In the **File Selection** view, attach:
    - Purchase Order Vouchers (POV)
    - Goods Received Notes (GRN)
    - Purchase Vouchers (PV)
    - Closing Stock snapshots
2. Click **Run Analysis**.
3. The Rust engine ingests the datasets, computes metrics and forecasts, and returns the structured payload.
4. The **Results Dashboard** updates with:
    - Historical transactional data
    - ABC / inventory analytics
    - Supplier risk indicators and clusters

---

## 5. Development

### 5.1 Rust core

- Core crate: `coreengine/Cargo.toml`.
- Bindings crate: `Chaudhary-procurement-engine.toml` / `keplcore`.

Useful commands:

```bash
# Run Rust tests
cargo test

# Build core engine only
cargo build --release -p coreengine
```

Key modules:

- `ingest.rs` – Excel/CSV parsing and transaction row normalization.
- `financials.rs` – Decimal aggregation and Pareto weights.
- `classifier.rs` – SBC metrics (ADI, CV²) and categorization.
- `forecaster/mod.rs` – routing + engines in `randomforest.rs`, `glm.rs`, `tsb.rs`.
- `analytics.rs` – inventory math (lead time, demand, trend).

### 5.2 Python GUI

Run tests and lint:

```bash
pytest
ruff check .
mypy .
```

GUI modules (examples):

- `selectionview.py` – file group widgets, file size limits per extension.
- `views/resultsview.py` – top‑level results tab widget.
- `charts/*.py` – specialized matplotlib widgets (Pareto, SBC matrix, supplier clusters, etc.).

---

## 6. Known limitations / current issues

- **Laggy GUI:**
    - Matplotlib rendering blocks the main thread when large datasets and multiple charts are refreshed at once.
    - State management is tightly coupled to view widgets, making incremental updates hard.

- **Data placeholders:**
    - Some dashboards currently rely on synthetic/random data where backend support is not yet wired (`top10_trends`, lead‑time categories, full SBC back‑prop to plots).

- **Adoption risk:**
    - Heavy native stack (Rust + pyo3 + maturin + PySide6 + matplotlib) requires more build tooling than typical internal Python dashboards.
