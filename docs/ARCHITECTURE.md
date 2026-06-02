# Architecture

## High-Level Architecture

```text
Raw Input
    ↓
Validation Layer
    ↓
Rust Engine
    ↓
Workbook Export
    ↓
Workbook Load
    ↓
Polars DataFrames
    ↓
Dashboard State
    ↓
Plotly Visualizations
```

---

## Layer Ownership

### Rust Engine

Owns:

* Ingestion
* Forecasting
* Analytics
* Financial calculations
* Classification
* Export preparation

Must not depend on:

* PySide6
* Plotly
* UI concepts

---

### Python Services

Own:

* Workflow orchestration
* State transitions
* Workbook coordination

Must not contain business logic.

---

### Repository Layer

Owns:

* Workbook loading
* Workbook saving
* Cache loading
* Metadata loading

Must not contain UI logic.

---

### Dashboard Layer

Owns:

* Visualization
* Filtering
* Navigation
* User interactions

Must not contain forecasting logic.

---

## Runtime Model

### First Execution

```text
Raw Dataset
    ↓
Forecasting
    ↓
Analytics
    ↓
Workbook Export
```

### Subsequent Execution

```text
Workbook
    ↓
Validation
    ↓
Cache Load
    ↓
Dashboard
```

No forecasting occurs during workbook reuse.

---

## Data Ownership

### Excel

Owns:

* Persistence
* Audit trail
* Distribution

### Polars

Owns:

* In-memory analytical state

### DuckDB

Owns:

* Analytical querying

### Plotly

Owns:

* Rendering

### PySide6

Owns:

* User interaction
* Application lifecycle
