"""Global exception handlers for FastAPI."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    CostIntelException,
    DuplicateResourceError,
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
    WebhookDeliveryError,
)
from app.core.logging import configure_logging
import structlog

logger = structlog.get_logger()


def add_exception_handlers(app: FastAPI) -> None:
    """Add global exception handlers to the FastAPI application."""
    
    @app.exception_handler(CostIntelException)
    async def handle_costintel_exception(
        request: Request,
        exc: CostIntelException,
    ):
        """Handle all application-specific exceptions."""
        logger.warning(
            "Application exception",
            error=exc.message,
            status_code=exc.status_code,
            path=request.url.path,
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.__class__.__name__,
                    "message": exc.message,
                    "status_code": exc.status_code,
                }
            },
        )
    
    @app.exception_handler(Exception)
    async def handle_generic_exception(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        logger.error(
            "Unhandled exception",
            error=str(exc),
            path=request.url.path,
            exc_info=True,
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "InternalServerError",
                    "message": "An unexpected error occurred. Our team has been notified.",
                    "status_code": 500,
                }
            },
        )
