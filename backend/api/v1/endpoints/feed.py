"""FastAPI endpoints for querying and filtering sports news feed cards."""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status

from api.deps import get_article_repository
from db.repository import ArticleRepository
from schemas.feed import (
    FeedItemResponse,
    PaginatedFeedResponse,
    ToneEnum,
    UserPreferences,
)

router = APIRouter()


def _parse_comma_separated_list(items: Optional[List[str]]) -> Optional[List[str]]:
    """Parse list of strings that may contain comma-separated entries into a clean flat list."""
    if not items:
        return None
    cleaned_items: List[str] = []
    for item in items:
        if isinstance(item, str):
            for sub_item in item.split(","):
                val = sub_item.strip()
                if val:
                    cleaned_items.append(val)
    return list(dict.fromkeys(cleaned_items)) if cleaned_items else None


@router.get(
    "",
    response_model=PaginatedFeedResponse,
    summary="Retrieve paginated and filtered sports feed",
    description="Query sports news articles with multi-criteria filtering by tags, publisher, date range, tone, and search text.",
)
async def get_feed(
    tags: Optional[List[str]] = Query(
        default=None,
        description="Filter by team, league, or sport tags. Supports multiple query parameters or comma-separated values.",
    ),
    publisher: Optional[List[str]] = Query(
        default=None,
        description="Filter by publisher identifier(s) (e.g. 'sport5', 'ynet', 'one'). Supports multiple params or comma-separated values.",
    ),
    date_from: Optional[datetime] = Query(
        default=None,
        description="Filter articles published on or after this timestamp (ISO 8601).",
    ),
    date_to: Optional[datetime] = Query(
        default=None,
        description="Filter articles published on or before this timestamp (ISO 8601).",
    ),
    tone: Optional[ToneEnum] = Query(
        default=None,
        description="Filter by journalistic tone ('objective', 'hype', 'critical').",
    ),
    search: Optional[str] = Query(
        default=None,
        description="Free-text search substring matching across headline, micro-summary, or body.",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number (1-indexed).",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of articles per page (max 100).",
    ),
    repo: ArticleRepository = Depends(get_article_repository),
) -> PaginatedFeedResponse:
    """Retrieve filtered and paginated feed of enriched sports articles."""
    # 1. Validate date range consistency
    if date_from is not None and date_to is not None:
        if date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date range: date_from cannot be after date_to",
            )

    # 2. Clean and parse tags & publisher query lists
    parsed_tags = _parse_comma_separated_list(tags)
    parsed_publishers = _parse_comma_separated_list(publisher)

    # 3. Query repository
    articles, total = await repo.list_articles(
        tags=parsed_tags,
        publishers=parsed_publishers,
        date_from=date_from,
        date_to=date_to,
        tone=tone,
        search=search,
        page=page,
        page_size=page_size,
    )

    # 4. Calculate pagination metadata
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1 and page <= total_pages + 1

    items = [FeedItemResponse.model_validate(article) for article in articles]

    return PaginatedFeedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=has_next,
        has_prev=has_prev,
    )


@router.post(
    "/personal",
    response_model=PaginatedFeedResponse,
    summary="Retrieve personalized feed based on user preferences",
    description="Retrieve a paginated feed tailored to user profile preferences (followed tags, excluded sources, preferred tones).",
)
async def get_personalized_feed(
    preferences: UserPreferences = Body(
        ...,
        description="User profile preferences including followed tags, excluded publishers, and preferred tones.",
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number (1-indexed).",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Number of articles per page (max 100).",
    ),
    repo: ArticleRepository = Depends(get_article_repository),
) -> PaginatedFeedResponse:
    """Retrieve personalized feed matching the UserPreferences model."""
    articles, total = await repo.get_articles_by_preferences(
        preferences=preferences,
        page=page,
        page_size=page_size,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1 and page <= total_pages + 1

    items = [FeedItemResponse.model_validate(article) for article in articles]

    return PaginatedFeedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=has_next,
        has_prev=has_prev,
    )


@router.get(
    "/{article_id}",
    response_model=FeedItemResponse,
    summary="Retrieve single article by ID",
    description="Lookup a specific enriched sports article by its primary key database ID.",
)
async def get_article_by_id(
    article_id: int = Path(..., ge=1, description="Primary key ID of the article."),
    repo: ArticleRepository = Depends(get_article_repository),
) -> FeedItemResponse:
    """Retrieve a single enriched article by ID with 404 handling."""
    article = await repo.get_by_id(article_id)
    if article is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article with ID {article_id} not found",
        )

    return FeedItemResponse.model_validate(article)
