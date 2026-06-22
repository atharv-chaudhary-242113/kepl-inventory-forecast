"""Sourcing-risk analytics per item.

DOMAIN_RULES.md lists alternative-supplier availability and supplier dependency
among the supplier-risk factors. This module measures, for each item, how
concentrated its procurement spend is across suppliers: a single-source or
highly-concentrated item is more exposed to a supplier failure. Dependency and
risk are expressed with the SupplierDependencyLevel / RiskLevel enums. Spend stays
Decimal-exact. Pure over Polars LazyFrames.
"""

import polars as pl

from opstools.inventory_forecast.domain import RiskLevel, SupplierDependencyLevel

# Decimal money scale (ingestion/schema.py MONEY_SCALE).
_MONEY: pl.datatypes.DataTypeClass | pl.Decimal = pl.Decimal(scale=4)

# Concentration cut-points on the top supplier's spend share (pending business
# validation, DOMAIN_RULES.md "Supplier risk weighting methodology").
_CONCENTRATED_SHARE: float = 0.80
_MODERATE_SHARE: float = 0.50


def build_sourcing_risk(pv: pl.LazyFrame) -> pl.LazyFrame:
    """Classify each item by how concentrated its supplier base is.

    Args:
        pv: Canonical PV ledger — the authoritative spend source (DOMAIN_RULES.md).

    Returns:
        A LazyFrame ``[item, supplier_count(Int64), total_spend(Decimal),
        top_supplier_share(Float64), dependency_level(Utf8), risk_level(Utf8)]``,
        sorted by item. ``top_supplier_share`` is the largest single supplier's
        fraction of the item's total spend.
    """
    per_supplier = pv.group_by(["item", "supplier"]).agg(
        pl.col("amount").sum().alias("_supplier_spend")
    )

    per_item = per_supplier.group_by("item").agg(
        pl.len().alias("supplier_count"),
        pl.col("_supplier_spend").sum().alias("total_spend"),
        pl.col("_supplier_spend").max().alias("_top_spend"),
    )

    return (
        per_item.with_columns(
            # Decimal / Decimal share, then cast to Float64 for a presentation ratio.
            pl.when(pl.col("total_spend") > pl.lit(0, dtype=_MONEY))
            .then((pl.col("_top_spend") / pl.col("total_spend")).cast(pl.Float64))
            .otherwise(0.0)
            .alias("top_supplier_share")
        )
        .with_columns(_dependency_expr())
        .with_columns(_risk_expr())
        .select(
            [
                "item",
                pl.col("supplier_count").cast(pl.Int64),
                "total_spend",
                "top_supplier_share",
                "dependency_level",
                "risk_level",
            ]
        )
        .sort("item")
    )


def _dependency_expr() -> pl.Expr:
    """Map supplier_count + top-share onto a SupplierDependencyLevel."""
    share = pl.col("top_supplier_share")
    return (
        pl.when(pl.col("supplier_count") <= 1)
        .then(pl.lit(SupplierDependencyLevel.SINGLE_SOURCE.value))
        .when(share >= _CONCENTRATED_SHARE)
        .then(pl.lit(SupplierDependencyLevel.CONCENTRATED.value))
        .when(share >= _MODERATE_SHARE)
        .then(pl.lit(SupplierDependencyLevel.MODERATE.value))
        .otherwise(pl.lit(SupplierDependencyLevel.DIVERSIFIED.value))
        .alias("dependency_level")
    )


def _risk_expr() -> pl.Expr:
    """Map a dependency level onto a RiskLevel (higher concentration = higher risk)."""
    level = pl.col("dependency_level")
    return (
        pl.when(level == SupplierDependencyLevel.SINGLE_SOURCE.value)
        .then(pl.lit(RiskLevel.CRITICAL.value))
        .when(level == SupplierDependencyLevel.CONCENTRATED.value)
        .then(pl.lit(RiskLevel.HIGH.value))
        .when(level == SupplierDependencyLevel.MODERATE.value)
        .then(pl.lit(RiskLevel.MEDIUM.value))
        .otherwise(pl.lit(RiskLevel.LOW.value))
        .alias("risk_level")
    )
