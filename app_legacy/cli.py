"""Console entrypoints used by Poetry scripts."""

from __future__ import annotations

import subprocess

import uvicorn


def start() -> None:
    """Start FastAPI server with autoreload for local development."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


def worker() -> None:
    """Start Celery worker process."""
    raise SystemExit(
        subprocess.call(["celery", "-A", "celery_worker", "worker", "--loglevel=info"])
    )


def beat() -> None:
    """Start Celery beat scheduler."""
    raise SystemExit(
        subprocess.call(["celery", "-A", "celery_worker", "beat", "--loglevel=info"])
    )


def flower() -> None:
    """Start Flower monitoring UI."""
    raise SystemExit(
        subprocess.call(["celery", "-A", "celery_worker", "flower", "--port=5555"])
    )


def migrate() -> None:
    """Apply latest Alembic migrations."""
    raise SystemExit(subprocess.call(["alembic", "upgrade", "head"]))


def makemigrations() -> None:
    """Generate an autogeneration migration skeleton."""
    raise SystemExit(subprocess.call(["alembic", "revision", "--autogenerate"]))
