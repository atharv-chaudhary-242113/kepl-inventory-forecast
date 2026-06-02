# API Contract

## Design Rules

* All FFI boundaries are explicit.
* All public interfaces are typed.
* Panics must not cross the PyO3 boundary.
* All inputs are validated before engine execution.

---

## Python → Rust

### Forecast Request

```python
ForecastRequest(
    input_file: str,
    forecast_horizon: int,
    selected_models: list[str]
)
```

---

## Rust → Python

### Forecast Result

```rust
pub struct ForecastResult {
    pub forecasts: Vec<ForecastRecord>,
    pub metrics: ForecastMetrics,
    pub classifications: ClassificationSummary,
    pub financials: FinancialSummary,
}
```

---

## Error Contract

Rust errors must be converted into Python exceptions.

Internal Rust panics must be contained.

Public APIs must return structured error information.

---

## Stability Requirements

Workbook schemas are versioned.

Public API contracts are versioned.

Breaking changes require migration documentation.
