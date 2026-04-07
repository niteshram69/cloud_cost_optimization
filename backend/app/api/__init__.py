from backend.app.api.admin import router as admin_router
from backend.app.api.auth import router as auth_router
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.ingest import router as ingest_router
from backend.app.api.migrations import router as migrations_router
from backend.app.api.platform import router as platform_router
from backend.app.api.pricing import router as pricing_router

__all__ = [
    "admin_router",
    "auth_router",
    "dashboard_router",
    "ingest_router",
    "migrations_router",
    "platform_router",
    "pricing_router",
]
