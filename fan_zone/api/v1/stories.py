"""FastAPI REST endpoints for synthesized, copyright-safe sports stories."""

import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.db.session import get_db
from fan_zone.models.story import Story
from fan_zone.repositories.story_repo import StoryRepository
from fan_zone.schemas.story import (
    PaginatedStoryResponse,
    StoryCitation,
    StoryDetailSchema,
    StorySummarySchema,
    SynthesizeResponse,
)
from fan_zone.services.story_service import StoryService

router = APIRouter()


def serialize_story(story: Story) -> StorySummarySchema:
    """Helper converting an ORM Story entity into a StorySummarySchema."""
    citations = [
        StoryCitation(
            article_id=c.get("article_id"),
            source_name=c.get("source_name", "מקור"),
            source_code=c.get("source_code"),
            publisher=c.get("publisher", c.get("source_name", "מקור")),
            original_title=c.get("original_title", ""),
            url=c.get("url", ""),
            published_at=c.get("published_at"),
        )
        for c in (story.citations_json or [])
    ]

    return StorySummarySchema(
        id=story.id,
        title=story.title,
        summary=story.summary,
        sport=story.sport,
        competition=story.competition,
        teams=story.teams_json or [],
        players=story.players_json or [],
        tags=story.tags_json or [],
        lead_image_url=story.lead_image_url,
        lead_image_caption=story.lead_image_caption,
        lead_image_credit=story.lead_image_credit,
        citations=citations,
        article_count=story.article_count,
        published_at=story.published_at,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


@router.get("", response_model=PaginatedStoryResponse, summary="List synthesized sports stories")
async def list_stories(
    sport: Optional[str] = Query(None, description="Filter by sport category (e.g. כדורגל, כדורסל)"),
    team: Optional[str] = Query(None, description="Filter by club or team name"),
    competition: Optional[str] = Query(None, description="Filter by tournament or league"),
    tag: Optional[str] = Query(None, description="Filter by topic or entity tag"),
    q: Optional[str] = Query(None, alias="search_query", description="Search query in title or summary"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, alias="limit", description="Items per page"),
    sort_by: str = Query("published_at", description="Sort field (published_at, id)"),
    order: str = Query("desc", description="Sort order: desc or asc"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedStoryResponse:
    """Returns paginated, multi-source synthesized sports news stories with full publisher citations."""
    repo = StoryRepository(db)
    sort_desc = order.strip().lower() != "asc"
    skip = (page - 1) * page_size

    stories, total = await repo.list_stories(
        sport=sport,
        team=team,
        competition=competition,
        tag=tag,
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


@router.get("/{id}", response_model=StoryDetailSchema, summary="Get synthesized story detail")
async def get_story(
    id: int,
    db: AsyncSession = Depends(get_db),
) -> StoryDetailSchema:
    """Retrieves full details of a synthesized story, including multi-source citations."""
    repo = StoryRepository(db)
    story = await repo.get_by_id(id, db=db)
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story with ID {id} not found",
        )
    return serialize_story(story)


@router.post("/synthesize", response_model=SynthesizeResponse, summary="Trigger multi-source story synthesis")
async def trigger_story_synthesis(
    limit: int = Query(50, ge=1, le=200, description="Max recent articles to evaluate"),
    db: AsyncSession = Depends(get_db),
) -> SynthesizeResponse:
    """Clusters ingested articles across publishers and synthesizes structured briefs with citations."""
    service = StoryService(db=db)
    results = await service.synthesize_all_pending(limit=limit)

    return SynthesizeResponse(
        status="success",
        stories_created=results["stories_created"],
        stories_updated=results["stories_updated"],
        message=f"Synthesis complete: created {results['stories_created']} story briefs.",
    )
