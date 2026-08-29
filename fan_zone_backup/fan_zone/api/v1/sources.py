"""FastAPI REST endpoints for sports news sources."""

from typing import List, Union
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.db.session import get_db
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.schemas.source import SourceRead, SourceStatSchema

router = APIRouter()


@router.get("", response_model=List[SourceStatSchema], summary="List all monitored news sources")
async def list_sources(
    db: AsyncSession = Depends(get_db),
) -> List[SourceStatSchema]:
    """Returns all 7 configured Israeli sports news outlets along with current
    operational status, polling timestamps, and total ingested article counts.
    """
    repo = SourceRepository(db)
    return await repo.get_stats(db=db)


@router.get("/{source_id_or_code}", response_model=SourceRead, summary="Get source details by ID or code")
async def get_source(
    source_id_or_code: str,
    db: AsyncSession = Depends(get_db),
) -> SourceRead:
    """Retrieves source configuration by numeric ID or machine code (e.g. 'sport5', 'one', 'walla')."""
    repo = SourceRepository(db)
    
    source = None
    if source_id_or_code.isdigit():
        source = await repo.get_by_id(int(source_id_or_code), db=db)
    
    if not source:
        source = await repo.get_by_name(source_id_or_code, db=db)

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id_or_code}' not found",
        )

    return SourceRead.model_validate(source)
