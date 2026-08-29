"""Ingestion Service coordinating scrapers, AI entity enrichment, and persistence."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.article import Article
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.models.source import Source
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.repositories.tag_repo import TagRepository
from fan_zone.schemas.article import ArticleCreate
from fan_zone.schemas.ingest import IngestionRunStats
from fan_zone.schemas.media import MediaCreate
from fan_zone.scrapers.base import (
    BaseSourceParser,
    ExtractedArticle,
    normalize_canonical_url,
)
from fan_zone.scrapers.registry import ScraperRegistry, get_scraper_for_url

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrates multi-source news discovery, downloading, parsing, deduplication,
    AI entity tagging, and database persistence for Fan-Zone.
    """

    def __init__(
        self,
        db: AsyncSession,
        ai_processor: Optional[Any] = None,
        client: Optional[httpx.AsyncClient] = None,
        article_repo: Optional[ArticleRepository] = None,
        source_repo: Optional[SourceRepository] = None,
        tag_repo: Optional[TagRepository] = None,
        registry: Optional[ScraperRegistry] = None,
    ) -> None:
        self.db = db
        self.ai_processor = ai_processor
        self.client = client
        self.article_repo = article_repo or ArticleRepository(db)
        self.source_repo = source_repo or SourceRepository(db)
        self.tag_repo = tag_repo or TagRepository(db)
        self.registry = registry or ScraperRegistry()

    async def _get_client(self) -> Tuple[httpx.AsyncClient, bool]:
        if self.client:
            return self.client, False
        client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
        return client, True

    async def ingest_url(self, url: str, source_name: Optional[str] = None) -> Tuple[Optional[Article], bool]:
        """Ingests a single article from a URL with full deduplication, AI enrichment, and persistence.
        Returns: (Article, is_newly_created)
        """
        canonical_url = normalize_canonical_url(url)
        if not canonical_url:
            logger.warning(f"Invalid URL provided for ingestion: {url}")
            return None, False

        # 1. Select parser
        parser = None
        if source_name:
            parser = self.registry.get_scraper(source_name)
        if not parser:
            parser = self.registry.get_scraper_for_url(canonical_url)
        if not parser:
            parser = self.registry.get_scraper("sport5")

        # 2. Resolve source in DB
        source = None
        if parser:
            source = await self.source_repo.get_by_code(parser.source_code, db=self.db)
            if not source:
                source = await self.source_repo.get_by_name(parser.source_name, db=self.db)
            if not source:
                source, _ = await self.source_repo.create_or_get(
                    {
                        "name": parser.source_code,
                        "display_name": parser.source_name,
                        "base_url": parser.base_url,
                    },
                    db=self.db,
                )

        # 3. Pre-check: canonical URL existence for this source
        existing_by_url = await self.article_repo.get_by_canonical_url(
            canonical_url,
            source_id=source.id if source else None,
            db=self.db,
        )
        if existing_by_url:
            logger.info(f"Article already exists by canonical URL for source {source.name if source else ''}: {canonical_url}")
            return existing_by_url, False

        # 4. Download & Parse
        client, should_close = await self._get_client()
        try:
            extracted = await parser.parse_article(client, canonical_url)
        finally:
            if should_close:
                await client.aclose()

        if not extracted:
            logger.warning(f"Failed to parse article content from URL: {canonical_url}")
            return None, False

        # 5. Ensure source
        if not source:
            source, _ = await self.source_repo.create_or_get(
                {
                    "name": extracted.source_name.lower().replace(" ", ""),
                    "display_name": extracted.source_name,
                    "base_url": f"https://{extracted.source_domain}",
                },
                db=self.db,
            )

        # 6. Process, enrich with AI, and persist
        return await self.process_and_persist_article(extracted, source)

    async def process_and_persist_article(
        self,
        extracted: ExtractedArticle,
        source: Source,
    ) -> Tuple[Optional[Article], bool]:
        """Enriches an ExtractedArticle with AI tags/headlines and saves to the repository.
        Deduplication is scoped per source.
        """
        # Check duplicate by canonical URL or content hash for this source
        existing_by_url = await self.article_repo.get_by_canonical_url(
            extracted.canonical_url,
            source_id=source.id,
            db=self.db,
        )
        if existing_by_url:
            logger.info(f"Article duplicate detected by canonical URL for source {source.name}: {extracted.canonical_url}")
            return existing_by_url, False

        existing_by_hash = await self.article_repo.get_by_content_hash(
            extracted.content_hash,
            source_id=source.id,
            db=self.db,
        )
        if existing_by_hash:
            logger.info(f"Article duplicate detected by content hash ({extracted.content_hash}) for source {source.name}: {extracted.original_title}")
            return existing_by_hash, False

        # Prepare base fields
        ai_headline = None
        ai_subheadline = None
        sport = extracted.category_hint or "ספורט כללי"
        competition = None
        teams_list: List[str] = []
        players_list: List[str] = []
        tags_list: List[str] = list(extracted.tags)
        ingestion_status = IngestionStatus.PENDING
        error_msg = None

        # AI Enrichment
        if self.ai_processor:
            try:
                ai_res = await self.ai_processor.analyze_article(
                    title=extracted.original_title,
                    subtitle=extracted.original_subtitle,
                    body=extracted.raw_body_text,
                )
                if ai_res:
                    ai_headline = getattr(ai_res, "headline", None)
                    ai_subheadline = getattr(ai_res, "subheadline", None)
                    sport = getattr(ai_res, "sport", sport)
                    competition = getattr(ai_res, "competition", None)
                    teams_list = getattr(ai_res, "teams", []) or []
                    players_list = getattr(ai_res, "players", []) or []
                    tags_list = list(set(tags_list + (getattr(ai_res, "tags", []) or [])))
                    ingestion_status = IngestionStatus.AI_PROCESSED
            except Exception as e:
                logger.warning(f"AI enrichment failed for article '{extracted.original_title}': {e}")
                ingestion_status = IngestionStatus.AI_FALLBACK
                error_msg = str(e)
                ai_headline = extracted.original_title
                ai_subheadline = extracted.original_subtitle

        # Prepare ArticleCreate schema
        article_data = ArticleCreate(
            source_id=source.id,
            canonical_url=extracted.canonical_url,
            content_hash=extracted.content_hash,
            original_title=extracted.original_title,
            original_subtitle=extracted.original_subtitle,
            author=extracted.author,
            published_at=extracted.published_at or datetime.now(timezone.utc),
            raw_paragraphs=extracted.paragraphs,
            cleaned_body=extracted.raw_body_text,
            raw_html=extracted.raw_html,
            ai_headline=ai_headline,
            ai_subheadline=ai_subheadline,
            sport=sport,
            competition=competition,
            teams_json=teams_list,
            players_json=players_list,
            tags_json=tags_list,
            ingestion_status=ingestion_status,
            error_message=error_msg,
        )

        # Prepare MediaCreate list
        media_items: List[MediaCreate] = []
        pos = 0
        if extracted.main_image:
            media_items.append(
                MediaCreate(
                    url=extracted.main_image.url,
                    caption=extracted.main_image.caption,
                    credit=extracted.main_image.credit,
                    is_primary=True,
                    position_index=pos,
                    media_type=MediaType.IMAGE,
                )
            )
            pos += 1

        for g_img in extracted.gallery_images:
            media_items.append(
                MediaCreate(
                    url=g_img.url,
                    caption=g_img.caption,
                    credit=g_img.credit,
                    is_primary=False,
                    position_index=pos,
                    media_type=MediaType.IMAGE,
                )
            )
            pos += 1

        # Prepare Tag Tuples
        tag_tuples: List[Tuple[str, TagType]] = []
        if sport:
            tag_tuples.append((sport, TagType.SPORT))
        if competition:
            tag_tuples.append((competition, TagType.COMPETITION))
        for t in teams_list:
            tag_tuples.append((t, TagType.TEAM))
        for p in players_list:
            tag_tuples.append((p, TagType.PLAYER))
        for g in tags_list:
            tag_tuples.append((g, TagType.TOPIC))

        # Upsert in repository
        article, is_created = await self.article_repo.upsert_article(
            article_data=article_data,
            media_data=media_items,
            tag_names=tag_tuples,
            db=self.db,
        )

        # Update source poll status
        await self.source_repo.update_poll_status(
            source_id=source.id,
            success=True,
            articles_added=1 if is_created else 0,
            db=self.db,
        )

        return article, is_created

    async def ingest_source(
        self,
        source_name_or_id: Union[str, int],
        max_articles: int = 10,
    ) -> IngestionRunStats:
        """Polls a specific source, discovers article URLs, and processes them up to max_articles."""
        start_time = datetime.now(timezone.utc)
        stats = IngestionRunStats(
            source_name=str(source_name_or_id),
            total_discovered=0,
            total_processed=0,
            total_ingested=0,
            total_skipped=0,
            total_skipped_duplicate=0,
            total_failed=0,
            total_errors=0,
            duration_seconds=0.0,
        )

        # Resolve Source
        if isinstance(source_name_or_id, int):
            source = await self.source_repo.get_by_id(source_name_or_id, db=self.db)
        else:
            source = await self.source_repo.get_by_code(source_name_or_id, db=self.db)
            if not source:
                source = await self.source_repo.get_by_name(source_name_or_id, db=self.db)

        if not source:
            logger.error(f"Source not found in DB: {source_name_or_id}")
            stats.errors.append(f"Source '{source_name_or_id}' not found")
            stats.total_failed += 1
            stats.total_errors += 1
            return stats

        stats.source_name = source.name
        parser = self.registry.get_scraper(source.code) or self.registry.get_scraper(source.name)
        if not parser:
            logger.error(f"No registered parser for source: {source.name}")
            stats.errors.append(f"No registered parser for source '{source.name}'")
            stats.total_failed += 1
            stats.total_errors += 1
            return stats

        # Discover
        client, should_close = await self._get_client()
        try:
            discovered_urls = await parser.discover_articles(client)
            stats.total_discovered = len(discovered_urls)

            for url in discovered_urls[:max_articles]:
                try:
                    canon_url = normalize_canonical_url(url)
                    # Pre-check existence for this source
                    if await self.article_repo.get_by_canonical_url(canon_url, source_id=source.id, db=self.db):
                        stats.total_skipped += 1
                        stats.total_skipped_duplicate += 1
                        continue

                    extracted = await parser.parse_article(client, canon_url)
                    if not extracted:
                        stats.total_failed += 1
                        stats.total_errors += 1
                        continue

                    article, is_created = await self.process_and_persist_article(extracted, source)
                    if is_created:
                        stats.total_ingested += 1
                    else:
                        stats.total_skipped += 1
                        stats.total_skipped_duplicate += 1
                except Exception as e:
                    logger.error(f"Error ingesting {url}: {e}")
                    stats.total_failed += 1
                    stats.total_errors += 1
                    stats.errors.append(f"{url}: {str(e)}")
        finally:
            if should_close:
                await client.aclose()

        stats.total_processed = stats.total_ingested + stats.total_skipped + stats.total_failed
        stats.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        return stats

    async def ingest_all_sources(self, max_articles_per_source: int = 10) -> IngestionRunStats:
        """Polls all active sources registered in the database and ingests new articles."""
        start_time = datetime.now(timezone.utc)
        aggregate_stats = IngestionRunStats(
            source_name="ALL_SOURCES",
            total_discovered=0,
            total_processed=0,
            total_ingested=0,
            total_skipped=0,
            total_skipped_duplicate=0,
            total_failed=0,
            total_errors=0,
            duration_seconds=0.0,
        )

        active_sources = await self.source_repo.get_all_active(db=self.db)
        for source in active_sources:
            try:
                s_stats = await self.ingest_source(source.id, max_articles=max_articles_per_source)
                aggregate_stats.total_discovered += s_stats.total_discovered
                aggregate_stats.total_processed += s_stats.total_processed
                aggregate_stats.total_ingested += s_stats.total_ingested
                aggregate_stats.total_skipped += s_stats.total_skipped
                aggregate_stats.total_skipped_duplicate += s_stats.total_skipped_duplicate
                aggregate_stats.total_failed += s_stats.total_failed
                aggregate_stats.total_errors += s_stats.total_errors
                aggregate_stats.errors.extend(s_stats.errors)
            except Exception as e:
                logger.error(f"Failed ingesting source {source.name}: {e}")
                aggregate_stats.total_failed += 1
                aggregate_stats.total_errors += 1
                aggregate_stats.errors.append(f"{source.name}: {str(e)}")

        aggregate_stats.duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
        return aggregate_stats
