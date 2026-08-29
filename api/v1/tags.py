"""FastAPI REST endpoints for sports entity tags and taxonomy."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.db.session import get_db
from fan_zone.repositories.tag_repo import TagRepository
from fan_zone.schemas.tag import TagSchema

router = APIRouter()


@router.get("", response_model=List[TagSchema], summary="List and search entity tags")
async def list_tags(
    type: Optional[str] = Query(None, description="Filter by tag type: sport, team, player, competition, topic, general"),
    tag_type: Optional[str] = Query(None, description="Alias for type filter"),
    q: Optional[str] = Query(None, description="Search tag name substring"),
    search_query: Optional[str] = Query(None, description="Alias for q keyword search"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of tags to return"),
    db: AsyncSession = Depends(get_db),
) -> List[TagSchema]:
    """Lists extracted entity taxonomy tags with optional type filtering and search."""
    effective_type = type or tag_type
    effective_q = q or search_query
    repo = TagRepository(db)
    tags = await repo.list_tags(tag_type=effective_type, search_query=effective_q, limit=limit, db=db)
    return [TagSchema.model_validate(t) for t in tags]


@router.get("/popular", response_model=List[TagSchema], summary="Get most popular entity tags")
async def get_popular_tags(
    limit: int = Query(20, ge=1, le=100, description="Number of popular tags to return"),
    db: AsyncSession = Depends(get_db),
) -> List[TagSchema]:
    """Returns the top entity tags ranked by total article association count."""
    repo = TagRepository(db)
    tags = await repo.get_popular_tags(limit=limit, db=db)
    return [TagSchema.model_validate(t) for t in tags]
