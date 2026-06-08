# DOMAIN_RULES.md

# Domain Rules Specification

## Purpose

This document defines the authoritative business rules governing procurement analytics, inventory analysis, forecasting, supplier intelligence, risk analysis, classification, and workbook generation.

Only rules documented here are considered authoritative.

Implementation must follow this specification.

---

# Business Context

The organization operates a procurement-driven inventory environment.

Inventory replenishment is primarily triggered by observed consumption and operational requirements rather than fixed inventory policies.

The system exists to:

* Analyze procurement behavior.
* Analyze supplier performance.
* Estimate demand.
* Forecast future demand.
* Analyze inventory risk.
* Support purchasing decisions.
* Support supplier selection decisions.

---

# Core Business Entities

## Supplier

A supplier is an external entity that provides inventory items.

Suppliers are identified through the `Particulars` field.

---

## Supplier Normalization

Supplier names must be normalized before analysis.

Branch information inside parentheses must be removed.

Examples:

```text
ABC Electricals (Noida)
ABC Electricals (Delhi)
ABC Electricals (Ghaziabad)
```

Normalize to:

```text
ABC Electricals
```

The normalized value becomes the canonical supplier identifier.

---

## Item

An item is identified using:

```text
Normalized Supplier
+
Item Details
```

The same item description may exist under multiple suppliers.

Such records represent independent supplier relationships.

---

# Procurement Lifecycle

## Purchase Order Voucher (POV)

Represents procurement intent.

Generated when inventory is ordered from a supplier.

Used for:

* Lead-time analysis
* Procurement history
* Pending delivery analysis
* Supplier performance analysis

---

## Goods Received Note (GRN)

Represents physical receipt of inventory.

Generated when inventory is delivered.

Used for:

* Delivery analysis
* Lead-time analysis
* Inventory movement analysis
* Supplier performance analysis

---

## Purchase Voucher (PV)

Represents finalized financial procurement transactions.

PV is the authoritative financial procurement source.

PV provides:

* Exact procurement price
* Unit information
* Cost information
* Freight information
* Finalized procurement value

When financial conflicts exist between:

```text
POV
GRN
PV
```

PV is considered the source of truth.

PV is used for:

* Spend analysis
* Inventory valuation
* Supplier expenditure analysis
* Freight analysis
* Financial reporting

---

## Closing Stock

Represents inventory quantities available at a specific date.

Closing stock files are inventory snapshots.

Used for:

* Inventory analysis
* Demand reconstruction
* Forecast preparation

---

# Lead-Time Rules

## Lead-Time Definition

Lead time is defined as:

```text
Lead Time =
Delivery Date − Order Date
```

Where:

```text
Order Date = POV Date
Delivery Date = GRN Date
```

---

## Matching Rules

POV and GRN matching requires:

* Same supplier
* Same item

Matching occurs chronologically.

---

## FIFO Matching

The oldest unmatched order must be matched first.

Matching follows a FIFO process.

---

## Partial Deliveries

Partial deliveries are valid.

A supplier may fulfill a single purchase order through multiple GRNs.

The system must support:

```text
One Order → Many Deliveries
Many Deliveries → One Order
```

---

# Pending Deliveries

A delivery is considered pending when:

```text
Ordered Quantity > Delivered Quantity
```

for a matched procurement relationship.

Pending deliveries contribute to supplier risk.

---

# Unordered Deliveries

An unordered delivery exists when inventory is received without a corresponding active order relationship.

Potential matching indicators include:

* Supplier similarity
* Item similarity
* Chronological proximity
* Price similarity

These events must be recorded for analysis.

---

# Supplier Partnership Detection

Suppliers may be flagged as suspected partners when:

* Pending deliveries exist.
* Unordered deliveries exist.
* Pricing remains similar.
* Procurement chronology remains consistent.

and

```text
Observed Frequency ≥ 3
```

The system must flag such relationships for review.

The system must not automatically conclude collusion or fraud.

---

# Supplier Analysis

## Supplier Spend

Supplier spend equals total procurement expenditure associated with the supplier.

Financial values must originate from PV whenever available.

---

## Supplier Availability

Supplier availability is derived from:

* Delivery history
* Pending deliveries
* Fulfillment consistency

---

## Supplier Reliability

Supplier reliability should consider:

* Average lead time
* Lead-time variability
* Delivery completion rate
* Pending deliveries

---

# Supplier Risk

Supplier risk is a composite metric.

Factors may include:

* Average lead time
* Lead-time variability
* Delivery completion rate
* Pending deliveries
* Supplier dependency
* Price volatility
* Alternative supplier availability

Higher scores indicate higher procurement risk.

---

# Inventory Classification

## ABC Classification

ABC classification is based on cumulative procurement value.

Procurement value must use PV financial data whenever available.

---

## Class A

Highest-value inventory items.

Approximate cumulative contribution:

```text
0% – 80%
```

---

## Class B

Moderate-value inventory items.

Approximate cumulative contribution:

```text
80% – 95%
```

---

## Class C

Remaining inventory items.

Approximate cumulative contribution:

```text
95% – 100%
```

Thresholds may be configurable.

---

# Demand Classification

The system uses Syntetos–Boylan Classification (SBC).

Classification metrics:

* ADI
* CV²

---

## Smooth

```text
ADI < 1.32
CV² < 0.49
```

---

## Erratic

```text
ADI < 1.32
CV² ≥ 0.49
```

---

## Intermittent

```text
ADI ≥ 1.32
CV² < 0.49
```

---

## Lumpy

```text
ADI ≥ 1.32
CV² ≥ 0.49
```

---

# Demand Reconstruction

The system does not receive direct sales ledgers.

Historical demand must be reconstructed using:

```text
GRN
PV
Closing Stock
```

The reconstruction process must generate a chronological demand series suitable for forecasting.

The exact reconstruction methodology may evolve independently of the forecasting layer.

---

# Forecasting

## Primary Forecasting Method

There is no single primary method. Forecasting is routed by Syntetos–Boylan class,
and the per-class winner is selected by backtested accuracy (MASE/RMSSE) against
naive baselines. Exponential smoothing (ETS) is the baseline for the continuous
(smooth/erratic) classes; the intermittent classes use Croston-family methods.

---

## Forecast Components

Exponential smoothing (ETS) models continuous demand through:

```text
Level
Trend
Seasonality
```

---

### Level

Represents baseline demand.

---

### Trend

Represents long-term directional movement.

Examples:

```text
Growing Demand
Declining Demand
Stable Demand
```

---

### Seasonality

Represents recurring demand fluctuations.

Examples:

```text
Monthly
Quarterly
Annual
```

---

## Forecast Output

The forecasting engine must produce:

```text
Forecast Quantity
Trend Estimate
Seasonality Estimate
Forecast Metrics
```

---

# Forecast Routing

Demand classification determines supplementary forecasting behavior.

---

## Smooth

Use ETS (or Theta). Random Forest is not used: tree models cannot extrapolate a
trend (predictions are bounded by training values) and overfit the short per-item
series we have.

---

## Erratic

Use ETS (damped or multiplicative-error). A Tweedie GLM may be trialled as an
optional count-aware challenger; a plain Gaussian GLM is not used, because the
problem here is quantity variance, not the mean trajectory a GLM models.

---

## Intermittent

Use Teunter–Syntetos–Babai (TSB), benchmarked against Croston-SBA. TSB updates the
demand probability every period, making it robust to items that go obsolete.

---

## Lumpy

Use TSB or Croston-SBA. For this class the forecast output is the lead-time demand
distribution feeding the reorder point, not a point-forecast curve — a point
forecast on lumpy demand is close to meaningless.

---

## Lumpy

Use:

```text
Teunter–Syntetos–Babai
```

---

## Forecast Pipeline

```text
Demand Reconstruction
        ↓
SBC Classification
        ↓
Baselines (Naive / SeasonalNaive / SES) + Class-Routed Candidates
        ↓
Backtested Selection (rolling-origin CV, MASE / RMSSE)
        ↓
Final Forecast
```

---

# Financial Rules

## Currency Precision

Financial calculations must use:

* Decimal arithmetic
* Fixed-point arithmetic

Floating-point currency accumulation is prohibited.

---

## Procurement Cost

Procurement cost must be sourced from PV whenever available.

---

## Freight

Freight information originates from PV.

Current business assumption:

```text
Freight = 18%
```

The exact accounting interpretation requires validation.

Potential interpretations:

* Freight
* GST
* Freight plus tax

Until validated, the system must treat freight as a separate cost component.

---

# Inventory Philosophy

The organization does not operate using fixed inventory thresholds.

There are currently no mandatory:

* Reorder Levels
* Danger Levels
* Safety Stock Levels

Procurement behavior is primarily consumption-driven.

A typical procurement cycle follows:

```text
Inventory Consumed
        ↓
Inventory Ordered
        ↓
Inventory Received
```

---

# Workbook Requirements

Generated workbooks must contain:

* Metadata
* Forecasts
* Demand History
* Financial Analysis
* Supplier Risk Analysis
* Inventory Classifications
* Lead-Time Analysis
* Pending Deliveries
* Supplier Partnership Analysis
* Dashboard Cache

Workbooks are the canonical persisted representation of system outputs.

---

# Pending Business Decisions

The following areas require future validation:

* Exact demand reconstruction methodology
* Freight accounting interpretation
* PV accounting semantics
* Supplier grouping beyond parenthetical normalization
* Supplier risk weighting methodology
* Inventory health scoring methodology

No implementation may assume final behavior for these areas without approval.
