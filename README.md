# KEPL Inventory Forecast

Offline inventory forecasting and analytics workbench built with Rust, Python, PySide6, Plotly, Polars, DuckDB, PyArrow, and PyO3.

The platform ingests inventory and demand data, generates forecasts and analytical insights, exports a reusable Excel workbook, and provides interactive dashboards for business users. Forecasting and analytics are executed once per dataset and persisted for future reuse.

---

# Objectives

* Generate reliable inventory forecasts.
* Calculate operational and financial metrics.
* Classify inventory using ABC, XYZ, and risk models.
* Export reusable analytical workbooks.
* Load previously generated workbooks without recomputation.
* Provide responsive dashboards for business users.
* Operate fully offline.
* Maintain strong engineering, testing, security, and reproducibility standards.

---

# Core Principles

* Keep the design simple.
* Keep business logic isolated from presentation logic.
* Keep file I/O isolated from business logic.
* Treat all external inputs as untrusted.
* Treat Excel as a persistence and interchange format.
* Use cached datasets for dashboard operations.
* Run forecasting exactly once per dataset.
* Prefer explicit types over dynamic behavior.
* Prefer composition over inheritance.
* Measure before optimizing.
* Optimize only validated bottlenecks.

---

# Architecture Overview

```text
Raw Input Data
        │
        ▼
Validation Layer
        │
        ▼
Rust Engine
        │
        ├── Ingestion
        ├── Forecasting
        ├── Analytics
        ├── Financial Analysis
        ├── Classification
        └── Export Preparation
        │
        ▼
Excel Workbook
        │
        ├── Metadata
        ├── Forecasts
        ├── Analytics
        ├── Financials
        ├── Classifications
        └── Dashboard Cache
        │
        ▼
Python Application
        │
        ├── PySide6
        ├── Polars
        ├── DuckDB
        └── Plotly
        │
        ▼
Interactive Dashboards
```

---

# Technology Stack

## Rust

Responsible for:

* Data ingestion
* Forecasting
* Analytics
* Financial calculations
* Inventory classifications
* Validation
* Export preparation

### Key Libraries

* PyO3
* Polars
* Chrono
* RustDecimal
* Serde

---

## Python

Responsible for:

* Application orchestration
* State management
* Workbook management
* Dashboard management

### Key Libraries

* PySide6
* Plotly
* Polars
* DuckDB
* OpenPyXL
* Pydantic

---

# Forecasting

Implement:

* Random Forest Forecasting
* General Linear Model Forecasting
* Teunter-Syntetos-Babai Forecasting

Support:

* Configurable forecast horizons
* Forecast confidence metrics
* Model performance metrics
* Historical comparisons

---

# Analytics

Calculate:

* Trend metrics
* Seasonality metrics
* Demand variability metrics
* Inventory KPIs
* Operational KPIs
* Business KPIs

---

# Classification

Generate:

* ABC Classification
* XYZ Classification
* ABC-XYZ Classification
* Risk Classification

---

# Financial Analysis

Calculate:

* Inventory value
* Carrying cost
* Inventory turnover
* Stockout exposure
* Excess inventory exposure
* Forecast financial impact

Financial values must use deterministic decimal arithmetic or fixed-point representations.

---

# Workbook Workflow

## First Execution

```text
Raw Dataset
    │
    ▼
Run Forecasting
    │
    ▼
Generate Analytics
    │
    ▼
Export Workbook
    │
    ▼
Open Dashboard
```

---

## Subsequent Executions

```text
Existing Workbook
    │
    ▼
Validate Workbook
    │
    ▼
Load Dashboard Cache
    │
    ▼
Open Dashboard
```

No forecasting or analytics are executed during workbook reuse.

---

# Workbook Structure

## Metadata

Stores:

* Application version
* Workbook schema version
* Generation timestamp
* Runtime statistics
* Source file metadata
* Source file hash
* Output hash

---

## Forecasts

Stores:

* Historical demand
* Forecast values
* Forecast metrics
* Confidence information

---

## Analytics

Stores:

* Trend metrics
* Seasonality metrics
* Demand metrics
* Operational metrics

---

## Financials

Stores:

* Inventory metrics
* Financial metrics
* Risk metrics

---

## Classifications

Stores:

* ABC classifications
* XYZ classifications
* Combined classifications

---

## Dashboard Cache

Stores:

* Precomputed aggregations
* Dashboard summaries
* Chart-ready datasets
* Filter-ready datasets

The dashboard cache serves as the primary dashboard data source.

---

# Dashboard Features

Provide:

* Executive Summary Dashboard
* Forecast Dashboard
* Financial Dashboard
* Classification Dashboard
* Operational Dashboard

Support:

* Interactive filtering
* Interactive charts
* Zooming
* Panning
* Tooltips
* Exportable visualizations

---

# Data Management

## Persistence

Excel workbooks serve as the canonical persistence and interchange format.

---

## In-Memory Analytics

Polars owns:

* In-memory analytical datasets
* Filtering operations
* Aggregations

---

## Analytical Querying

DuckDB owns:

* Complex analytical queries
* Large dataset operations

---

## Dashboard Operations

Dashboard interactions operate exclusively on cached in-memory datasets.

Dashboard interactions never:

* Re-run forecasting
* Re-run analytics
* Re-read workbook files

---

# Performance Principles

* Run forecasting once per dataset.
* Load workbooks once per session.
* Cache dashboard datasets in memory.
* Minimize Rust-Python boundary crossings.
* Minimize memory copies.
* Avoid unnecessary dataframe reconstruction.
* Avoid repeated Excel reads.
* Profile before optimizing.

---

# Security Principles

* Treat all external inputs as untrusted.
* Validate all workbook schemas.
* Validate all user inputs.
* Reject unsupported workbook versions.
* Restrict file operations to approved locations.
* Prevent path traversal.
* Prevent UNC path abuse.
* Prevent workbook tampering.
* Prevent formula injection.
* Prevent query injection.
* Prevent renderer resource exhaustion.
* Audit Rust-Python boundaries.
* Protect data integrity.

Refer to `THREAT_MODEL.md` and `SECURITY_REQUIREMENTS.md` for full security controls.

---

# Environment Management

The project standardizes on uv.

Use uv for:

* Virtual environments
* Dependency management
* Dependency locking
* Tool execution

All developers must use the committed `uv.lock` file.

Install dependencies:

```bash
uv sync
```

Run development tooling:

```bash
uv run pytest
uv run mypy .
uv run ruff check .
uv run ruff format .
```

---

# Code Quality

## Python

Use:

* Ruff
* PyTest
* MyPy
* Pydantic

---

## Rust

Use:

* cargo fmt
* Clippy
* cargo test
* cargo audit
* cargo deny
* Criterion

---

# Testing

Test:

* Forecasting
* Analytics
* Financial calculations
* Classifications
* Workbook generation
* Workbook loading
* Rust-Python integration
* Dashboard workflows
* Security controls
* Performance constraints

---

# Reproducibility

Python reproducibility:

```text
uv.lock
```

Rust reproducibility:

```text
cargo.lock
```

Environment recreation:

```bash
uv sync
cargo build
```

All dependency changes must be committed through lockfile updates.

---

# Packaging

Provide:

* Offline desktop application
* Windows deployment
* One-click launch
* Bundled dependencies

Require:

* No terminal usage
* No internet connection

---

# Documentation

The project documentation set consists of:

```text
README.md
PROJECT_CONSTITUTION.md
ARCHITECTURE.md
THREAT_MODEL.md
SECURITY_REQUIREMENTS.md
ADR/
WORKBOOK_SCHEMA.md
API_CONTRACT.md
DOMAIN_MODEL.md
PERFORMANCE_BUDGET.md
TEST_PLAN.md
CODING_STANDARDS.md
DEPENDENCY_POLICY.md
ROADMAP.md
```

---

# Status

KEPL Inventory Forecast is designed as a reusable inventory forecasting and analytics platform that prioritizes correctness, maintainability, security, reproducibility, and operational efficiency.
