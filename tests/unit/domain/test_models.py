"""Unit tests for domain DTOs and enums."""

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError  # Pydantic's, not our domain ValidationError

from opstools.inventory_forecast.domain.enums import AbcClass, SbcClass, SourceKind
from opstools.inventory_forecast.domain.models import SourceSet, WorkbookMeta


def test_enum_string_values():
    assert SourceKind.POV == "pov"
    assert SourceKind.CLOSING_STOCK == "closing_stock"
    assert AbcClass.A == "A"
    assert SbcClass.LUMPY == "lumpy"


def test_source_set_iter_with_kind_pairs_paths_to_kinds():
    sources = SourceSet(
        pov=(Path("pov_2024.xlsx"),),
        grn=(Path("grn_2024.xlsx"),),
        pv=(Path("pv_2024.xlsx"),),
        closing_stock=(Path("stock_2024.xlsx"),),
    )
    pairs = list(sources.iter_with_kind())
    assert pairs == [
        (Path("pov_2024.xlsx"), SourceKind.POV),
        (Path("grn_2024.xlsx"), SourceKind.GRN),
        (Path("pv_2024.xlsx"), SourceKind.PV),
        (Path("stock_2024.xlsx"), SourceKind.CLOSING_STOCK),
    ]
    assert sources.all_paths == tuple(p for p, _ in pairs)


def test_source_set_is_frozen():
    sources = SourceSet()
    with pytest.raises(ValidationError):
        sources.pov = (Path("x.xlsx"),)  # frozen model => assignment rejected


def test_workbook_meta_holds_documented_fields():
    meta = WorkbookMeta(
        schema_version="1.0.0",
        application_version="0.1.0",
        generated_at=datetime(2026, 1, 1, 12, 0, 0),
        source_hash="abc",
        output_hash="def",
        forecast_horizon=12,
        total_suppliers=3,
        total_items=42,
        total_records=1000,
        processing_time_seconds=4.2,
    )
    assert meta.forecast_horizon == 12
    assert meta.total_items == 42


def test_workbook_meta_rejects_nonpositive_horizon():
    with pytest.raises(ValidationError):
        WorkbookMeta(
            schema_version="1.0.0",
            application_version="0.1.0",
            generated_at=datetime(2026, 1, 1),
            source_hash="abc",
            output_hash="def",
            forecast_horizon=0,
            total_suppliers=3,
            total_items=42,
            total_records=1000,
            processing_time_seconds=4.2,
        )
