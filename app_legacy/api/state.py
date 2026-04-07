"""In-memory optimization report store used by dashboard APIs.

In production, replace with a persistent warehouse (e.g., ClickHouse, BigQuery,
Snowflake, or Postgres) and tenant-isolated RBAC.
"""

from __future__ import annotations

import asyncio
from collections import deque

from app.decision_engine.models import OptimizationReport


class OptimizationReportStore:
    """Thread-safe in-memory store for recent optimization reports."""

    def __init__(self, max_reports: int = 500):
        self._reports: deque[OptimizationReport] = deque(maxlen=max_reports)
        self._lock = asyncio.Lock()

    async def add(self, report: OptimizationReport) -> None:
        async with self._lock:
            self._reports.append(report)

    async def list_all(self) -> list[OptimizationReport]:
        async with self._lock:
            return list(self._reports)


report_store = OptimizationReportStore()
