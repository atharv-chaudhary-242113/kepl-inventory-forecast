# Threat Model

## Security Objectives

Protect:

* Forecast accuracy
* Financial calculations
* Inventory analytics
* Workbook integrity
* Application availability
* Local file system
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

# Trust Boundaries

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

```text
Python
    ↕
PyO3 Boundary
    ↕
Rust Engine
```

Validate all data crossing every boundary.

---

# Critical Assets

## Business Assets

* Forecast outputs
* Financial metrics
* Inventory metrics
* Classifications
* Executive summaries

## Technical Assets

* Workbook exports
* Dashboard cache
* Configuration files
* Logs
* Application state

## System Assets

* Local file system
* User credentials
* Network credentials
* Workstation resources

---

# Threat Categories

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
* Prefix values beginning with:

  * =
  * *
  * *
  * @

Priority: High

---

# File System Threats

## UNC Path Injection

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

## Path Traversal

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

## Arbitrary File Access Through Metadata

Risk:

* Workbook controls file operations

Controls:

* Ignore workbook-supplied paths
* Use application-controlled directories

Priority: High

---

# Workbook Threats

## ZIP Bombs

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

## XML External Entity Attacks

Risk:

* Local file disclosure
* Resource abuse

Controls:

* Disable DTD processing
* Disable external entities
* Disable external resource loading

Priority: Medium

---

## Oversized Workbooks

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

# Dashboard Threats

## Plotly XSS

Risk:

* JavaScript execution
* Dashboard compromise

Controls:

* HTML-escape workbook content
* Sanitize metadata
* Never render raw workbook HTML

Priority: Medium

---

## QWebEngine Abuse

Risk:

* Local file access
* Remote resource access

Controls:

* Disable unnecessary capabilities
* Restrict local file access
* Restrict remote content

Priority: Medium

---

## QWebChannel Abuse

Risk:

* Direct access to Python objects

Controls:

* Expose minimal interfaces
* Validate all inputs
* Apply strict type checks

Priority: Medium

---

## Renderer Process Exhaustion

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

## Dashboard Recreation Abuse

Risk:

* Resource exhaustion

Controls:

* Debounce filter actions
* Throttle refreshes
* Reuse dashboard widgets

Priority: Medium

---

# Query Threats

## DuckDB Injection

Risk:

* Arbitrary query execution
* File access abuse

Controls:

* Use parameterized queries
* Validate identifiers
* Disable unnecessary extensions

Priority: High

---

## Polars Expression Injection

Risk:

* Unexpected query behavior

Controls:

* Avoid dynamic expression construction
* Validate identifiers

Priority: Medium

---

# Rust-Python Boundary Threats

## Invalid Data Structures

Risk:

* Crashes
* Panics
* Undefined behavior

Controls:

* Validate lengths
* Validate dimensions
* Validate ranges
* Validate enum values

Priority: High

---

## Panic Propagation

Risk:

* Python process termination

Controls:

* Catch Rust panics
* Convert panics to Python exceptions

Priority: High

---

## Unsafe Rust Abuse

Risk:

* Memory corruption

Controls:

* Minimize unsafe code
* Audit unsafe blocks
* Test unsafe code

Priority: High

---

# Resource Exhaustion Threats

## Memory Exhaustion

Risk:

* Application instability

Controls:

* Limit workbook size
* Limit cache size
* Limit dataset size

Priority: High

---

## CPU Exhaustion

Risk:

* Unresponsive application

Controls:

* Benchmark algorithms
* Reject pathological workloads

Priority: Medium

---

## Chart Rendering Exhaustion

Risk:

* Frozen dashboards

Controls:

* Aggregate large datasets
* Limit categories
* Paginate large tables

Priority: Medium

---

## Serialization Bombs

Risk:

* Massive Rust-Python transfers

Controls:

* Chunk large transfers
* Limit payload sizes

Priority: Medium

---

# State Management Threats

## State Desynchronization

Risk:

* Incorrect dashboard outputs

Controls:

* Maintain a single source of truth
* Centralize state management

Priority: High

---

## Concurrent File Access

Risk:

* Corrupted workbooks
* Inconsistent reads

Controls:

* Detect file locks
* Warn users
* Prefer local copies

Priority: Medium

---

# Financial Integrity Threats

## Floating Point Errors

Risk:

* Incorrect financial calculations

Controls:

* Use Decimal
* Use integer cents where appropriate

Priority: High

---

## Date Parsing Errors

Risk:

* Invalid forecasts

Controls:

* Normalize dates
* Store ISO-8601 values internally

Priority: High

---

# Logging Threats

## Sensitive Data Exposure

Risk:

* Confidential data leakage

Controls:

* Avoid logging business data
* Sanitize logs

Priority: Medium

---

## Log Forgery

Risk:

* Misleading audit trails

Controls:

* Use structured logging
* Sanitize user-controlled values

Priority: Medium

---

# Dependency Threats

## Python Supply Chain

Controls:

* Pin dependency versions
* Run pip-audit
* Review upgrades

Priority: Medium

---

## Rust Supply Chain

Controls:

* Run cargo audit
* Run cargo deny
* Review dependency changes

Priority: Medium

---

# Windows Desktop Threats

## DLL Search Order Hijacking

Risk:

* Arbitrary code execution

Controls:

* Restrict DLL search paths
* Avoid loading dependencies from user-controlled directories
* Sign release builds where practical

Priority: Medium

---

## Network Share Execution

Risk:

* Increased DLL hijacking exposure
* Unpredictable execution

Controls:

* Require local installation
* Warn on network execution

Priority: Medium

---

## PyInstaller Runtime Extraction Abuse

Risk:

* Runtime asset tampering

Controls:

* Validate extraction directory permissions
* Verify ownership
* Consider one-folder deployment

Priority: Low

---

## Windows File Locking Conflicts

Risk:

* Export failures
* Partial writes

Controls:

* Detect sharing violations
* Handle PermissionError gracefully
* Notify users

Priority: High

---

## Incomplete Exports

Risk:

* Corrupted workbooks

Controls:

* Write to temporary files
* Validate outputs
* Perform atomic replacement

Priority: High

---

## Temporary File Leakage

Risk:

* Data exposure

Controls:

* Use managed temporary directories
* Remove temporary files after use
* Clean up on startup

Priority: Medium

---

# Workbook Authenticity

Risk:

* Forged workbooks presented as system-generated

Controls:

Store:

* Application version
* Workbook schema version
* Generation timestamp
* Source file hash
* Output hash

Optionally:

* Digitally sign workbook metadata

Priority: Medium

---

# Security Testing Requirements

Test:

* Malformed workbooks
* Corrupted archives
* ZIP bombs
* Formula injection
* UNC paths
* Path traversal
* Workbook tampering
* Schema downgrade attacks
* Query injection
* Plotly XSS
* Rust boundary failures
* Large datasets
* Resource exhaustion
* State desynchronization
* Concurrent access
* DLL hijacking scenarios
* File locking scenarios

Block releases on critical failures.

---

# Highest Priority Risks

1. Silent data corruption
2. Workbook tampering
3. Formula injection
4. UNC path injection
5. Path traversal
6. Rust-Python boundary failures
7. DuckDB query injection
8. ZIP bomb attacks
9. Floating-point financial errors
10. Date parsing errors
11. State desynchronization
12. Windows file-locking failures
13. Renderer process exhaustion
14. Plotly/QWebEngine abuse
15. Dependency supply-chain compromise

---

# Security Principles

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
* Keep Rust-Python contracts explicit.
* Measure security continuously.
* Block releases on critical security failures.
