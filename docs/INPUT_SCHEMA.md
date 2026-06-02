# INPUT_SCHEMA.md

# Input Schema Specification

## Purpose

This document defines the canonical input formats accepted by the KEPL Inventory Forecast platform.

The ingestion layer must operate on semantic schema detection rather than fixed row positions.

The system must tolerate ERP-generated report layouts containing metadata rows, blank formatting rows, grouped records, and varying header positions.

---

# General Parsing Rules

## Supported Formats

Accepted formats:

```text
.csv
.xls
.xlsx
```

---

## Header Detection

The application must not assume that headers begin on a specific row.

Reports may contain:

* Company information
* Report titles
* Date ranges
* Generated timestamps
* Blank formatting rows

before the actual tabular data begins.

Example:

```text
Company Name
Address
Report Name
Date Range

Date | Vch/Bill No | Particulars | Item Details | ...
```

The ingestion layer must locate the first valid header row dynamically.

---

## Header Matching

Column matching must be:

* Case-insensitive
* Whitespace-insensitive
* Position-independent

The parser must identify columns by name rather than column index.

---

## Additional Columns

The parser must tolerate:

* Additional columns
* Unused columns
* Reordered columns

Only required columns participate in domain processing.

---

# Hierarchical Report Parsing Rules

## Background

The procurement reports are hierarchical.

A supplier may appear once and implicitly apply to multiple subsequent rows.

Example:

| Particulars     | Item Details      |
| --------------- | ----------------- |
| ABC Electricals | Copper Wire 2.5mm |
|                 | Copper Wire 4mm   |
|                 | Copper Wire 6mm   |
| XYZ Traders     | PVC Tape          |
|                 | Cable Tie         |

---

## Forward-Fill Rule

Empty cells in grouped columns inherit the most recent non-empty value from the same column.

Example:

Before normalization:

| Particulars     | Item Details      |
| --------------- | ----------------- |
| ABC Electricals | Copper Wire 2.5mm |
|                 | Copper Wire 4mm   |
|                 | Copper Wire 6mm   |

After normalization:

| Particulars     | Item Details      |
| --------------- | ----------------- |
| ABC Electricals | Copper Wire 2.5mm |
| ABC Electricals | Copper Wire 4mm   |
| ABC Electricals | Copper Wire 6mm   |

---

## Forward-Fill Columns

The following columns must be forward-filled:

```text
Particulars
```

Additional columns may be added in future schema revisions.

---

## Record Preservation

Rows must not be discarded solely because a field is empty.

An empty `Particulars` value does not represent missing data.

It represents inheritance from the previous row.

---

## Row Rejection Rules

Reject a row only when both fields are empty:

```text
Particulars
AND
Item Details
```

Such rows are treated as formatting separators.

---

## Canonicalization Order

Apply transformations in the following sequence:

```text
Locate Header
    ↓
Extract Rows
    ↓
Remove Empty Separator Rows
    ↓
Forward Fill Grouped Columns
    ↓
Normalize Supplier Names
    ↓
Validate Schema
    ↓
Construct Domain Records
```

---

# Supplier Normalization

Supplier normalization occurs after forward-fill processing.

Remove all parenthetical suffixes from the `Particulars` field.

Example:

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

# Purchase Order Voucher (POV)

## Purpose

Represents purchase orders placed with suppliers.

Used for:

* Lead-time analysis
* Procurement history
* Pending delivery analysis
* Supplier analysis

---

## Required Columns

| Column       |
| ------------ |
| Date         |
| Vch/Bill No  |
| Particulars  |
| Item Details |
| Qty.         |
| Unit         |
| Price        |
| Amount       |

---

## Column Definitions

### Date

Purchase order creation date.

---

### Vch/Bill No

Purchase order identifier.

---

### Particulars

Supplier name.

Subject to supplier normalization.

---

### Item Details

Inventory item description.

---

### Qty.

Ordered quantity.

Must be positive.

---

### Unit

Inventory measurement unit.

Examples:

```text
Nos
Meters
Kg
Box
```

---

### Price

Unit purchase price.

Must be non-negative.

---

### Amount

Extended purchase value.

Must be non-negative.

---

# Goods Received Note (GRN)

## Purpose

Represents physical inventory receipt.

Used for:

* Delivery analysis
* Lead-time analysis
* Supplier performance analysis
* Inventory movement analysis

---

## Required Columns

| Column       |
| ------------ |
| Date         |
| Vch/Bill No  |
| Particulars  |
| Item Details |
| Qty.         |
| Unit         |
| Price        |
| Amount       |

---

## Column Definitions

### Date

Inventory receipt date.

---

### Vch/Bill No

Goods receipt identifier.

---

### Particulars

Supplier name.

Subject to supplier normalization.

---

### Item Details

Delivered inventory item.

---

### Qty.

Delivered quantity.

Must be positive.

---

### Unit

Inventory measurement unit.

---

### Price

Unit purchase price.

Must be non-negative.

---

### Amount

Total transaction amount.

Must be non-negative.

---

# Purchase Voucher (PV)

## Purpose

Represents finalized procurement transactions.

Used for:

* Spend analysis
* Supplier expenditure analysis
* Financial analysis

---

## Required Columns

| Column       |
| ------------ |
| Date         |
| Vch/Bill No  |
| Particulars  |
| Item Details |
| Qty.         |
| Unit         |
| Price        |
| Amount       |

---

## Column Definitions

### Date

Voucher creation date.

---

### Vch/Bill No

Voucher identifier.

---

### Particulars

Supplier name.

Subject to supplier normalization.

---

### Item Details

Purchased inventory item.

---

### Qty.

Purchased quantity.

Must be positive.

---

### Unit

Inventory measurement unit.

---

### Price

Unit purchase price.

Must be non-negative.

---

### Amount

Total purchase value.

Must be non-negative.

---

# Closing Stock

## Purpose

Represents inventory snapshots captured on a specific date.

Used for:

* Inventory analysis
* Demand estimation
* Forecast preparation

---

## Required Columns

| Column       |
| ------------ |
| Item Details |
| Qty.         |
| Price        |
| Amount       |

---

## Optional Columns

| Column     |
| ---------- |
| Cat. No    |
| Item Group |
| Make       |
| Unit       |

---

## Column Definitions

### Item Details

Inventory item description.

---

### Qty.

Inventory quantity available at snapshot date.

Must be zero or greater.

---

### Price

Inventory valuation price.

Must be non-negative.

---

### Amount

Inventory valuation amount.

Must be non-negative.

---

# Item Identity

Current canonical item identity:

```text
Normalized Supplier
+
Item Details
```

This relationship reflects the procurement reality that the same inventory description may be sourced from multiple suppliers.

Future schema versions may introduce a dedicated item master.

---

# Validation Rules

Reject records when:

* Required columns are missing.
* Date parsing fails.
* Quantity is negative.
* Price is negative.
* Amount is negative.
* Supplier normalization produces an empty value.
* Item Details is empty.

---

# Parser Requirements

The ingestion layer must support:

* Variable header positions.
* ERP-generated report metadata.
* Blank formatting rows.
* Hierarchical supplier grouping.
* Forward-filled supplier inheritance.
* Reordered columns.
* Additional unused columns.
* Multiple workbook sheets.
* Multiple yearly input files.

The parser must rely on semantic column identification rather than positional assumptions.

---

# Future Extensions

Future schema versions may introduce:

* Item master files.
* Supplier master files.
* Sales history files.
* Inventory movement ledgers.
* Pricing history files.

Schema evolution must remain backward-compatible whenever possible.
