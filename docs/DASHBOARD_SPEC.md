# DASHBOARD_SPEC.md

# Dashboard Specification

## View 1 — File Selection

Purpose:

Load source files or previously generated workbooks.

Inputs:

* POV Files
* GRN Files
* PV Files
* Closing Stock Files

Alternative Input:

* Existing Forecast Workbook

Actions:

* Validate Files
* Preview File Statistics
* Start Processing
* Open Existing Workbook

Displayed Information:

* File Name
* Record Count
* Date Range
* Validation Status

---

## View 2 — Configuration & Execution

Purpose:

Configure forecasting and analysis.

Configuration:

* Forecast Horizon

* Forecast Granularity

  * Monthly
  * Quarterly

* Supplier Risk Analysis

  * Enabled
  * Disabled

* Partnership Detection

  * Enabled
  * Disabled

Execution Controls:

* Run Analysis
* Export Workbook

Progress Information:

* Records Processed
* Current Stage
* Estimated Remaining Time

---

## View 3 — Results Dashboard

### Executive Dashboard

KPIs

* Total Inventory Value
* Total Procurement Spend
* Total Suppliers
* Total Unique Items
* High-Risk Suppliers
* Pending Deliveries
* Suspected Supplier Partnerships

Charts

* Monthly Procurement Spend
* Monthly Demand Trend
* Inventory Value Distribution
* Supplier Risk Distribution
* ABC Distribution

Tables

* Top 20 Items by Value
* Top 20 Suppliers by Spend
* High-Risk Suppliers

---

### Forecast Dashboard

KPIs

* Forecast Horizon
* Forecast Coverage
* Forecasted Demand

Charts

* Historical Demand vs Forecast
* Seasonal Decomposition
* Trend Component
* Forecast Confidence

Filters

* Supplier
* Item
* Category
* Date Range

Tables

* Forecast Results
* Demand History

---

### Supplier Dashboard

KPIs

* Supplier Count
* Average Lead Time
* Average Spend
* High-Risk Suppliers

Charts

* Supplier Spend Distribution
* Lead-Time Distribution
* Risk Score Distribution

Tables

* Supplier Rankings
* Lead-Time Rankings
* Pending Deliveries
* Partnership Detection Results

---

### Inventory Dashboard

KPIs

* Inventory Value
* ABC Distribution
* Stock Concentration

Charts

* ABC Classification
* Inventory Value Distribution
* Item Value Distribution

Tables

* Class A Items
* Class B Items
* Class C Items

---

### Financial Dashboard

KPIs

* Procurement Spend
* Freight Cost
* Average Unit Cost
* Supplier Cost Concentration

Charts

* Monthly Spend
* Monthly Freight
* Supplier Spend Distribution

Tables

* Cost Analysis
* Freight Analysis
* Supplier Expenditure Analysis

---

## Filtering Requirements

All dashboards must support:

* Supplier Filter
* Item Filter
* Date Filter

Filtering response target:

```text
< 200 ms
```

Filtering must operate on cached in-memory datasets.

No workbook reloads.
No forecasting reruns.
