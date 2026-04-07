from __future__ import annotations

from collections.abc import AsyncGenerator
import os

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import settings


def _resolve_async_database_url() -> str:
    explicit = os.getenv("ASYNC_DATABASE_URL")
    if explicit:
        return explicit

    url = str(settings.database_url)
    if url.startswith("mysql+aiomysql://") or url.startswith("mysql+asyncmy://"):
        return url
    if url.startswith("mysql+pymysql://"):
        return "mysql+aiomysql://" + url[len("mysql+pymysql://") :]
    if url.startswith("mysql://"):
        return "mysql+aiomysql://" + url[len("mysql://") :]
    return ""


ASYNC_DATABASE_URL = _resolve_async_database_url()
async_engine = (
    create_async_engine(ASYNC_DATABASE_URL, pool_pre_ping=True, future=True)
    if ASYNC_DATABASE_URL
    else None
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
) if async_engine is not None else None


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Async MySQL database is not configured. "
                "Set ASYNC_DATABASE_URL with mysql+aiomysql:// or mysql+asyncmy://"
            ),
        )

    async with AsyncSessionLocal() as session:
        yield session
