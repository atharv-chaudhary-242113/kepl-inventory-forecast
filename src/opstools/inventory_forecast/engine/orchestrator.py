"""Engine orchestration and Business Intelligence aggregation.

Coordinates the execution of analytical models and synthesizes
their outputs into a unified AnalyticsSummary, which now acts
as the single source of truth for the Business Intelligence
platform.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import polars as pl

from opstools.inventory_forecast.domain.enums import (
    InventoryStatus,
    RiskLevel,
    SupplierDependencyLevel,
    TrendDirection,
)
from opstools.inventory_forecast.domain.models import (
    AnalyticsSummary,
    DashboardPanelData,
    ExecutiveMetric,
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
    forecasting,
    inventory_health,
    lead_time,
    reorder,
    supplier_risk,
)

logger = logging.getLogger(__name__)


def run_analytics_engine(
    pov_df: pl.DataFrame,
    grn_df: pl.DataFrame,
    pv_df: pl.DataFrame,
    closing_stock_df: pl.DataFrame,
    forecast_horizon: int,
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
        forecast_horizon: Number of periods to forecast.

    Returns:
        AnalyticsSummary containing all business metrics and BI data.
    """
    logger.info("Starting engine execution for Business Intelligence platform.")

    # 1. Base Computations
    logger.info("Computing lead times and demand history.")
    # pyrefly: ignore [missing-attribute]
    lead_times = lead_time.calculate_lead_times(pov_df, grn_df)
    # pyrefly: ignore [bad-argument-count, bad-argument-type]
    demand_history = demand.reconstruct_demand(pov_df, grn_df)

    logger.info("Classifying inventory.")
    # pyrefly: ignore [missing-attribute]
    demand_chars = classification.classify_demand(demand_history)
    # pyrefly: ignore [missing-attribute]
    _ = classification.classify_abc(pv_df, closing_stock_df)  # Internal use or caching

    logger.info("Generating forecasts.")
    # pyrefly: ignore [missing-attribute]
    forecasts = forecasting.generate_forecasts(
        demand_history, demand_chars, forecast_horizon
    )

    logger.info("Assessing supplier performance and risk.")
    # pyrefly: ignore [missing-attribute]
    _ = lead_time.evaluate_performance(lead_times)
    # pyrefly: ignore [missing-attribute]
    supplier_risks = supplier_risk.assess_risks(pov_df)

    logger.info("Calculating inventory health and replenishment.")
    # pyrefly: ignore [missing-attribute]
    health_reports = inventory_health.assess_health(closing_stock_df, forecasts)
    # pyrefly: ignore [missing-attribute]
    replenishments = reorder.recommend_replenishment(
        closing_stock_df, forecasts, lead_times
    )

    # 2. Business Intelligence Aggregation
    logger.info("Synthesizing Business Intelligence insights.")

    sourcing_risks_list = _build_sourcing_risks(supplier_risks)
    executive_metrics = _build_executive_metrics(
        health_reports, supplier_risks, replenishments
    )
    procurement_insights = _build_procurement_insights(
        health_reports, sourcing_risks_list, replenishments
    )
    dashboard_data = _build_dashboard_data(forecasts, health_reports, supplier_risks)

    return AnalyticsSummary(
        forecasts=tuple(forecasts),
        supplier_risks=tuple(supplier_risks),
        replenishment_recommendations=tuple(replenishments),
        inventory_health=tuple(health_reports),
        executive_metrics=tuple(executive_metrics),
        dashboard_data=tuple(dashboard_data),
        procurement_insights=tuple(procurement_insights),
        sourcing_risks=tuple(sourcing_risks_list),
    )


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
