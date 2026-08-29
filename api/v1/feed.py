"""FastAPI REST endpoints for personalized fan feed."""

import math
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.api.v1.stories import serialize_story
from fan_zone.db.session import get_db
from fan_zone.repositories.story_repo import StoryRepository
from fan_zone.schemas.story import PaginatedStoryResponse

router = APIRouter()


@router.get("", response_model=PaginatedStoryResponse, summary="Personalized fan news feed")
async def get_fan_feed(
    sports: Optional[List[str]] = Query(None, description="Filter by favorite sports (multi-select)"),
    teams: Optional[List[str]] = Query(None, description="Filter by favorite teams (multi-select)"),
    competitions: Optional[List[str]] = Query(None, description="Filter by favorite competitions (multi-select)"),
    tags: Optional[List[str]] = Query(None, description="Filter by favorite topic tags (multi-select)"),
    q: Optional[str] = Query(None, alias="search_query", description="Keyword search in title or summary"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, alias="limit", description="Items per page"),
    sort_by: str = Query("published_at", description="Sort field (published_at, id)"),
    order: str = Query("desc", description="Sort order: desc or asc"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedStoryResponse:
    """Returns a tailored, personalized sports news feed filtered by fan preferences
    (favorite teams, sports, leagues), containing copyright-safe synthesized story briefs
    with full publisher citations.
    """
    repo = StoryRepository(db)
    sort_desc = order.strip().lower() != "asc"
    skip = (page - 1) * page_size

    stories, total = await repo.list_stories(
        sports=sports,
        teams=teams,
        competitions=competitions,
        tags=tags,
        search_query=q,
        skip=skip,
        limit=page_size,
        sort_by=sort_by,
        sort_desc=sort_desc,
        db=db,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1

    items = [serialize_story(s) for s in stories]

    return PaginatedStoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=has_next,
        has_prev=has_prev,
    )
