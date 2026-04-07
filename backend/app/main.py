from __future__ import annotations

import time
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func

from backend.app.api import admin_router, auth_router, dashboard_router, ingest_router, migrations_router, platform_router, pricing_router
from backend.app.core.config import settings
from backend.app.database import Base, SessionLocal, engine
from backend.app.models import (
    APIKey,
    BillingCycle,
    IngestedRecord,
    MigrationJob,
    MigrationStatus,
    User,
    WebhookEvent,
    WebhookProcessStatus,
)
from backend.app.services.auth_service import AuthService
from backend.app.services.platform_bootstrap_service import PlatformBootstrapService

logger = logging.getLogger(__name__)

APP_START_TIME = time.monotonic()

REQUEST_COUNT = Counter(
    "cloudteck_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "cloudteck_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5],
)
ACTIVE_USERS_GAUGE = Gauge("cloudteck_active_users_total", "Active user count")
RUNNING_MIGRATIONS_GAUGE = Gauge("cloudteck_running_migrations_total", "Running migrations count")
INGESTED_RECORDS_GAUGE = Gauge("cloudteck_ingested_records_total", "Ingested records count")
ACTIVE_API_KEYS_GAUGE = Gauge("cloudteck_active_api_keys_total", "Active API keys count")
ESTIMATED_REVENUE_GAUGE = Gauge("cloudteck_estimated_revenue_total", "Estimated invoiced revenue total")
WEBHOOK_FAILURES_GAUGE = Gauge("cloudteck_webhook_failures_total", "Failed webhook events")


def get_uptime_seconds() -> float:
    return time.monotonic() - APP_START_TIME


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        PlatformBootstrapService(db).bootstrap()
        if settings.bootstrap_admin_enabled:
            admin_user = AuthService(db).bootstrap_admin_user()
            logger.info("Bootstrap admin ready: %s", admin_user.email)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.project_name,
    version="1.0.0",
    description=settings.project_tagline,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = exc.errors()
    first_message = "Validation failed"
    if details:
        first = details[0]
        loc = ".".join(str(item) for item in first.get("loc", []) if item is not None)
        msg = str(first.get("msg", "Validation failed"))
        first_message = f"{loc}: {msg}" if loc else msg
    return JSONResponse(
        status_code=422,
        content={
            "detail": first_message,
            "error": {
                "code": "validation_error",
                "message": "Validation failed",
                "details": details,
            },
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Unexpected internal error",
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred. Contact support with request trace.",
            },
        },
    )


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start

    endpoint = request.url.path
    REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status=str(response.status_code)).inc()
    REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(elapsed)

    return response


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.project_name,
        "tagline": settings.project_tagline,
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    # Grafana/Prometheus scrape-friendly endpoint.
    from backend.app.database import SessionLocal

    db = SessionLocal()
    try:
        active_users = db.query(User).filter(User.is_active.is_(True)).count()
        running_migrations = db.query(MigrationJob).filter(MigrationJob.status == MigrationStatus.RUNNING).count()
        ingested_records = db.query(IngestedRecord).count()
        active_api_keys = db.query(APIKey).filter(APIKey.is_active.is_(True)).count()
        estimated_revenue = db.query(func.sum(BillingCycle.total_amount)).scalar() or 0
        webhook_failures = db.query(WebhookEvent).filter(WebhookEvent.status == WebhookProcessStatus.FAILED).count()
        ACTIVE_USERS_GAUGE.set(active_users)
        RUNNING_MIGRATIONS_GAUGE.set(running_migrations)
        INGESTED_RECORDS_GAUGE.set(ingested_records)
        ACTIVE_API_KEYS_GAUGE.set(active_api_keys)
        ESTIMATED_REVENUE_GAUGE.set(float(estimated_revenue))
        WEBHOOK_FAILURES_GAUGE.set(webhook_failures)
    finally:
        db.close()

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(admin_router)
app.include_router(ingest_router)
app.include_router(migrations_router)
app.include_router(platform_router)
app.include_router(pricing_router)
