"""Dashboard cache state management.

Handles the serialization and deserialization of BI dashboard state
into the workbook's Dashboard_Cache sheet. While the primary GUI
is excluded from the core engine, this module preserves the contract
for future Plotly/Dash state persistence (e.g., user filter selections,
sort orders, or active tabs) directly within the single source of truth.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import polars as pl

from opstools.inventory_forecast.workbook.schema import (
    WorksheetName,
    get_sheet_schema,
)

logger = logging.getLogger(__name__)


def build_dashboard_cache_df(state: dict[str, Any] | None = None) -> pl.DataFrame:
    """Serialize dashboard visualization state into a DataFrame.

    Converts an arbitrary state dictionary into a key-value tabular
    format suitable for Excel persistence. Values are JSON serialized.

    Args:
        state: Dictionary of JSON-serializable dashboard state.

    Returns:
        A Polars DataFrame containing the serialized cache.
    """
    _ = get_sheet_schema(WorksheetName.DASHBOARD_CACHE)
    df_schema = {"cache_key": pl.Utf8, "cache_value": pl.Utf8}

    if not state:
        return pl.DataFrame(schema=df_schema)

    data = []
    for key, value in state.items():
        try:
            serialized = json.dumps(value)
            data.append({"cache_key": str(key), "cache_value": serialized})
        except (TypeError, ValueError) as exc:
            logger.warning("Failed to serialize dashboard cache key %r: %s", key, exc)

    return pl.DataFrame(data, schema=df_schema)


def parse_dashboard_cache_df(df: pl.DataFrame) -> dict[str, Any]:
    """Deserialize dashboard state from a DataFrame.

    Reconstructs the state dictionary from the key-value tabular format.

    Args:
        df: The Dashboard_Cache DataFrame.

    Returns:
        Dictionary of parsed dashboard state.
    """
    if df.is_empty():
        return {}

    if "cache_key" not in df.columns or "cache_value" not in df.columns:
        logger.debug("Dashboard cache DataFrame is missing standard key/value columns.")
        return {}

    state: dict[str, Any] = {}

    for row in df.iter_rows(named=True):
        key = row.get("cache_key")
        value_str = row.get("cache_value")

        if key is None or value_str is None:
            continue

        try:
            state[str(key)] = json.loads(str(value_str))
        except (json.JSONDecodeError, TypeError):
            # Fallback to string if JSON decoding fails (e.g., manual Excel edit)
            state[str(key)] = value_str

    return state
