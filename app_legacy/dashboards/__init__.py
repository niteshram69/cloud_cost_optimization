"""Dashboards package."""

from app.dashboards.schemas import AdminDashboardResponse, ClientDashboardResponse
from app.dashboards.service import DashboardAggregationService

__all__ = ["AdminDashboardResponse", "ClientDashboardResponse", "DashboardAggregationService"]
