# Internal API Contract

There is no FFI in this build, so "API contract" means the boundaries between
internal layers: the signatures other layers may depend on, and the invariants each
layer guarantees. These are stable. Breaking one requires updating this document in
the same commit and, if it changes output, bumping the workbook schema version.

---

## Design Rules

- Every public function is fully type-annotated and `mypy --strict` clean.
- Data crossing a layer boundary is a Pydantic model or a Polars frame whose schema
  (column names + dtypes) is documented in this file or `WORKBOOK_SCHEMA.md`.
- Functions in `engine` and `viz` are pure: same input → same output, no I/O.
- Errors raised across a boundary are subclasses of `opstools.inventory_forecast.domain.errors.InventoryForecastError`.
- Inputs are validated at the ingestion boundary; engine functions assume clean
  frames and state that assumption in their docstrings.

---

## `domain` — shared by all layers

```python
class SourceKind(StrEnum):
    POV = "pov"; GRN = "grn"; PV = "pv"; CLOSING_STOCK = "closing_stock"

class AbcClass(StrEnum):
    A = "A"; B = "B"; C = "C"

class SbcClass(StrEnum):
    SMOOTH = "smooth"; ERRATIC = "erratic"
    INTERMITTENT = "intermittent"; LUMPY = "lumpy"

class InventoryForecastError(Exception):
    """Base for all domain errors."""

class SchemaError(InventoryForecastError):          # missing/unrecognized columns, no header found
class ValidationError(InventoryForecastError):      # bad values: negative qty/price/amount, empty supplier
class WorkbookVersionError(InventoryForecastError): # workbook schema version unsupported
class ForecastError(InventoryForecastError):        # forecasting failed for a series
```

Canonical ingested-frame schema (the contract every `read_source` output meets):

| Column     | Dtype       | Notes                                   |
| ---------- | ----------- | --------------------------------------- |
| `date`     | `Date`      | parsed; null only where source allows   |
| `supplier` | `Utf8`      | forward-filled, parenthetical-normalized|
| `item`     | `Utf8`      | non-empty                               |
| `qty`      | `Float64`   | ≥ 0                                     |
| `unit`     | `Utf8`      | may be empty for Closing Stock          |
| `price`    | `Decimal`   | ≥ 0                                     |
| `amount`   | `Decimal`   | ≥ 0                                     |

---

## `ingestion`

```python
def read_source(path: Path, kind: SourceKind) -> pl.LazyFrame:
    """Read a raw ERP export into a normalized, validated LazyFrame.

    Guarantees on the returned frame: canonical column names and dtypes per the
    domain schema above; supplier forward-filled and normalized; date is a Polars
    Date; qty/price/amount non-negative.

    Raises:
        SchemaError: header row not found, or a required column is missing.
        ValidationError: a value violates a domain constraint.
    """
```

---

## `engine` — representative signatures

```python
def reconstruct_demand(grn: pl.LazyFrame, pv: pl.LazyFrame,
                       closing: pl.LazyFrame) -> pl.LazyFrame:
    """Reconstruct a chronological per-item demand series from receipts,
    purchases, and stock snapshots. Output: [supplier, item, period, demand]."""

def classify_sbc(demand: pl.LazyFrame) -> pl.LazyFrame:
    """Syntetos–Boylan classification. Adds [adi, cv_squared, sbc_class] per item.
    Thresholds: ADI=1.32, CV²=0.49."""

def compute_lead_time(pov: pl.LazyFrame, grn: pl.LazyFrame) -> pl.LazyFrame:
    """FIFO match orders to receipts per (supplier, item), oldest order first,
    supporting partial deliveries. Output adds [order_date, delivery_date,
    lead_time_days]. Dates are parsed locally to Date to avoid dtype drift."""

def build_pending_deliveries(matched: pl.LazyFrame) -> pl.LazyFrame:
    """Rows where ordered_qty > delivered_qty for a matched relationship."""

def forecast_demand(demand: pl.LazyFrame, sbc: pl.LazyFrame,
                    horizon: int, cfg: Settings) -> pl.LazyFrame:
    """Route each series by SBC class — smooth/erratic→ETS or Theta,
    intermittent→TSB (benchmarked vs Croston-SBA), lumpy→TSB/Croston-SBA —
    each scored against Naive/SES baselines and selected by MASE/RMSSE. Output:
    [supplier, item, period, forecast, lower, upper, model, metric_*]."""

def build_reorder_recommendations(demand: pl.LazyFrame, lead_time: pl.LazyFrame,
                                  cfg: Settings) -> pl.LazyFrame:
    """reorder_point = (avg_monthly_demand * lead_time_months)
                       + (cfg.service_z * demand_std * sqrt(lead_time_months)).
    Falls back to cfg.default_lead_time_days when history is insufficient."""

def build_inventory_valuation(closing: pl.LazyFrame, pv: pl.LazyFrame,
                              snapshot_date: date) -> pl.LazyFrame:
    """Value inventory at snapshot_date using PV as the price source of truth.
    snapshot_date is passed explicitly — never read from a row-level Date column."""
```

The full builder set mirrors the workbook sheets: demand history, forecasts,
supplier partnerships, ABC, financial summary, inventory valuation, pending
deliveries, price variance, sourcing risk, fill rate, inventory health, reorder
recommendations.

---

## `workbook`

```python
def write_workbook(sheets: Mapping[str, pl.DataFrame], meta: WorkbookMeta,
                   path: Path) -> None:
    """Write all sheets plus a Metadata sheet in one pass. Money columns written
    as Decimal-formatted; cells sanitized against formula injection."""

def read_workbook(path: Path) -> LoadedWorkbook:
    """Validate workbook schema version, then load every sheet as a Polars frame.
    Raises WorkbookVersionError on mismatch."""
```

`WorkbookMeta` carries: application version, workbook schema version, generation
timestamp, source-file hashes, output hash, and runtime statistics. Sheet names and
columns are specified in `WORKBOOK_SCHEMA.md`.

---

## `services`

```python
def run_pipeline(sources: SourceSet, cfg: Settings, out: Path,
                 progress: Callable[[Stage, float], None]) -> Path:
    """Raw files → workbook on disk. `progress(stage, fraction)` must be safe to
    call from a worker thread. Returns the written workbook path."""

def load_dashboard_state(workbook: Path) -> AppState:
    """Workbook → immutable in-memory state for the dashboard. Read-only; never
    triggers recomputation."""
```

---

## `viz`

```python
def executive_overview(cache: DashboardCache) -> plotly.graph_objects.Figure: ...
def forecast_vs_history(cache: DashboardCache, item_key: str) -> Figure: ...
```

Every viz function takes cached frames and returns a Plotly `Figure`. No side
effects, no Qt imports.

---

## Versioning and Stability

The workbook schema and this contract are versioned together. A breaking change
bumps the workbook schema version and ships migration notes. Additive changes
(new sheet, new optional column) are backward-compatible and do not bump the major
version.