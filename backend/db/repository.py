"""Database repository for article persistence, queries, and filters."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy import (
    String,
    Text,
    and_,
    cast,
    desc,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from models.feed import ArticleModel
from schemas.feed import (
    AIEnrichedCard,
    RawArticlePayload,
    ToneEnum,
    UserPreferences,
)


class ArticleRepository:
    """Repository providing asynchronous CRUD operations and filtered queries for ArticleModel."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_article(self, article: ArticleModel) -> ArticleModel:
        """Persist a newly instantiated ArticleModel to the database."""
        self.session.add(article)
        await self.session.commit()
        await self.session.refresh(article)
        self.session.expunge(article)
        return article

    async def create_enriched_article(
        self,
        raw: RawArticlePayload,
        enriched: AIEnrichedCard,
    ) -> ArticleModel:
        """Construct and persist an ArticleModel combining raw payload and AI enrichment results."""
        tone_value = enriched.tone.value if hasattr(enriched.tone, "value") else str(enriched.tone)
        url_str = str(raw.url).strip()
        publisher_str = str(raw.publisher).strip().lower()
        image_url_str = str(raw.image_url).strip() if raw.image_url else None

        article = ArticleModel(
            title=raw.title,
            url=url_str,
            publisher=publisher_str,
            published_at=raw.published_at,
            raw_body=raw.raw_body,
            micro_summary=enriched.micro_summary,
            tags=list(enriched.tags),
            tone=tone_value,
            context_label=enriched.context_label,
            category=raw.category,
            author=raw.author,
            image_url=image_url_str,
        )
        self.session.add(article)
        await self.session.commit()
        await self.session.refresh(article)
        self.session.expunge(article)
        return article

    async def get_by_id(self, article_id: int) -> Optional[ArticleModel]:
        """Fetch a single article by its primary key ID."""
        stmt = select(ArticleModel).where(ArticleModel.id == article_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_url(self, url: str) -> Optional[ArticleModel]:
        """Fetch a single article by its canonical source URL."""
        clean_url = str(url).strip()
        stmt = select(ArticleModel).where(ArticleModel.url == clean_url)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_by_url(self, url: str) -> bool:
        """Check if an article with the given canonical URL already exists."""
        clean_url = str(url).strip()
        stmt = select(func.count(ArticleModel.id)).where(ArticleModel.url == clean_url)
        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    async def update_article(
        self,
        article_id: int,
        **kwargs: Any,
    ) -> Optional[ArticleModel]:
        """Update fields on an existing article record."""
        article = await self.get_by_id(article_id)
        if article is None:
            return None

        for key, value in kwargs.items():
            if hasattr(article, key):
                if key == "tone" and hasattr(value, "value"):
                    setattr(article, key, value.value)
                elif key == "url" and value is not None:
                    setattr(article, key, str(value).strip())
                elif key == "publisher" and value is not None:
                    setattr(article, key, str(value).strip().lower())
                else:
                    setattr(article, key, value)

        article.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(article)
        return article

    async def delete_article(self, article_id: int) -> bool:
        """Delete an article by its primary key ID."""
        article = await self.get_by_id(article_id)
        if article is None:
            return False

        await self.session.delete(article)
        await self.session.commit()
        return True

    async def list_articles(
        self,
        tags: Optional[List[str]] = None,
        publishers: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        tone: Optional[Union[str, ToneEnum]] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ArticleModel], int]:
        """Query articles matching multi-criteria filters with pagination.

        Supports cross-dialect JSON tag filtering across SQLite and PostgreSQL.
        Returns a tuple of (items, total_count).
        """
        filters: List[Any] = []

        # 1. Publisher filter
        if publishers:
            clean_pubs = [p.strip().lower() for p in publishers if p and p.strip()]
            if clean_pubs:
                filters.append(ArticleModel.publisher.in_(clean_pubs))

        # 2. Date range filter
        if date_from is not None:
            filters.append(ArticleModel.published_at >= date_from)
        if date_to is not None:
            filters.append(ArticleModel.published_at <= date_to)

        # 3. Tone filter
        if tone is not None:
            tone_val = tone.value if hasattr(tone, "value") else str(tone).strip().lower()
            if tone_val:
                filters.append(ArticleModel.tone == tone_val)

        # 4. Text search filter (matches headline, micro-summary, or body)
        if search and search.strip():
            clean_search = search.strip()
            pattern = f"%{clean_search}%"
            filters.append(
                or_(
                    ArticleModel.title.ilike(pattern),
                    ArticleModel.micro_summary.ilike(pattern),
                    ArticleModel.raw_body.ilike(pattern),
                )
            )

        # 5. Tag filter (cross-dialect JSON array matching via cast to String)
        if tags:
            tag_conditions: List[Any] = []
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    clean_tag = tag.strip().replace('"', "")
                    if clean_tag:
                        escaped_tag = json.dumps(clean_tag, ensure_ascii=True).strip('"')
                        tag_conditions.append(
                            or_(
                                cast(ArticleModel.tags, String).ilike(f'%"{clean_tag}"%'),
                                cast(ArticleModel.tags, String).ilike(f'%"{escaped_tag}"%'),
                            )
                        )
            if tag_conditions:
                filters.append(or_(*tag_conditions))

        # Count total matching records
        count_stmt = select(func.count(ArticleModel.id))
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        total_result = await self.session.execute(count_stmt)
        total: int = total_result.scalar() or 0

        # Enforce valid pagination boundaries
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 100))
        offset = (safe_page - 1) * safe_page_size

        # Retrieve paginated items sorted newest first
        items_stmt = select(ArticleModel)
        if filters:
            items_stmt = items_stmt.where(and_(*filters))
        items_stmt = (
            items_stmt.order_by(desc(ArticleModel.published_at), desc(ArticleModel.id))
            .offset(offset)
            .limit(safe_page_size)
        )

        items_result = await self.session.execute(items_stmt)
        items = list(items_result.scalars().all())

        return items, total

    async def get_articles_by_preferences(
        self,
        preferences: UserPreferences,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ArticleModel], int]:
        """Retrieve paginated feed matching a UserPreferences specification."""
        filters: List[Any] = []

        # Followed tags filter
        if preferences.followed_tags:
            tag_conditions: List[Any] = []
            for tag in preferences.followed_tags:
                if isinstance(tag, str) and tag.strip():
                    clean_tag = tag.strip().replace('"', "")
                    if clean_tag:
                        escaped_tag = json.dumps(clean_tag, ensure_ascii=True).strip('"')
                        tag_conditions.append(
                            or_(
                                cast(ArticleModel.tags, String).ilike(f'%"{clean_tag}"%'),
                                cast(ArticleModel.tags, String).ilike(f'%"{escaped_tag}"%'),
                            )
                        )
            if tag_conditions:
                filters.append(or_(*tag_conditions))

        # Excluded sources filter
        if preferences.excluded_sources:
            clean_excluded = [
                s.strip().lower()
                for s in preferences.excluded_sources
                if isinstance(s, str) and s.strip()
            ]
            if clean_excluded:
                filters.append(ArticleModel.publisher.notin_(clean_excluded))

        # Preferred tones filter
        if preferences.preferred_tones:
            tone_values = [
                t.value if hasattr(t, "value") else str(t).strip().lower()
                for t in preferences.preferred_tones
                if t
            ]
            if tone_values:
                filters.append(ArticleModel.tone.in_(tone_values))

        # Count total matching records
        count_stmt = select(func.count(ArticleModel.id))
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        total_result = await self.session.execute(count_stmt)
        total: int = total_result.scalar() or 0

        # Pagination and sorting
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 100))
        offset = (safe_page - 1) * safe_page_size

        items_stmt = select(ArticleModel)
        if filters:
            items_stmt = items_stmt.where(and_(*filters))
        items_stmt = (
            items_stmt.order_by(desc(ArticleModel.published_at), desc(ArticleModel.id))
            .offset(offset)
            .limit(safe_page_size)
        )

        items_result = await self.session.execute(items_stmt)
        items = list(items_result.scalars().all())

        return items, total
