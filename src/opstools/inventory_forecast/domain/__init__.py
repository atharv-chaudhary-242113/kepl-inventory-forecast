"""Pure domain types: enums, error hierarchy, and DTOs.

Re-exported here so callers can write
`from opstools.inventory_forecast.domain import SourceKind` without reaching
into submodules. This layer imports nothing else of ours (ARCHITECTURE.md
§4.1): `domain` is the foundation everything else depends on.
"""

from opstools.inventory_forecast.domain.enums import (
    AbcClass,
    ForecastGranularity,
    SbcClass,
    SourceKind,
)
from opstools.inventory_forecast.domain.errors import (
    ForecastError,
    InventoryForecastError,
    SchemaError,
    ValidationError,
    WorkbookVersionError,
)
from opstools.inventory_forecast.domain.models import SourceSet, WorkbookMeta

__all__ = [
    "AbcClass",
    "ForecastError",
    "ForecastGranularity",
    "InventoryForecastError",
    "SbcClass",
    "SchemaError",
    "SourceKind",
    "SourceSet",
    "ValidationError",
    "WorkbookMeta",
    "WorkbookVersionError",
]
