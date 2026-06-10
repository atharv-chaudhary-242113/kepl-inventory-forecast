"""Pure domain data-transfer objects.

Pydantic models that cross layer boundaries (API_CONTRACT.md; Constitution
Rules 7-8). No I/O, no Polars, no Qt — just typed, validated data. Models that
must carry Polars frames (AppState, DashboardCache) are defined alongside the
workbook/services layers that build them, where their frame fields can be
specified precisely; defining them here would be speculative.
"""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from opstools.inventory_forecast.domain.enums import SourceKind


class SourceSet(BaseModel):
    """The grouped input files for a single pipeline run.

    Each ERP report type may arrive as several files (e.g. one per year —
    INPUT_SCHEMA.md "Multiple yearly input files"), so each field is a tuple of
    paths. Tuples (not lists) keep the model genuinely immutable and hashable,
    supporting reproducibility (Constitution Rule 9). File existence/validity is
    checked later at the ingestion boundary, not here.
    """

    model_config = ConfigDict(frozen=True)

    pov: tuple[Path, ...] = ()
    grn: tuple[Path, ...] = ()
    pv: tuple[Path, ...] = ()
    closing_stock: tuple[Path, ...] = ()

    def iter_with_kind(self) -> Iterator[tuple[Path, SourceKind]]:
        """Yield every (path, kind) pair across all four report groups.

        Ingestion will loop over this to dispatch each file to the right
        reader, so the (path, kind) pairing lives with the data, not in caller
        code.
        """
        for path in self.pov:
            yield path, SourceKind.POV
        for path in self.grn:
            yield path, SourceKind.GRN
        for path in self.pv:
            yield path, SourceKind.PV
        for path in self.closing_stock:
            yield path, SourceKind.CLOSING_STOCK

    @property
    def all_paths(self) -> tuple[Path, ...]:
        """All input paths across the four groups, in canonical order."""
        return self.pov + self.grn + self.pv + self.closing_stock


class WorkbookMeta(BaseModel):
    """Provenance and run statistics written to the Metadata sheet.

    Mirrors the Metadata sheet columns in WORKBOOK_SCHEMA.md and the authenticity
    controls in THREAT_MODEL.md. `generated_at` is the only sanctioned place for
    wall-clock time (Constitution Rule 9): it lives in metadata, never in
    business logic.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str
    application_version: str
    generated_at: datetime
    source_hash: str
    output_hash: str
    forecast_horizon: int = Field(gt=0)
    total_suppliers: int = Field(ge=0)
    total_items: int = Field(ge=0)
    total_records: int = Field(ge=0)
    processing_time_seconds: float = Field(ge=0.0)
