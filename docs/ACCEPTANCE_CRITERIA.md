# ACCEPTANCE_CRITERIA.md

# Acceptance Criteria

## Functional

The system shall:

* Load POV files.
* Load GRN files.
* Load PV files.
* Load Closing Stock files.
* Validate schemas.
* Reconstruct supplier relationships.
* Calculate lead times.
* Calculate pending deliveries.
* Calculate supplier risk.
* Detect supplier partnerships.
* Classify inventory.
* Forecast demand.
* Export workbooks.
* Load exported workbooks.

---

## Performance

### Initial Processing

20,000+ records per source file.

Target:

```text
< 60 seconds
```

for full processing on a modern workstation.

---

### Workbook Loading

Target:

```text
< 5 seconds
```

---

### Dashboard Startup

Target:

```text
< 3 seconds
```

---

### Filter Response

Target:

```text
< 200 milliseconds
```

---

## Reliability

The system shall:

* Reject invalid schemas.
* Reject malformed dates.
* Reject negative quantities.
* Reject negative costs.
* Detect workbook version mismatches.

---

## Security

The system shall:

* Prevent path traversal.
* Prevent UNC path usage.
* Prevent formula injection.
* Prevent query injection.
* Validate workbook integrity.

---

## Reproducibility

The same inputs must produce:

* Identical classifications.
* Identical forecasts.
* Identical risk scores.
* Identical workbook outputs.

under identical application versions.
