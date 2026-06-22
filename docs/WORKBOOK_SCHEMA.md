# WORKBOOK_SCHEMA.md

# Workbook Schema

## Sheet: Metadata

One row.

Columns:

* schema_version
* application_version
* generated_at
* forecast_horizon
* total_suppliers
* total_items
* total_records
* processing_time_seconds

---

## Sheet: Demand_History

Granularity:

Monthly

Columns:

* period
* supplier
* item
* demand_quantity
* demand_value

---

## Sheet: Forecasts

Columns:

* supplier
* item
* forecast_period
* forecast_quantity
* forecast_value
* trend_component
* seasonal_component
* model_used
* confidence_score

---

## Sheet: Supplier_Analysis

Columns:

* supplier
* total_spend
* total_orders
* total_deliveries
* average_lead_time
* lead_time_stddev
* pending_deliveries
* reliability_score
* risk_score

---

## Sheet: Supplier_Partnerships

Columns:

* supplier_a
* supplier_b
* matching_events
* confidence_score
* status

---

## Sheet: Lead_Time_Analysis

Columns:

* supplier
* item
* pov_date
* grn_date
* ordered_qty
* delivered_qty
* lead_time_days

---

## Sheet: Pending_Deliveries

Columns:

* supplier
* item
* voucher_number
* ordered_qty
* delivered_qty
* pending_qty
* order_date
* age_days

---

## Sheet: Financial_Summary

Columns:

* supplier
* item
* quantity
* unit_cost
* freight_cost
* total_cost
* total_spend

PV is the authoritative source.

---

## Sheet: ABC_Classification

Columns:

* supplier
* item
* annual_value
* cumulative_percentage
* abc_class

---

## Sheet: SBC_Classification

Columns:

* supplier
* item
* adi
* cv_squared
* demand_class

Values:

```text
Smooth
Erratic
Intermittent
Lumpy
```

---

## Sheet: Inventory_Valuation

Columns:

* item
* quantity
* unit_cost
* inventory_value
* snapshot_date

---

## Sheet: Dashboard_Cache

Precomputed aggregates.

Purpose:

Dashboard rendering only.

Contains:

* Monthly spend
* Monthly demand
* Supplier summaries
* Item summaries
* ABC summaries
* Risk summaries

This sheet is the primary dashboard source.
