# Project Constitution

## Purpose

KEPL Inventory Forecast is an offline inventory forecasting and analytics platform designed for repeatable, auditable, and reproducible business decision support.

---

## Core Rules

### Rule 1

Rust owns business logic.

Rust is responsible for:

* Forecasting
* Analytics
* Financial calculations
* Classification
* Validation

Business logic must not be implemented in the UI layer.

---

### Rule 2

Python owns presentation.

Python is responsible for:

* Application orchestration
* State management
* Workbook coordination
* Visualization

Python must not contain forecasting or financial calculation logic.

---

### Rule 3

Excel owns persistence.

Excel workbooks are the canonical persisted representation of engine outputs.

Excel is not a database.

---

### Rule 4

Dashboards never perform forecasting.

Dashboards may:

* Filter
* Aggregate cached data
* Visualize

Dashboards must never:

* Re-run forecasts
* Re-run analytics
* Recompute classifications

---

### Rule 5

Forecasting executes once per dataset.

Expensive computations must be persisted and reused.

---

### Rule 6

All external inputs are untrusted.

Validate:

* Files
* Workbook contents
* Metadata
* User input

before processing.

---

### Rule 7

Type safety is mandatory.

Use:

* Rust types
* Pydantic models
* MyPy validation

Avoid untyped interfaces.

---

### Rule 8

Environment reproducibility is mandatory.

Python dependencies are managed through:

* uv
* uv.lock

Rust dependencies are managed through:

* Cargo
* Cargo.lock

---

### Rule 9

Measure before optimizing.

Optimize only validated bottlenecks.

---

### Rule 10

Documentation must reflect implementation.

When architecture changes, documentation must be updated.
