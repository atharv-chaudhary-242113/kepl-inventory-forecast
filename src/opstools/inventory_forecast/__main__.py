"""Console entry point for the application.

Wired to the `inventory-forecast` script in pyproject.toml and runnable as
`python -m opstools.inventory_forecast`. In Phase 0 the engine and UI are not
yet built, so `main` reports the version and exits cleanly — exactly what the
Phase 0 gate checks (ROADMAP.md). The PySide6 bootstrap arrives in Phase 6.
"""

from opstools.inventory_forecast import __version__


def main() -> int:
    """Start the application and return a process exit code (0 == success)."""
    print(f"KEPL Inventory Forecast {__version__}")
    print("Scaffold build: engine and UI are not yet wired. Exiting cleanly.")
    return 0


if __name__ == "__main__":
    # SystemExit carries the int code to the shell; `python -m ...` exits 0.
    raise SystemExit(main())
