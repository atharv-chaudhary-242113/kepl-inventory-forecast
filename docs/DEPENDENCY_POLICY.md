# Dependency Policy

## Principles
- One strong library per concern, not several overlapping ones.
- Every dependency earns its place. "Easy to maintain" means a small, understood
  dependency surface.
- All dependencies are pinned in `uv.lock`. Adding one is a deliberate, recorded act.
- Prefer libraries that are actively maintained, permissively or compatibly
  licensed, and wheel-distributed (no build toolchain required at install).

## Runtime Dependencies

| Library              | Concern                | Why this one                                       |
| -------------------- | ---------------------- | -------------------------------------------------- |
| polars               | data engine            | Rust-backed, lazy, typed (ADR-006)                 |
| fastexcel / calamine | Excel reading          | fast; handles `.xls` and `.xlsx`                   |
| xlsxwriter           | Excel writing          | rich formatting; backs Polars `write_excel`        |
| statsforecast        | forecasting            | ETS, Theta, Croston-SBA, TSB, baselines; numba-fast (ADR-007) |
| scikit-learn / lightgbm (opt.) | optional ML challenger | global GBM benchmark only; not a per-class default |
| pydantic             | validation + settings  | typed boundaries (Constitution Rules 7–8)          |
| pyside6              | desktop UI             | native, offline (ADR-002)                          |
| plotly               | charts                 | interactive, exportable (ADR-005)                  |

## Development Dependencies

| Library          | Concern                                  |
| ---------------- | ---------------------------------------- |
| ruff             | lint + format (single tool)              |
| mypy             | strict static typing                     |
| pytest           | unit + integration tests                 |
| pytest-benchmark | the Rust-vs-Python performance harness   |
| pyinstaller      | offline Windows packaging                |

## Explicitly Not Used (and Why)
- **pandas in the processing path** — Polars owns data; pandas appears only as a
  transient at the statsforecast boundary, then converts straight back.
- **DuckDB** — Polars covers our needs at this scale. DuckDB is the *documented
  escalation* if a profiled join/aggregation outgrows Polars, never a default.
- **Rust / PyO3** — the entire premise of this branch (see `BENCHMARK_PLAN.md`).
- **Heavy ORMs / DB drivers** — there is no database; the workbook is persistence.

## Adding a Dependency
1. State the concern it covers and why no existing dependency can.
2. Check license compatibility and maintenance health.
3. `uv add <pkg>`; commit the updated `uv.lock`.
4. Note the addition and its justification in the commit message.

## Removing or Replacing
A dependency that no longer earns its place is removed in a dedicated commit, with
the lockfile updated and any doc that referenced it amended.