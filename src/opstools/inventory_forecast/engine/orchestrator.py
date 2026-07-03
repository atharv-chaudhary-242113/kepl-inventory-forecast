"""Engine orchestration and Business Intelligence aggregation.

Coordinates the execution of analytical models and synthesizes
their outputs into a unified AnalyticsSummary, which now acts
as the single source of truth for the Business Intelligence
platform.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime

import polars as pl

from opstools.inventory_forecast.config import Settings
from opstools.inventory_forecast.domain.enums import (
    AbcClass,
    ForecastModel,
    ForecastStatus,
    InventoryStatus,
    RiskLevel,
    SbcClass,
    SupplierDependencyLevel,
    TrendDirection,
)
from opstools.inventory_forecast.domain.models import (
    AbcClassification,
    AnalyticsSummary,
    DashboardPanelData,
    ExecutiveMetric,
    ForecastMetrics,
    ForecastResult,
    InventoryHealthReport,
    ProcurementInsight,
    ReplenishmentRecommendation,
    SourcingRiskReport,
    SupplierRisk,
)

# Core engine subsystems
from . import (
    classification,
    demand,
    financials,
    forecasting,
    inventory_health,
    lead_time,
    pending,
    reorder,
    supplier_risk,
    valuation,
)

logger = logging.getLogger(__name__)


def run_analytics_engine(
    pov_df: pl.DataFrame,
    grn_df: pl.DataFrame,
    pv_df: pl.DataFrame,
    closing_stock_df: pl.DataFrame,
    cfg: Settings,
) -> AnalyticsSummary:
    """Execute the core analytical engine and BI aggregation.

    Coordinates all subsystem calculations and synthesizes
    the Business Intelligence insights required by procurement
    managers.

    Args:
        pov_df: Validated purchase order data.
        grn_df: Validated goods receipt data.
        pv_df: Validated purchase voucher (financial) data.
        closing_stock_df: Validated closing stock levels.
        cfg: Runtime configuration and tunables.

    Returns:
        AnalyticsSummary containing all business metrics and BI data.
    """
    logger.info("Starting engine execution for Business Intelligence platform.")

    # 0. Convert eager ingestion frames to Polars LazyFrames for the engine
    pov = pov_df.lazy()
    grn = grn_df.lazy()
    pv = pv_df.lazy()
    stock = closing_stock_df.lazy()

    # 1. Base Computations
    logger.info("Computing lead times and demand history.")
    lead_times = lead_time.compute_lead_time(pov, grn)
    demand_history = demand.reconstruct_demand(pov)

    logger.info("Generating financials and pending deliveries.")
    financial_summary = financials.build_financial_summary(pv, cfg)
    pending_deliveries = pending.build_pending_deliveries(lead_times)

    logger.info("Classifying inventory.")
    demand_chars = classification.classify_sbc(demand_history)

    abc_df = classification.build_abc_classification(pv, cfg).collect()

    logger.info("Generating forecasts.")
    forecasts_df = forecasting.forecast_demand(
        demand=demand_history,
        sbc=demand_chars,
        horizon=cfg.forecast_horizon,
        cfg=cfg,
    ).collect()

    logger.info("Assessing supplier performance and risk.")
    supplier_risks_df = supplier_risk.build_supplier_analysis(
        lead_time=lead_times,
        pending=pending_deliveries,
        financial=financial_summary,
        cfg=cfg,
    ).collect()

    logger.info("Calculating inventory valuation and health.")
    inventory_val = valuation.build_inventory_valuation(
        stock, pv, snapshot_date=date(2025, 8, 5)
    )
    health_reports_df = inventory_health.build_inventory_health(
        valuation=inventory_val,
        demand=demand_history,
    ).collect()

    logger.info("Recommending replenishment.")
    replenishments_df = reorder.build_reorder_recommendations(
        demand=demand_history,
        lead_time=lead_times,
        cfg=cfg,
    ).collect()

    # 2. Domain Model Mapping
    logger.info("Mapping engine results to business domain models.")
    health_reports = _map_health(health_reports_df)
    replenishments = _map_replenishments(replenishments_df)
    forecast_results = _map_forecasts(forecasts_df)
    supplier_risks = _map_supplier_risks(supplier_risks_df)
    abc_classification = _map_abc(abc_df)

    # 3. Business Intelligence Aggregation
    logger.info("Synthesizing Business Intelligence insights.")

    sourcing_risks_list = _build_sourcing_risks(supplier_risks)
    executive_metrics = _build_executive_metrics(
        health_reports, supplier_risks, replenishments
    )
    procurement_insights = _build_procurement_insights(
        health_reports, sourcing_risks_list, replenishments
    )
    dashboard_data = _build_dashboard_data(
        forecast_results, health_reports, supplier_risks
    )

    return AnalyticsSummary(
        forecasts=tuple(forecast_results),
        supplier_risks=tuple(supplier_risks),
        replenishment_recommendations=tuple(replenishments),
        inventory_health=tuple(health_reports),
        abc_classification=tuple(abc_classification),
        executive_metrics=tuple(executive_metrics),
        dashboard_data=tuple(dashboard_data),
        procurement_insights=tuple(procurement_insights),
        sourcing_risks=tuple(sourcing_risks_list),
    )


def _map_health(df: pl.DataFrame) -> list[InventoryHealthReport]:
    """Map the eager inventory health DataFrame to domain models."""
    reports = []
    if df.height == 0:
        return reports
    for row in df.iter_rows(named=True):
        try:
            status_enum = InventoryStatus(
                row.get("status", InventoryStatus.HEALTHY.value)
            )
        except ValueError:
            status_enum = InventoryStatus.HEALTHY

        reports.append(
            InventoryHealthReport(
                item_id=str(row.get("item", "unknown")),
                status=status_enum,
                months_of_cover=float(row.get("months_of_cover") or 0.0),
                excess_inventory_value=float(row.get("excess_inventory_value") or 0.0),
            )
        )
    return reports


def _map_replenishments(df: pl.DataFrame) -> list[ReplenishmentRecommendation]:
    """Map the eager replenishment DataFrame to domain models."""
    recs = []
    if df.height == 0:
        return recs
    for row in df.iter_rows(named=True):
        rp = float(row.get("reorder_point") or 0.0)
        recs.append(
            ReplenishmentRecommendation(
                item_id=str(row.get("item", "unknown")),
                baseline_stock_level=rp,
                estimate_stock_level=0.0,
                replenishment_quantity=rp,
            )
        )
    return recs


def _map_supplier_risks(df: pl.DataFrame) -> list[SupplierRisk]:
    """Map the eager supplier risk DataFrame to domain models."""
    risks = []
    if df.height == 0:
        return risks
    for row in df.iter_rows(named=True):
        risk_val = float(row.get("risk_score") or 0.0)
        if risk_val > 0.8:
            risk_lvl = RiskLevel.CRITICAL
        elif risk_val > 0.5:
            risk_lvl = RiskLevel.HIGH
        elif risk_val > 0.2:
            risk_lvl = RiskLevel.MEDIUM
        else:
            risk_lvl = RiskLevel.LOW

        risks.append(
            SupplierRisk(
                supplier_id=str(row.get("supplier", "unknown")),
                item_id="ALL",  # Engine aggregates at supplier level
                dependency_level=SupplierDependencyLevel.DIVERSIFIED,
                risk_level=risk_lvl,
                supplier_count=1,
            )
        )
    return risks


def _map_forecasts(df: pl.DataFrame) -> list[ForecastResult]:
    """Map the eager forecast DataFrame to domain models."""
    results = []
    if df.height == 0:
        return results

    grouped: dict[str, dict[str, list[float] | str]] = {}
    for row in df.iter_rows(named=True):
        item = str(row.get("item", "unknown"))
        if item not in grouped:
            grouped[item] = {
                "model_used": str(row.get("model_used", "naive")),
                "values": [],
            }

        values_list = grouped[item]["values"]
        if isinstance(values_list, list):
            values_list.append(float(row.get("forecast_quantity") or 0.0))

    for item, data in grouped.items():
        model_str = str(data["model_used"])
        try:
            model_enum = ForecastModel(model_str)
        except ValueError:
            model_enum = ForecastModel.NAIVE

        vals = data["values"]
        if isinstance(vals, list):
            val_tuple = tuple(vals)
            results.append(
                ForecastResult(
                    item_id=item,
                    demand_class=SbcClass.NEW_ITEM,
                    selected_model=model_enum,
                    forecast_values=val_tuple,
                    lower_bound=tuple(0.0 for _ in val_tuple),
                    upper_bound=tuple(v * 1.2 for v in val_tuple),
                    metrics=ForecastMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 1),
                    status=ForecastStatus.SUCCESS,
                    generated_at=datetime.now(UTC),
                )
            )
    return results


def _map_abc(df: pl.DataFrame) -> list[AbcClassification]:
    """Map the eager ABC classification DataFrame to domain models."""
    classifications: list[AbcClassification] = []

    if df.height == 0:
        return classifications

    for row in df.iter_rows(named=True):
        classifications.append(
            AbcClassification(
                supplier_id=str(row["supplier"]),
                item_id=str(row["item"]),
                annual_value=row["annual_value"],
                quantityt_bought=int(row["quantityt_bought"]),
                revenue_percentage=float(row["revenue_percentage"]),
                cumulative_revenue_percentage=float(
                    row["cumulative_revenue_percentage"]
                ),
                quantity_percentage=float(row["quantity_percentage"]),
                cumulative_quantity_percentage=float(
                    row["cumulative_quantity_percentage"]
                ),
                abc_class=AbcClass(str(row["abc_class"])),
            )
        )

    return classifications


def _build_sourcing_risks(
    supplier_risks: Sequence[SupplierRisk],
) -> list[SourcingRiskReport]:
    """Aggregate supplier risks into item-centric sourcing risks."""
    risk_map: dict[str, list[SupplierRisk]] = {}
    for sr in supplier_risks:
        risk_map.setdefault(sr.item_id, []).append(sr)

    reports = []
    for item_id, risks in risk_map.items():
        if not risks:
            continue

        # Designate the first available as primary for BI reporting
        primary = risks[0]

        risk_levels = [r.risk_level for r in risks]
        if RiskLevel.CRITICAL in risk_levels:
            overall_risk = RiskLevel.CRITICAL
        elif RiskLevel.HIGH in risk_levels:
            overall_risk = RiskLevel.HIGH
        elif RiskLevel.MEDIUM in risk_levels:
            overall_risk = RiskLevel.MEDIUM
        else:
            overall_risk = RiskLevel.LOW

        reports.append(
            SourcingRiskReport(
                item_id=item_id,
                supplier_count=primary.supplier_count,
                primary_supplier=primary.supplier_id,
                dependency_level=primary.dependency_level,
                risk_level=overall_risk,
            )
        )

    return reports


def _build_executive_metrics(
    health_reports: Sequence[InventoryHealthReport],
    supplier_risks: Sequence[SupplierRisk],
    replenishments: Sequence[ReplenishmentRecommendation],
) -> list[ExecutiveMetric]:
    """Calculate top-level KPIs for the executive summary dashboard."""
    metrics = []

    # 1. Inventory Health
    overstocked = sum(
        1 for h in health_reports if h.status == InventoryStatus.OVERSTOCKED
    )
    stockouts = sum(1 for h in health_reports if h.status == InventoryStatus.LOW_STOCK)
    excess_value = sum(h.excess_inventory_value for h in health_reports)

    metrics.append(
        ExecutiveMetric(
            category="Inventory",
            metric_name="Total Excess Value",
            value=excess_value,
            trend=TrendDirection.FLAT,
            status="Warning" if excess_value > 10000 else "Healthy",
        )
    )
    metrics.append(
        ExecutiveMetric(
            category="Inventory",
            metric_name="Items Overstocked",
            value=float(overstocked),
            trend=TrendDirection.UP if overstocked > 0 else TrendDirection.FLAT,
            status="Action Required" if overstocked > 0 else "Healthy",
        )
    )
    metrics.append(
        ExecutiveMetric(
            category="Inventory",
            metric_name="Items Facing Stockout",
            value=float(stockouts),
            trend=TrendDirection.UP if stockouts > 0 else TrendDirection.FLAT,
            status="Critical" if stockouts > 0 else "Healthy",
        )
    )

    # 2. Supplier Risk
    critical_suppliers = sum(
        1 for r in supplier_risks if r.risk_level == RiskLevel.CRITICAL
    )
    metrics.append(
        ExecutiveMetric(
            category="Procurement",
            metric_name="Critical Risk Suppliers",
            value=float(critical_suppliers),
            trend=TrendDirection.FLAT,
            status="Critical" if critical_suppliers > 0 else "Healthy",
        )
    )

    # 3. Replenishment Needs
    total_replenishment_qty = sum(r.replenishment_quantity for r in replenishments)
    metrics.append(
        ExecutiveMetric(
            category="Procurement",
            metric_name="Pending Replenishment Volume",
            value=total_replenishment_qty,
            trend=TrendDirection.UP,
            status="Normal",
        )
    )

    return metrics


def _build_procurement_insights(
    health_reports: Sequence[InventoryHealthReport],
    sourcing_risks: Sequence[SourcingRiskReport],
    replenishments: Sequence[ReplenishmentRecommendation],
) -> list[ProcurementInsight]:
    """Generate actionable insights and alerts for procurement managers."""
    insights = []

    # Dead stock alert
    dead_stock_items = [
        h for h in health_reports if h.status == InventoryStatus.DEAD_STOCK
    ]
    if dead_stock_items:
        impact = sum(h.excess_inventory_value for h in dead_stock_items)
        insights.append(
            ProcurementInsight(
                insight_type="Dead Stock Alert",
                priority=RiskLevel.HIGH,
                description=f"Identified {len(dead_stock_items)} items as dead stock.",
                affected_items=len(dead_stock_items),
                potential_impact=impact,
            )
        )

    # Single-source critical dependencies
    single_source = [
        r
        for r in sourcing_risks
        if r.dependency_level == SupplierDependencyLevel.SINGLE_SOURCE
    ]
    if single_source:
        insights.append(
            ProcurementInsight(
                insight_type="Sourcing Vulnerability",
                priority=RiskLevel.CRITICAL,
                description=f"{len(single_source)} items rely on a single supplier.",
                affected_items=len(single_source),
                potential_impact=0.0,
            )
        )

    # Immediate stockout risks
    immediate_needs = [
        r
        for r in replenishments
        if r.estimate_stock_level < (r.baseline_stock_level * 0.2)
    ]
    if immediate_needs:
        insights.append(
            ProcurementInsight(
                insight_type="Stockout Risk",
                priority=RiskLevel.HIGH,
                description=f"{len(immediate_needs)} items are severely "
                f"below baseline stock levels.",
                affected_items=len(immediate_needs),
                potential_impact=0.0,
            )
        )

    return insights


def _build_dashboard_data(
    forecasts: Sequence[ForecastResult],
    health_reports: Sequence[InventoryHealthReport],
    supplier_risks: Sequence[SupplierRisk],
) -> list[DashboardPanelData]:
    """Pre-compute flattened data for Plotly dashboard generation."""
    panels = []

    # Panel: Inventory Health Distribution
    health_counts: dict[InventoryStatus, int] = {}
    for h in health_reports:
        health_counts[h.status] = health_counts.get(h.status, 0) + 1

    total_items = len(health_reports) or 1
    for status, count in health_counts.items():
        panels.append(
            DashboardPanelData(
                panel_id="inventory_health_pie",
                dimension=status.value.title(),
                metric="Item Count",
                value=float(count),
                percentage=(count / total_items) * 100.0,
            )
        )

    # Panel: Risk Level Distribution
    risk_counts: dict[RiskLevel, int] = {}
    for r in supplier_risks:
        risk_counts[r.risk_level] = risk_counts.get(r.risk_level, 0) + 1

    total_risks = len(supplier_risks) or 1
    for level, count in risk_counts.items():
        panels.append(
            DashboardPanelData(
                panel_id="supplier_risk_bar",
                dimension=level.value.title(),
                metric="Supplier Count",
                value=float(count),
                percentage=(count / total_risks) * 100.0,
            )
        )

    # Panel: Forecast Model Usage
    model_counts: dict[str, int] = {}
    for f in forecasts:
        model_counts[f.selected_model.value] = (
            model_counts.get(f.selected_model.value, 0) + 1
        )

    total_forecasts = len(forecasts) or 1
    for model, count in model_counts.items():
        panels.append(
            DashboardPanelData(
                panel_id="forecast_model_usage",
                dimension=model.upper(),
                metric="Selection Count",
                value=float(count),
                percentage=(count / total_forecasts) * 100.0,
            )
        )

    return panels
