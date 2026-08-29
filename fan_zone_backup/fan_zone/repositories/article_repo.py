"""Repository for articles, media items, and tag associations."""

import hashlib
from typing import Dict, List, Optional, Sequence, Tuple, Union
from datetime import datetime, timezone
from sqlalchemy import and_, asc, desc, func, or_, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from fan_zone.models.article import Article
from fan_zone.models.media import ArticleMedia
from fan_zone.models.tag import Tag, ArticleTag
from fan_zone.models.source import Source
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.repositories.base import BaseRepository
from fan_zone.repositories.tag_repo import TagRepository
from fan_zone.schemas.article import ArticleCreate, ArticleUpdate
from fan_zone.schemas.media import MediaCreate


class ArticleRepository(BaseRepository[Article]):
    """Async repository for managing news articles and media associations."""

    @staticmethod
    def compute_content_hash(title: str, paragraphs: Sequence[str]) -> str:
        """Computes a deterministic SHA-256 hash over normalized title and paragraphs."""
        norm_title = title.strip()
        norm_paragraphs = "\n".join(p.strip() for p in paragraphs if p and p.strip())
        text_payload = f"{norm_title}\n{norm_paragraphs}".strip()
        return hashlib.sha256(text_payload.encode("utf-8")).hexdigest()

    async def get_by_id(
        self,
        article_id: int,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Article]:
        session = self._get_session(db)
        stmt = (
            select(Article)
            .options(
                joinedload(Article.source),
                selectinload(Article.media),
                selectinload(Article.article_tags).joinedload(ArticleTag.tag),
                selectinload(Article.tags),
            )
            .where(Article.id == article_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_canonical_url(
        self,
        canonical_url: str,
        source_id: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Article]:
        session = self._get_session(db)
        conditions = [Article.canonical_url == canonical_url.strip()]
        if source_id is not None:
            conditions.append(Article.source_id == source_id)
        stmt = (
            select(Article)
            .options(
                joinedload(Article.source),
                selectinload(Article.media),
                selectinload(Article.tags),
            )
            .where(and_(*conditions))
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_content_hash(
        self,
        content_hash: str,
        source_id: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Article]:
        session = self._get_session(db)
        conditions = [Article.content_hash == content_hash.strip()]
        if source_id is not None:
            conditions.append(Article.source_id == source_id)
        stmt = (
            select(Article)
            .options(
                joinedload(Article.source),
                selectinload(Article.media),
                selectinload(Article.tags),
            )
            .where(and_(*conditions))
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def exists_by_url_or_hash(
        self,
        canonical_url: str,
        content_hash: str,
        source_id: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        session = self._get_session(db)
        match_expr = or_(
            Article.canonical_url == canonical_url.strip(),
            Article.content_hash == content_hash.strip(),
        )
        if source_id is not None:
            stmt = select(Article.id).where(and_(Article.source_id == source_id, match_expr)).limit(1)
        else:
            stmt = select(Article.id).where(match_expr).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def upsert_article(
        self,
        article_data: Union[ArticleCreate, dict],
        media_data: Optional[List[Union[MediaCreate, dict]]] = None,
        tag_names: Optional[List[Tuple[str, Union[TagType, str]]]] = None,
        db: Optional[AsyncSession] = None,
    ) -> Tuple[Article, bool]:
        """
        Atomically inserts or updates an article, associated media, and entity tags.
        Deduplication is scoped per source_id.
        Returns: (Article, is_created)
        """
        session = self._get_session(db)
        data = article_data.model_dump() if isinstance(article_data, ArticleCreate) else dict(article_data)

        # Normalize field names
        canonical_url = data["canonical_url"].strip()
        original_title = data["original_title"].strip()
        paragraphs = data.get("raw_paragraphs") or data.get("paragraphs") or []
        source_id = data.get("source_id")
        
        # Calculate content hash if not provided
        content_hash = data.get("content_hash") or self.compute_content_hash(original_title, paragraphs)
        data["content_hash"] = content_hash

        # Extract cleaned body if missing
        cleaned_body = data.get("cleaned_body")
        if not cleaned_body and paragraphs:
            cleaned_body = "\n\n".join(paragraphs)

        # Check existing by canonical URL or content hash scoped by source_id
        existing = await self.get_by_canonical_url(canonical_url, source_id=source_id, db=session)
        if not existing and content_hash:
            existing = await self.get_by_content_hash(content_hash, source_id=source_id, db=session)

        is_created = False
        if existing:
            # If already processed with AI and new payload does not specify updated AI headline, preserve existing
            if (
                existing.ingestion_status == IngestionStatus.AI_PROCESSED
                and not data.get("ai_headline")
                and data.get("ingestion_status") != IngestionStatus.AI_PROCESSED
            ):
                return existing, False

            article = existing
            # Update fields
            article.source_id = data.get("source_id", article.source_id)
            article.canonical_url = canonical_url
            article.content_hash = content_hash
            article.original_title = original_title
            article.original_subtitle = data.get("original_subtitle") or data.get("original_subheadline") or article.original_subtitle
            article.author = data.get("author") or article.author
            article.published_at = data.get("published_at") or article.published_at
            article.raw_paragraphs = paragraphs
            article.cleaned_body = cleaned_body
            article.raw_html = data.get("raw_html") or article.raw_html

            if data.get("ai_headline"):
                article.ai_headline = data["ai_headline"]
            if data.get("ai_subheadline"):
                article.ai_subheadline = data["ai_subheadline"]
            if data.get("summary"):
                article.summary = data["summary"]
            if data.get("sport"):
                article.sport = data["sport"]
            if data.get("competition"):
                article.competition = data["competition"]
            if data.get("teams_json"):
                article.teams_json = data["teams_json"]
            if data.get("players_json"):
                article.players_json = data["players_json"]
            if data.get("tags_json"):
                article.tags_json = data["tags_json"]
            if data.get("ingestion_status"):
                article.ingestion_status = data["ingestion_status"]
            if data.get("error_message") is not None:
                article.error_message = data["error_message"]

            article.updated_at = datetime.now(timezone.utc)
        else:
            is_created = True
            article = Article(
                source_id=data["source_id"],
                canonical_url=canonical_url,
                content_hash=content_hash,
                original_title=original_title,
                original_subtitle=data.get("original_subtitle") or data.get("original_subheadline"),
                author=data.get("author"),
                published_at=data.get("published_at") or datetime.now(timezone.utc),
                raw_paragraphs=paragraphs,
                cleaned_body=cleaned_body,
                raw_html=data.get("raw_html"),
                ai_headline=data.get("ai_headline"),
                ai_subheadline=data.get("ai_subheadline"),
                summary=data.get("summary"),
                sport=data.get("sport"),
                competition=data.get("competition"),
                teams_json=data.get("teams_json", []),
                players_json=data.get("players_json", []),
                tags_json=data.get("tags_json", []),
                ingestion_status=data.get("ingestion_status", IngestionStatus.PENDING),
                error_message=data.get("error_message"),
            )
            session.add(article)

        await session.flush()

        # Handle media items
        media_list = media_data if media_data is not None else data.get("media")
        if media_list is not None:
            # Remove old media if updating
            if not is_created:
                del_media_stmt = delete(ArticleMedia).where(ArticleMedia.article_id == article.id)
                await session.execute(del_media_stmt)
                await session.flush()

            for idx, item in enumerate(media_list):
                m_data = item.model_dump() if isinstance(item, MediaCreate) else dict(item)
                media_type = m_data.get("media_type", MediaType.IMAGE)
                if isinstance(media_type, str):
                    try:
                        media_type = MediaType(media_type.lower())
                    except ValueError:
                        media_type = MediaType.IMAGE

                is_primary = m_data.get("is_primary", False) or m_data.get("is_lead", False) or (idx == 0)
                media_obj = ArticleMedia(
                    article_id=article.id,
                    url=m_data["url"],
                    media_type=media_type,
                    caption=m_data.get("caption"),
                    credit=m_data.get("credit"),
                    is_primary=is_primary,
                    position_index=m_data.get("position_index", idx),
                )
                session.add(media_obj)

        # Handle tag associations
        all_tags_to_sync: List[Tuple[str, Union[TagType, str]]] = []
        if tag_names:
            all_tags_to_sync.extend(tag_names)
        else:
            # Auto-extract tags from structured fields
            if article.sport:
                all_tags_to_sync.append((article.sport, TagType.SPORT))
            if article.competition:
                all_tags_to_sync.append((article.competition, TagType.COMPETITION))
            for t in article.teams_json or []:
                all_tags_to_sync.append((t, TagType.TEAM))
            for p in article.players_json or []:
                all_tags_to_sync.append((p, TagType.PLAYER))
            for tg in article.tags_json or []:
                all_tags_to_sync.append((tg, TagType.GENERAL))

        if all_tags_to_sync:
            tag_repo = TagRepository(session)
            synced_tags = await tag_repo.get_or_create_tags(all_tags_to_sync, db=session)
            
            # Clear existing article tags
            del_tags_stmt = delete(ArticleTag).where(ArticleTag.article_id == article.id)
            await session.execute(del_tags_stmt)
            await session.flush()

            for t in synced_tags:
                t.article_count += 1
                art_tag = ArticleTag(article_id=article.id, tag_id=t.id)
                session.add(art_tag)

        await session.flush()
        refreshed = await self.get_by_id(article.id, db=session)
        return refreshed or article, is_created

    async def list_articles(
        self,
        source_id: Optional[int] = None,
        source_name: Optional[str] = None,
        sport: Optional[str] = None,
        team: Optional[str] = None,
        competition: Optional[str] = None,
        tag: Optional[str] = None,
        status: Optional[Union[IngestionStatus, str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search_query: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "published_at",
        sort_desc: bool = True,
        db: Optional[AsyncSession] = None,
    ) -> Tuple[List[Article], int]:
        """
        Lists articles with multi-parameter filtering, Hebrew substring search, and pagination.
        Returns: (List[Article], total_count)
        """
        session = self._get_session(db)
        
        # Base query with eager loading
        query = (
            select(Article)
            .options(
                joinedload(Article.source),
                selectinload(Article.media),
                selectinload(Article.tags),
                selectinload(Article.article_tags).joinedload(ArticleTag.tag),
            )
        )

        conditions = []

        if source_id is not None:
            conditions.append(Article.source_id == source_id)

        if source_name:
            conditions.append(
                Article.source_id.in_(
                    select(Source.id).where(func.lower(Source.name) == source_name.strip().lower())
                )
            )

        if sport:
            sport_term = f"%{sport.strip()}%"
            conditions.append(
                or_(
                    Article.sport.ilike(sport_term),
                    Article.id.in_(
                        select(ArticleTag.article_id)
                        .join(Tag, ArticleTag.tag_id == Tag.id)
                        .where(Tag.name.ilike(sport_term))
                    ),
                )
            )

        if competition:
            comp_term = f"%{competition.strip()}%"
            conditions.append(
                or_(
                    Article.competition.ilike(comp_term),
                    Article.id.in_(
                        select(ArticleTag.article_id)
                        .join(Tag, ArticleTag.tag_id == Tag.id)
                        .where(Tag.name.ilike(comp_term))
                    ),
                )
            )

        if team:
            team_term = f"%{team.strip()}%"
            conditions.append(
                Article.id.in_(
                    select(ArticleTag.article_id)
                    .join(Tag, ArticleTag.tag_id == Tag.id)
                    .where(Tag.name.ilike(team_term))
                )
            )

        if tag:
            tag_term = f"%{tag.strip()}%"
            conditions.append(
                Article.id.in_(
                    select(ArticleTag.article_id)
                    .join(Tag, ArticleTag.tag_id == Tag.id)
                    .where(Tag.name.ilike(tag_term))
                )
            )

        if status:
            if isinstance(status, str):
                try:
                    status = IngestionStatus(status)
                except ValueError:
                    pass
            conditions.append(Article.ingestion_status == status)

        if date_from:
            conditions.append(Article.published_at >= date_from)

        if date_to:
            conditions.append(Article.published_at <= date_to)

        if search_query:
            term = f"%{search_query.strip()}%"
            conditions.append(
                or_(
                    Article.ai_headline.ilike(term),
                    Article.original_title.ilike(term),
                    Article.ai_subheadline.ilike(term),
                    Article.original_subtitle.ilike(term),
                    Article.cleaned_body.ilike(term),
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        # Count query
        count_stmt = select(func.count(func.distinct(Article.id)))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        
        count_res = await session.execute(count_stmt)
        total_count = count_res.scalar() or 0

        # Sorting
        sort_attr = getattr(Article, sort_by, Article.published_at)
        order_fn = desc if sort_desc else asc
        query = query.order_by(order_fn(sort_attr), desc(Article.id))

        # Pagination
        query = query.offset(skip).limit(limit)

        result = await session.execute(query)
        articles = list(result.unique().scalars().all())
        return articles, total_count

    async def delete_article(
        self,
        article_id: int,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        session = self._get_session(db)
        article = await self.get_by_id(article_id, db=session)
        if not article:
            return False

        await session.delete(article)
        await session.flush()
        return True
