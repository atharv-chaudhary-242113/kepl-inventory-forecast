"""Ingestion layer: untrusted ERP exports -> clean, typed, validated frames.

Re-exports the public entry point so callers write
`from opstools.inventory_forecast.ingestion import read_source`. Depends only on
`domain` and `security` (ARCHITECTURE.md sec 4.2).
"""

from opstools.inventory_forecast.ingestion.reader import read_source

__all__ = ["read_source"]
