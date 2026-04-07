# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

# Security: Run as non-root user
RUN groupadd -r costintel && useradd -r -g costintel costintel

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.5

# Configure Poetry: Don't create virtual environment in container
RUN poetry config virtualenvs.create false

# Copy dependency files first (for layer caching)
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev dependencies in production)
RUN poetry install --no-dev --no-interaction --no-ansi

# Copy application code
COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY celery_worker.py alembic.ini ./

# Create upload directory with proper permissions
RUN mkdir -p /app/uploads && chown -R costintel:costintel /app

# Switch to non-root user
USER costintel

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default command (can be overridden)
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
