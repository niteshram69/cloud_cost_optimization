"""FastAPI application factory and lifespan management."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.router import router as v2_router
from app.core.config import settings
from app.core.constants import API_V1_PREFIX
from app.core.error_handlers import add_exception_handlers
from app.core.logging import configure_logging
from app.core.monitoring import get_metrics_response
from app.modules.auth.router import limiter as auth_limiter
from app.modules.auth.router import router as auth_router
from app.modules.classification.router import router as classification_router
from app.modules.cost.router import router as cost_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.decisions.router import router as decisions_router
from app.modules.ingestion.router import router as ingestion_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events: startup and shutdown."""
    # Startup: Initialize logging, connections, etc.
    configure_logging()
    
    yield
    
    # Shutdown: Cleanup resources
    pass


def create_application() -> FastAPI:
    """Factory function to create and configure FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="API for cloud cost optimization, classification, and decision-making",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )
    
    # CORS middleware (restrict in production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.DEBUG else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiter middleware and exception handling
    app.state.limiter = auth_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    
    # Root endpoint
    @app.get("/", tags=["info"])
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENVIRONMENT,
            "docs_url": "/docs" if settings.DEBUG else None,
            "redoc_url": "/redoc" if settings.DEBUG else None,
            "health_check_url": "/health",
        }
    
    # Health check endpoint (no auth required)
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "healthy", "version": settings.APP_VERSION}

    @app.get(settings.METRICS_ENDPOINT, include_in_schema=False)
    async def metrics():
        return get_metrics_response()
    
    # Include API routers
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    app.include_router(ingestion_router, prefix=API_V1_PREFIX)
    app.include_router(classification_router, prefix=API_V1_PREFIX)
    app.include_router(cost_router, prefix=API_V1_PREFIX)
    app.include_router(decisions_router, prefix=API_V1_PREFIX)
    app.include_router(dashboard_router, prefix=API_V1_PREFIX)
    app.include_router(v2_router)
    
    # Add global exception handlers
    add_exception_handlers(app)
    
    return app


# Create application instance
app = create_application()
