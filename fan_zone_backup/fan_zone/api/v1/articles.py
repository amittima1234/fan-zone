"""FastAPI REST endpoints for sports news articles."""

from datetime import datetime
import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.db.session import get_db
from fan_zone.models.article import Article
from fan_zone.models.enums import IngestionStatus
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.schemas.article import (
    ArticleDetailSchema,
    ArticleSummarySchema,
    PaginatedArticleResponse,
)
from fan_zone.schemas.media import MediaSchema
from fan_zone.schemas.source import SourceSummarySchema
from fan_zone.schemas.tag import TagSchema

router = APIRouter()


def serialize_article_summary(article: Article) -> ArticleSummarySchema:
    """Helper converting an ORM Article entity into an ArticleSummarySchema."""
    lead_img = None
    if article.lead_image:
        lead_img = MediaSchema(
            id=article.lead_image.id,
            url=article.lead_image.url,
            media_type=article.lead_image.media_type,
            caption=article.lead_image.caption,
            credit=article.lead_image.credit,
            is_primary=article.lead_image.is_primary,
            is_lead=article.lead_image.is_primary,
            position_index=article.lead_image.position_index,
        )

    source_summary = None
    if article.source:
        source_summary = SourceSummarySchema(
            id=article.source.id,
            name=article.source.name,
            display_name=article.source.display_name,
            code=article.source.code,
            base_url=article.source.base_url,
        )

    return ArticleSummarySchema(
        id=article.id,
        source_id=article.source_id,
        canonical_url=article.canonical_url,
        original_title=article.original_title,
        original_subtitle=article.original_subtitle,
        original_subheadline=article.original_subheadline,
        ai_headline=article.ai_headline,
        ai_subheadline=article.ai_subheadline,
        author=article.author,
        published_at=article.published_at,
        sport=article.sport,
        competition=article.competition,
        teams=article.teams_json or [],
        players=article.players_json or [],
        tags=article.tags_json or [],
        lead_image=lead_img,
        source=source_summary,
        ingestion_status=article.ingestion_status,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


def serialize_article_detail(article: Article) -> ArticleDetailSchema:
    """Helper converting an ORM Article entity into an ArticleDetailSchema."""
    base_summary = serialize_article_summary(article)

    media_schemas = [
        MediaSchema(
            id=m.id,
            url=m.url,
            media_type=m.media_type,
            caption=m.caption,
            credit=m.credit,
            is_primary=m.is_primary,
            is_lead=m.is_primary,
            position_index=m.position_index,
        )
        for m in (article.media or [])
    ]

    tags_detail = [
        TagSchema(
            id=t.id,
            name=t.name,
            slug=t.slug,
            tag_type=t.tag_type,
            article_count=t.article_count,
            created_at=t.created_at,
        )
        for t in (article.tags or [])
    ]

    return ArticleDetailSchema(
        id=base_summary.id,
        source_id=base_summary.source_id,
        canonical_url=base_summary.canonical_url,
        original_title=base_summary.original_title,
        original_subtitle=base_summary.original_subtitle,
        original_subheadline=base_summary.original_subheadline,
        ai_headline=base_summary.ai_headline,
        ai_subheadline=base_summary.ai_subheadline,
        author=base_summary.author,
        published_at=base_summary.published_at,
        sport=base_summary.sport,
        competition=base_summary.competition,
        teams=base_summary.teams,
        players=base_summary.players,
        tags=base_summary.tags,
        lead_image=base_summary.lead_image,
        source=base_summary.source,
        ingestion_status=base_summary.ingestion_status,
        created_at=base_summary.created_at,
        updated_at=base_summary.updated_at,
        raw_paragraphs=article.raw_paragraphs or [],
        paragraphs=article.raw_paragraphs or [],
        cleaned_body=article.cleaned_body,
        raw_html=article.raw_html,
        summary=article.summary,
        media=media_schemas,
        tags_detail=tags_detail,
    )


@router.get("", response_model=PaginatedArticleResponse, summary="List and search articles")
async def list_articles(
    sport: Optional[str] = Query(None, description="Filter by sport name (e.g. כדורגל, כדורסל)"),
    team: Optional[str] = Query(None, description="Filter by team/club name (e.g. מכבי תל אביב, מכבי חיפה)"),
    competition: Optional[str] = Query(None, description="Filter by league/competition (e.g. יורוליג, ליגת העל)"),
    tag: Optional[str] = Query(None, description="Filter by entity/topic tag"),
    source: Optional[str] = Query(None, description="Filter by source name/code (e.g. sport5, one, walla)"),
    source_name: Optional[str] = Query(None, description="Alias for source filter"),
    source_code: Optional[str] = Query(None, description="Alias for source filter"),
    source_id: Optional[int] = Query(None, description="Filter by source database ID"),
    status: Optional[str] = Query(None, description="Filter by ingestion status (PENDING, AI_PROCESSED, AI_FALLBACK, FAILED)"),
    date_from: Optional[datetime] = Query(None, description="Filter articles published on or after datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter articles published on or before datetime"),
    q: Optional[str] = Query(None, description="Hebrew keyword search in headline, title, subtitle, or body"),
    search_query: Optional[str] = Query(None, description="Alias for q keyword search"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Alias for page_size"),
    sort_by: str = Query("published_at", description="Field to sort by (published_at, created_at, id)"),
    order: str = Query("desc", description="Sort direction ('desc' or 'asc')"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedArticleResponse:
    """Lists ingested news articles with multi-parameter filtering, full-text Hebrew search,
    and structured pagination metadata.
    """
    repo = ArticleRepository(db)

    effective_source = source or source_name or source_code
    effective_q = q or search_query
    effective_page_size = limit if limit is not None else page_size
    sort_desc = order.strip().lower() != "asc"
    skip = (page - 1) * effective_page_size

    articles, total = await repo.list_articles(
        source_id=source_id,
        source_name=effective_source,
        sport=sport,
        team=team,
        competition=competition,
        tag=tag,
        status=status,
        date_from=date_from,
        date_to=date_to,
        search_query=effective_q,
        skip=skip,
        limit=effective_page_size,
        sort_by=sort_by,
        sort_desc=sort_desc,
        db=db,
    )

    total_pages = math.ceil(total / effective_page_size) if total > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1

    items = [serialize_article_summary(a) for a in articles]

    return PaginatedArticleResponse(
        items=items,
        total=total,
        page=page,
        page_size=effective_page_size,
        total_pages=total_pages,
        has_next=has_next,
        has_prev=has_prev,
    )


@router.get("/{id}", response_model=ArticleDetailSchema, summary="Get full article details")
async def get_article(
    id: int,
    db: AsyncSession = Depends(get_db),
) -> ArticleDetailSchema:
    """Retrieves complete article details by database ID, including full paragraph body,
    media gallery with captions, and normalized entity taxonomy tags.
    """
    repo = ArticleRepository(db)
    article = await repo.get_by_id(id, db=db)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article with ID {id} not found",
        )
    return serialize_article_detail(article)
