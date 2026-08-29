"""Integration tests for IngestionService with real DB sessions, mock AI, and simulated network transports."""

from datetime import datetime, timezone
import pytest
import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.article import Article, ArticleMedia
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.models.source import Source
from fan_zone.models.tag import Tag, ArticleTag
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.repositories.tag_repo import TagRepository
from fan_zone.schemas.article import ArticleCreate
from fan_zone.schemas.media import MediaCreate
from fan_zone.schemas.ingest import IngestionRunStats
from fan_zone.scrapers.base import (
    BaseSourceParser,
    ExtractedArticle,
    ExtractedImage,
    compute_content_hash,
    normalize_canonical_url,
)
from fan_zone.scrapers.registry import ScraperRegistry
from fan_zone.services.ingestion_service import IngestionService
from fan_zone.ai.mock import MockAIProcessor


@pytest.mark.asyncio
class TestIngestionServiceIntegration:
    """Comprehensive integration tests for IngestionService."""

    async def test_ingest_extracted_article_with_ai(self, db_session: AsyncSession):
        """Test full enrichment pipeline: AI headlines, entity tagging, media creation, and status update."""
        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        source_sport5 = next(s for s in sources if s.name == "sport5")

        ai_processor = MockAIProcessor()
        service = IngestionService(db=db_session, ai_processor=ai_processor)

        extracted = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=999999",
            canonical_url="https://www.sport5.co.il/articles.aspx?docID=999999&FolderID=64",
            content_hash=compute_content_hash("כותרת מקורית וסנסציונית", ["פסקה אחת", "פסקה שתיים"]),
            original_title="כותרת מקורית וסנסציונית: אתם לא תאמינו מה קרה!",
            original_subtitle="כותרת משנה מקורית",
            author="כתב ספורט 5",
            published_at=datetime(2026, 8, 28, 20, 0, 0, tzinfo=timezone.utc),
            paragraphs=["פסקה אחת", "פסקה שתיים"],
            raw_body_text="פסקה אחת\n\nפסקה שתיים",
            main_image=ExtractedImage(url="https://images.sport5.co.il/lead.jpg", caption="תמונה ראשית", is_main=True),
            gallery_images=[ExtractedImage(url="https://images.sport5.co.il/gal1.jpg")],
            tags=["ספורט 5"],
        )

        article, is_created = await service.process_and_persist_article(extracted, source_sport5)
        assert is_created is True
        assert article is not None
        assert article.id is not None
        assert article.ingestion_status == IngestionStatus.AI_PROCESSED
        assert article.ai_headline is not None
        assert article.sport is not None
        assert len(article.media) == 2
        assert article.media[0].is_primary is True
        assert article.media[0].url == "https://images.sport5.co.il/lead.jpg"

        # Check source poll status was updated
        updated_source = await source_repo.get_by_id(source_sport5.id)
        assert updated_source.last_polled_at is not None
        assert updated_source.last_success_at is not None
        assert updated_source.error_count == 0

    async def test_ingest_deduplication_by_url_and_hash(self, db_session: AsyncSession):
        """Verify duplicate articles are returned without creating new DB records."""
        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        source_one = next(s for s in sources if s.name == "one")

        service = IngestionService(db=db_session)

        extracted = ExtractedArticle(
            source_name="ONE",
            source_domain="one.co.il",
            original_url="https://www.one.co.il/Article/2026/888888.html",
            canonical_url="https://www.one.co.il/Article/2026/888888.html",
            content_hash=compute_content_hash("כותרת כפילות", ["פסקה א", "פסקה ב"]),
            original_title="כותרת כפילות",
            published_at=datetime(2026, 8, 28, 15, 0, 0, tzinfo=timezone.utc),
            paragraphs=["פסקה א", "פסקה ב"],
            raw_body_text="פסקה א\n\nפסקה ב",
        )

        art1, created1 = await service.process_and_persist_article(extracted, source_one)
        assert created1 is True

        # Re-ingest with identical content
        art2, created2 = await service.process_and_persist_article(extracted, source_one)
        assert created2 is False
        assert art2.id == art1.id

    async def test_ai_failure_fallback_resilience(self, db_session: AsyncSession):
        """Verify that when AI enrichment raises an exception, the article is saved with AI_FALLBACK."""
        class FailingAIProcessor:
            async def analyze_article(self, title: str, subtitle, body: str):
                raise TimeoutError("Gemini API timed out after 10s")

        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        source_walla = next(s for s in sources if s.name == "walla")

        service = IngestionService(db=db_session, ai_processor=FailingAIProcessor())

        extracted = ExtractedArticle(
            source_name="Walla! Sports",
            source_domain="walla.co.il",
            original_url="https://sports.walla.co.il/item/7777777",
            canonical_url="https://sports.walla.co.il/item/7777777",
            content_hash=compute_content_hash("כותרת כשל AI", ["פסקה אחת"]),
            original_title="כותרת כשל AI",
            original_subtitle="משנה כשל AI",
            published_at=datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc),
            paragraphs=["פסקה אחת"],
            raw_body_text="פסקה אחת",
        )

        art, is_created = await service.process_and_persist_article(extracted, source_walla)
        assert is_created is True
        assert art.ingestion_status == IngestionStatus.AI_FALLBACK
        assert "Gemini API timed out" in (art.error_message or "")
        assert art.ai_headline == "כותרת כשל AI"

    async def test_ingest_source_batch_with_mock_transport(self, db_session: AsyncSession):
        """Test full source batch ingestion flow with simulated HTTP transport."""
        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        source_sport5 = next(s for s in sources if s.name == "sport5")

        article_html = """
        <html>
        <head><title>Sport5</title></head>
        <body>
            <h1 class="article-title">ניצחון היסטורי בטורניר</h1>
            <span class="article-credit">עמית לוי</span>
            <div class="article-body"><p>פסקה ראשונה של הכתבה עם מספיק תווים.</p></div>
        </body>
        </html>
        """

        def handler(request: httpx.Request):
            url_str = str(request.url)
            if "articles.aspx?FolderID=64" in url_str:
                disc_html = """
                <html><body>
                    <a href="/articles.aspx?FolderID=64&docID=1001">כתבה 1</a>
                    <a href="/articles.aspx?FolderID=64&docID=1002">כתבה 2</a>
                </body></html>
                """
                return httpx.Response(200, text=disc_html, request=request)
            elif "docID=1001" in url_str:
                return httpx.Response(200, text=article_html, request=request)
            elif "docID=1002" in url_str:
                return httpx.Response(500, text="Internal Error", request=request)
            return httpx.Response(404, request=request)

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = IngestionService(
            db=db_session,
            ai_processor=MockAIProcessor(),
            client=mock_client,
        )

        try:
            stats = await service.ingest_source(source_sport5.id, max_articles=5)
            assert stats.total_discovered >= 2
            assert stats.total_ingested == 1
            assert stats.total_failed == 1
            assert stats.total_processed == 2
            assert stats.duration_seconds >= 0.0
        finally:
            await mock_client.aclose()
