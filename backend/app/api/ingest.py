from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database_async import get_async_db
from backend.app.schemas.ingest import IngestRequest, IngestResponse
from backend.app.services.ingest_service import IngestService

router = APIRouter(tags=["finops-ingestion"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_resources(
    payload: IngestRequest,
    db: AsyncSession = Depends(get_async_db),
) -> IngestResponse:
    service = IngestService(db=db)
    return await service.ingest(payload)
