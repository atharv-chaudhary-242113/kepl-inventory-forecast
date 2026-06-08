# Coding Standards

## Style (PEP 8 / PEP 257)
- ruff is the single formatter and linter. `ruff format` defines layout; `ruff check`
  defines correctness. No competing config.
- Line length 88. Imports sorted by ruff's isort rules.
- Module, public class, and public function docstrings are mandatory and describe
  *what and why*, not a line-by-line restatement of the code.

## Typing (PEP 484 / 585 / 604)
- `mypy --strict` must pass. No bare `Any` without an inline comment justifying it.
- Use built-in generics (`list[str]`, `dict[str, int]`) and `X | None`.
- A function returning a Polars frame documents its output schema (column names and
  dtypes) in its docstring — that schema is part of the contract.

## Structure
- The layer boundaries in `ARCHITECTURE.md` are enforced by imports: `engine` may
  not import `ui`, `viz`, or `workbook`; `viz` may not import Qt.
- Pure functions in `engine` and `viz`; side effects confined to `ingestion`,
  `workbook`, `services`, and `ui`.
- Prefer Polars expressions over Python loops over rows. A row loop in the
  processing path requires a comment explaining why it can't be vectorized.
- Functions are small and single-purpose. A function that ingests, computes, and
  writes is three functions.

## Comments for Learning
Per the author's preference, non-obvious transformations carry a short teaching
comment explaining the *what and why* — especially Polars idioms and the reasons
behind them. For example: why a `+` is used over `concat_str` for string
concatenation (to avoid a feature-gated API), or why a date column is parsed
locally with explicit strptime options at a boundary (to prevent dtype drift). These
comments are kept even where the code is "obvious to the interpreter," because they
document the reasoning, not the syntax.

## Errors
- Raise `KeplError` subclasses with actionable messages that name the offending file,
  column, or value where possible.
- Never swallow an exception silently. Never raise a bare `Exception`.
- Validation failures are expected control flow at the ingestion boundary; broken
  invariants inside the engine fail fast.

## Determinism
- Seed every stochastic model. No reliance on dict ordering for results. No
  wall-clock or environment in business logic (timestamps belong in metadata only).

## Tests
- Every engine module has a unit test mirroring it.
- Integration tests cover the full pipeline and a lossless workbook round-trip,
  plus a workbook-version-mismatch rejection.
- Performance-sensitive functions have a `pytest-benchmark` case.
- A bug fix adds a regression test that fails before the fix and passes after.

## Commits
- Small, scoped, and tied to a roadmap increment.
- A commit that changes architecture updates the affected document in the same
  commit (Constitution Rule 11).