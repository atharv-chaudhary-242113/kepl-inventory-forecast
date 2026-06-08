# Threat Model

## Purpose and Scope

This document identifies the assets KEPL Inventory Forecast must protect, the
boundaries data crosses, the threats against each, and the controls that mitigate
them. It is scoped to the pure-Python desktop build: a single-process, offline
application with no server, no network dependency, and no foreign-function
interface. The absence of an FFI is itself a security property — it removes an
entire class of boundary, panic-propagation, and memory-safety threats that a
mixed-language build must defend.

---

## Security Objectives

Protect:

* Forecast accuracy
* Financial calculations
* Inventory analytics
* Workbook integrity
* Application availability
* The local file system
* User workstations
* Internal business data

Assume:

* All external files are untrusted.
* All workbook metadata is untrusted.
* All user input is untrusted.
* Internal users may make mistakes.
* Internal users may act maliciously.
* Workstations may already be partially compromised.

---

## Trust Boundaries

```text
External Files
    ↓
Validation Layer
    ↓
Workbook Loader
    ↓
Application State
    ↓
Dashboard Layer
    ↓
Export Layer
```

Validate all data crossing every boundary. There is no language boundary in this
build; all layers run in one Python process, so the only trust boundaries are the
ones above — where untrusted bytes (files, workbook contents, user input) enter
trusted application state.

---

## Critical Assets

### Business Assets

* Forecast outputs
* Financial metrics
* Inventory metrics
* Classifications
* Executive summaries

### Technical Assets

* Workbook exports
* Dashboard cache
* Configuration files
* Logs
* Application state

### System Assets

* Local file system
* User credentials
* Network credentials
* Workstation resources

---

## Data Integrity Threats

### Silent Data Corruption

Risk:

* Incorrect forecasts
* Incorrect financial outputs
* Incorrect business decisions

Controls:

* Validate ranges
* Validate aggregates
* Validate cross-sheet consistency
* Validate statistical assumptions
* Reconcile exported results
* Implement control totals

Priority: Critical

---

### Workbook Tampering

Risk:

* Manipulated forecasts
* Manipulated analytics
* Manipulated financial metrics

Controls:

* Store workbook hash
* Store sheet hashes
* Validate integrity on load
* Detect modifications

Priority: Critical

---

### Schema Downgrade Attacks

Risk:

* Validation bypass
* Legacy parser abuse

Controls:

* Version workbook schemas
* Reject unsupported versions
* Require explicit migrations

Priority: High

---

### Formula Injection

Examples:

```excel
=HYPERLINK(...)
=WEBSERVICE(...)
=cmd|' /C calc'!A0
```

Risk:

* Malicious workbook execution
* Data exfiltration

Controls:

* Escape dangerous cell values
* Prefix any value beginning with one of these characters with a single quote:

  * `=`
  * `+`
  * `-`
  * `@`

Priority: High

---

## File System Threats

### UNC Path Injection

Examples:

```text
\\server\share\file.xlsx
```

Risk:

* NetNTLM leakage
* SMB relay attacks

Controls:

* Reject UNC paths
* Reject SMB paths
* Allow local paths only

Priority: High

---

### Path Traversal

Examples:

```text
..\..\Windows
```

Risk:

* Arbitrary file access
* Unauthorized overwrite

Controls:

* Resolve absolute paths
* Restrict operations to approved directories
* Reject traversal patterns

Priority: High

---

### Arbitrary File Access Through Metadata

Risk:

* Workbook content controls file operations

Controls:

* Ignore workbook-supplied paths
* Use application-controlled directories only

Priority: High

---

## Workbook Threats

### ZIP Bombs

Risk:

* Memory exhaustion
* Disk exhaustion
* Application crash

Controls:

* Validate archive structure
* Validate compression ratios
* Enforce workbook size limits

Priority: High

---

### XML External Entity Attacks

Risk:

* Local file disclosure
* Resource abuse

Controls:

* Disable DTD processing
* Disable external entities
* Disable external resource loading

Priority: Medium

---

### Oversized Workbooks

Risk:

* Out-of-memory crashes
* UI freezes

Controls:

* Enforce row limits
* Enforce column limits
* Enforce sheet limits
* Enforce workbook size limits

Priority: High

---

## Dashboard Threats

### Plotly XSS

Risk:

* JavaScript execution
* Dashboard compromise

Controls:

* HTML-escape workbook content
* Sanitize metadata
* Never render raw workbook HTML

Priority: Medium

---

### QWebEngine Abuse

Risk:

* Local file access
* Remote resource access

Controls:

* Disable unnecessary capabilities
* Restrict local file access
* Restrict remote content

Priority: Medium

---

### QWebChannel Abuse

Risk:

* Direct access to Python objects from the renderer

Controls:

* Expose minimal interfaces
* Validate all inputs
* Apply strict type checks

Priority: Medium

---

### Renderer Process Exhaustion

Risk:

* Zombie Chromium processes
* Memory leaks
* UI freezes

Controls:

* Reuse dashboard views
* Destroy unused views
* Explicitly release renderer resources
* Monitor renderer counts

Priority: Medium

---

### Dashboard Recreation Abuse

Risk:

* Resource exhaustion from rapid re-rendering

Controls:

* Debounce filter actions
* Throttle refreshes
* Reuse dashboard widgets

Priority: Medium

---

## Query Threats

### Polars Expression Injection

Risk:

* Unexpected query behavior from dynamically built expressions

Controls:

* Avoid dynamic expression construction from user input
* Validate identifiers (column/sheet names) against an allowlist

Priority: Medium

> Note: DuckDB is not a runtime dependency in this build (it is a documented
> performance escalation only). If DuckDB is later adopted, reintroduce a
> "DuckDB Injection" threat (parameterized queries, validated identifiers,
> disabled extensions) at High priority.

---

## Resource Exhaustion Threats

### Memory Exhaustion

Risk:

* Application instability

Controls:

* Limit workbook size
* Limit cache size
* Limit dataset size

Priority: High

---

### CPU Exhaustion

Risk:

* Unresponsive application

Controls:

* Benchmark algorithms against the performance budget
* Reject pathological workloads
* Run long computations on a background worker, never the UI thread

Priority: Medium

---

### Chart Rendering Exhaustion

Risk:

* Frozen dashboards

Controls:

* Aggregate large datasets before rendering
* Limit categories per chart
* Paginate large tables

Priority: Medium

---

## State Management Threats

### State Desynchronization

Risk:

* Incorrect dashboard outputs

Controls:

* Maintain a single source of truth
* Centralize state management
* Pass immutable frames from worker to UI

Priority: High

---

### Concurrent File Access

Risk:

* Corrupted workbooks
* Inconsistent reads

Controls:

* Detect file locks
* Warn users
* Prefer local copies

Priority: Medium

---

## Financial Integrity Threats

### Floating-Point Errors

Risk:

* Incorrect financial calculations

Controls:

* Use Decimal (Polars `Decimal` / Python `Decimal`)
* Use integer cents where appropriate
* Never accumulate currency in floating point

Priority: High

---

### Date Parsing Errors

Risk:

* Invalid lead times and forecasts

Controls:

* Normalize dates at the ingestion boundary
* Store ISO-8601 values internally
* Parse to an explicit Date dtype rather than relying on inference

Priority: High

---

## Logging Threats

### Sensitive Data Exposure

Risk:

* Confidential business data leakage through logs

Controls:

* Avoid logging business data
* Sanitize logs

Priority: Medium

---

### Log Forgery

Risk:

* Misleading audit trails

Controls:

* Use structured logging
* Sanitize user-controlled values

Priority: Medium

---

## Dependency Threats

### Python Supply Chain

Risk:

* Compromised or vulnerable third-party packages

Controls:

* Pin all dependency versions in `uv.lock`
* Run `pip-audit` (or equivalent) on the locked set
* Review upgrades before committing a lockfile change

Priority: Medium

---

## Windows Desktop Threats

### DLL Search Order Hijacking

Risk:

* Arbitrary code execution

Controls:

* Restrict DLL search paths
* Avoid loading dependencies from user-controlled directories
* Sign release builds where practical

Priority: Medium

---

### Network Share Execution

Risk:

* Increased DLL hijacking exposure
* Unpredictable execution

Controls:

* Require local installation
* Warn on network execution

Priority: Medium

---

### PyInstaller Runtime Extraction Abuse

Risk:

* Runtime asset tampering during extraction

Controls:

* Validate extraction directory permissions
* Verify ownership
* Prefer one-folder deployment

Priority: Low

---

### Windows File-Locking Conflicts

Risk:

* Export failures
* Partial writes

Controls:

* Detect sharing violations
* Handle `PermissionError` gracefully
* Notify users

Priority: High

---

### Incomplete Exports

Risk:

* Corrupted workbooks from interrupted writes

Controls:

* Write to a temporary file
* Validate the output
* Perform atomic replacement

Priority: High

---

### Temporary File Leakage

Risk:

* Data exposure through leftover temporary files

Controls:

* Use managed temporary directories
* Remove temporary files after use
* Clean up on startup

Priority: Medium

---

## Workbook Authenticity

Risk:

* Forged workbooks presented as system-generated

Controls — store in the Metadata sheet:

* Application version
* Workbook schema version
* Generation timestamp
* Source file hash
* Output hash

Optionally:

* Digitally sign workbook metadata

Priority: Medium

---

## Security Testing Requirements

Test:

* Malformed workbooks
* Corrupted archives
* ZIP bombs
* Formula injection
* UNC paths
* Path traversal
* Workbook tampering
* Schema downgrade attacks
* Polars expression injection
* Plotly XSS
* Large datasets
* Resource exhaustion
* State desynchronization
* Concurrent access
* DLL hijacking scenarios
* File-locking scenarios

Block releases on critical failures.

---

## Highest-Priority Risks

1. Silent data corruption
2. Workbook tampering
3. Formula injection
4. UNC path injection
5. Path traversal
6. ZIP bomb attacks
7. Floating-point financial errors
8. Date parsing errors
9. State desynchronization
10. Windows file-locking failures
11. Renderer process exhaustion
12. Plotly / QWebEngine abuse
13. Dependency supply-chain compromise

---

## Security Principles

* Validate all inputs.
* Trust no workbook content.
* Trust no metadata.
* Trust no user input.
* Fail closed.
* Prefer allowlists over blocklists.
* Treat Excel as untrusted.
* Treat workbook integrity as a first-class requirement.
* Treat data integrity as equal to cybersecurity.
* Isolate business logic from UI logic.
* Isolate file I/O from business logic.
* Run long computations off the UI thread.
* Measure security continuously.
* Block releases on critical security failures.