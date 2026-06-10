"""Domain enumerations shared across all layers.

Pure value types with no I/O and no dependency on other project modules.
StrEnum members compare equal to their string value, which keeps them ergonomic
when read from / written to Polars frames and Excel cells.
"""

from enum import StrEnum


class SourceKind(StrEnum):
    """The four ERP export types the pipeline ingests (INPUT_SCHEMA.md)."""

    POV = "pov"
    GRN = "grn"
    PV = "pv"
    CLOSING_STOCK = "closing_stock"


class AbcClass(StrEnum):
    """ABC inventory class by cumulative procurement value (DOMAIN_RULES.md)."""

    A = "A"
    B = "B"
    C = "C"


class SbcClass(StrEnum):
    """Syntetos-Boylan demand class (DOMAIN_RULES.md).

    Canonical values are lowercase; the workbook writer title-cases them for the
    SBC_Classification sheet's documented values (WORKBOOK_SCHEMA.md). Keeping
    one canonical casing internally avoids string-comparison bugs.
    """

    SMOOTH = "smooth"
    ERRATIC = "erratic"
    INTERMITTENT = "intermittent"
    LUMPY = "lumpy"


class ForecastGranularity(StrEnum):
    """Forecast period granularity (DASHBOARD_SPEC.md View 2)."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
