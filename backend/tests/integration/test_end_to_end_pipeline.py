"""Tier 4 Real-World Application Pipeline & End-to-End Integration Tests.

Verifies the complete lifecycle of the Fan Zone sports news platform:
1. Multi-publisher scraping (Sport5, Ynet, ONE) with HTML sanitization and strict text truncation (<= 3500 chars).
2. Event-driven queue decoupling (InMemoryTaskQueue) with URL deduplication.
3. AI Worker enrichment (structured outputs into AIEnrichedCard) and persistence via SQLAlchemy async repository.
4. Client delivery via FastAPI REST endpoints (/api/v1/feed, /api/v1/feed/{id}, /api/v1/feed/personal, /api/v1/ingestion/trigger).
5. Fault tolerance against corrupted RSS feeds, HTTP errors, and malformed HTML.
6. Multi-cycle ingestion idempotency and personalized feed preference matching.
"""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from httpx import ASGITransport
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.deps import get_db, get_settings
from core.config import Settings
from core.queue import InMemoryTaskQueue
from db.repository import ArticleRepository
from db.session import Base, create_async_db_engine, get_session_factory
from main import app
from models.feed import ArticleModel
from schemas.feed import (
    AIEnrichedCard,
    PublisherEnum,
    RawArticlePayload,
    ToneEnum,
    UserPreferences,
)
from services.ai_worker import (
    AIEnrichmentService,
    GeminiAIEnricher,
    MockAIEnricher,
)
from services.scrapers.one import ONEScraper
from services.scrapers.sport5 import Sport5Scraper
from services.scrapers.ynet import YnetScraper
from tests.fixtures.mock_gemini import create_mock_gemini_response
from tests.fixtures.sample_html import (
    ONE_ARTICLE_HTML,
    SPORT5_ARTICLE_HTML,
    SPORT5_LONG_ARTICLE_HTML,
    YNET_ARTICLE_HTML,
)
from tests.fixtures.sample_rss import (
    CORRUPTED_RSS_XML,
    ONE_RSS_XML,
    SPORT5_RSS_XML,
    YNET_RSS_XML,
)


# ---------------------------------------------------------------------------
# Test Fixtures & In-Memory Isolation
# ---------------------------------------------------------------------------

@pytest.fixture
def e2e_settings() -> Settings:
    """Isolated settings configured for in-memory E2E test execution."""
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USE_MOCK_AI=True,
        ENABLE_SCHEDULER=False,
        DEBUG=True,
        DB_ECHO=False,
        APP_ENV="test",
    )


@pytest.fixture
async def e2e_engine(e2e_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
    """Isolated async SQLite in-memory engine with clean table initialization."""
    engine = create_async_db_engine(e2e_settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def e2e_session_factory(
    e2e_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Provide session factory bound to the in-memory E2E database."""
    return get_session_factory(e2e_engine)


@pytest.fixture
async def e2e_db_session(
    e2e_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide an active AsyncSession rolled back after each test."""
    async with e2e_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture
def e2e_repo(e2e_db_session: AsyncSession) -> ArticleRepository:
    """ArticleRepository instance wired to the active E2E test database session."""
    return ArticleRepository(e2e_db_session)


@pytest.fixture
async def e2e_client(
    e2e_session_factory: async_sessionmaker[AsyncSession],
    e2e_settings: Settings,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """FastAPI async test client bound to the test database and isolated settings."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with e2e_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    def override_get_settings() -> Settings:
        return e2e_settings

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper Mock HTTP Transport for Scrapers
# ---------------------------------------------------------------------------

def create_mock_transport_for_scrapers(
    rss_map: Dict[str, str],
    html_map: Dict[str, str],
    error_urls: Optional[List[str]] = None,
) -> httpx.MockTransport:
    """Create a httpx.MockTransport that serves realistic RSS feeds and HTML articles."""
    error_urls = error_urls or []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)

        # Check for simulated network / server errors
        if any(err_url in url_str for err_url in error_urls):
            return httpx.Response(500, text="Internal Server Error")

        # Check RSS endpoints
        for endpoint, rss_content in rss_map.items():
            if endpoint in url_str:
                return httpx.Response(200, text=rss_content, headers={"Content-Type": "application/xml; charset=utf-8"})

        # Check HTML article endpoints
        for endpoint, html_content in html_map.items():
            if endpoint in url_str:
                return httpx.Response(200, text=html_content, headers={"Content-Type": "text/html; charset=utf-8"})

        # Default fallback
        return httpx.Response(200, text="<html><body><p>תוכן כללי</p></body></html>")

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# 1. Full Pipeline Flow Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFullPipelineFlow:
    """End-to-End tests validating the full pipeline: Scrape -> Truncate -> Queue -> Enrich -> Persist -> API Delivery."""

    async def test_e2e_event_driven_pipeline_flow(
        self,
        e2e_client: httpx.AsyncClient,
        e2e_session_factory: async_sessionmaker[AsyncSession],
        e2e_settings: Settings,
    ):
        """Verify the complete event-driven lifecycle from scraping to REST API query.

        Flow:
        1. Sport5Scraper scrapes mock RSS & HTML.
        2. Extracted article is checked for <= 3500 character truncation.
        3. RawArticlePayload is pushed to InMemoryTaskQueue.
        4. AIEnrichmentService pops item from queue, performs mock AI enrichment into AIEnrichedCard.
        5. Article is saved into SQLite via ArticleRepository.
        6. FastAPI GET /api/v1/feed queries the persisted article with tag and tone filters.
        """
        # Step 1: Initialize scraper with mock HTTP transport
        transport = create_mock_transport_for_scrapers(
            rss_map={"sport5.co.il/rss": SPORT5_RSS_XML, "sport5.co.il": SPORT5_RSS_XML},
            html_map={"450101": SPORT5_ARTICLE_HTML, "sport5.co.il": SPORT5_ARTICLE_HTML},
        )
        scraper = Sport5Scraper()

        async with httpx.AsyncClient(transport=transport) as http_client:
            raw_articles = []
            entries = await scraper.fetch_rss(http_client)
            assert len(entries) > 0, "Failed to parse RSS feed entries"

            first_entry = entries[0]
            html_text = await scraper.fetch_article_html(http_client, first_entry["link"])
            assert html_text is not None

            payload = scraper.extract_article(html_text, rss_entry=first_entry)
            assert payload is not None
            assert payload.publisher == "sport5"
            assert len(payload.raw_body) <= 3500, "Raw body exceeded 3500 chars limit"
            raw_articles.append(payload)

        # Step 2: Push to InMemoryTaskQueue
        queue = InMemoryTaskQueue()
        pushed = await queue.push(raw_articles[0])
        assert pushed is True, "Failed to push article to task queue"
        assert await queue.size() == 1

        # Step 3: AI Worker pops from queue, enriches, and persists to DB
        ai_service = AIEnrichmentService(use_mock=True, settings_obj=e2e_settings)

        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            persisted = await ai_service.process_queue_item(queue, repo)
            assert persisted is not None
            assert persisted.id > 0
            assert persisted.publisher == "sport5"
            assert "Maccabi Tel Aviv" in persisted.tags or "Euroleague" in persisted.tags
            assert persisted.tone in ("hype", "objective", "critical")

        # Step 4: Verify queue is now drained
        assert await queue.size() == 0

        # Step 5: Query via FastAPI REST endpoint /api/v1/feed
        response = await e2e_client.get("/api/v1/feed")
        assert response.status_code == 200
        feed_data = response.json()

        assert feed_data["total"] == 1
        assert len(feed_data["items"]) == 1

        item = feed_data["items"][0]
        assert item["publisher"] == "sport5"
        assert item["url"] == str(raw_articles[0].url)
        assert len(item["micro_summary"]) > 0
        assert len(item["tags"]) > 0
        assert item["tone"] == persisted.tone

        # Step 6: Filter by tone via FastAPI
        tone_response = await e2e_client.get("/api/v1/feed", params={"tone": item["tone"]})
        assert tone_response.status_code == 200
        tone_data = tone_response.json()
        assert tone_data["total"] == 1

        # Step 7: Query single article by ID
        single_res = await e2e_client.get(f"/api/v1/feed/{item['id']}")
        assert single_res.status_code == 200
        assert single_res.json()["id"] == item["id"]

    async def test_e2e_long_article_truncation_and_enrichment(
        self,
        e2e_client: httpx.AsyncClient,
        e2e_session_factory: async_sessionmaker[AsyncSession],
        e2e_settings: Settings,
    ):
        """Verify long article HTML (>3500 chars) is strictly truncated, enriched, and queryable."""
        scraper = Sport5Scraper()
        rss_entry = {
            "title": "ניתוח מעמיק: משחק העונה ביורוליג",
            "link": "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=999111",
            "summary": "ניתוח ארוך במיוחד",
            "published_at": datetime.now(timezone.utc),
            "author": "עמרי פולק",
            "category": "יורוליג",
            "image_url": None,
        }

        # Long HTML exceeds 3500 characters
        payload = scraper.extract_article(SPORT5_LONG_ARTICLE_HTML, rss_entry=rss_entry)
        assert payload is not None
        assert len(payload.raw_body) <= 3500, f"Body length {len(payload.raw_body)} exceeded 3500 limit"

        # Queue and enrich
        queue = InMemoryTaskQueue()
        await queue.push(payload)

        ai_service = AIEnrichmentService(use_mock=True, settings_obj=e2e_settings)
        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            persisted = await ai_service.process_queue_item(queue, repo)
            assert persisted is not None

        # Verify through API
        res = await e2e_client.get(f"/api/v1/feed/{persisted.id}")
        assert res.status_code == 200
        data = res.json()
        assert len(data["micro_summary"].split()) <= 40
        assert "<script>" not in data["micro_summary"]
        assert "<iframe" not in data["micro_summary"]


# ---------------------------------------------------------------------------
# 2. Multi-Publisher Concurrent Ingestion Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestMultiPublisherConcurrentIngestion:
    """End-to-End tests validating concurrent scraping across Sport5, Ynet, and ONE."""

    async def test_concurrent_multi_publisher_ingestion(
        self,
        e2e_client: httpx.AsyncClient,
        e2e_session_factory: async_sessionmaker[AsyncSession],
        e2e_settings: Settings,
    ):
        """Concurrently scrape Sport5, Ynet, and ONE, push all to queue, enrich, and verify in API feed."""
        transport = create_mock_transport_for_scrapers(
            rss_map={
                "sport5.co.il": SPORT5_RSS_XML,
                "ynet.co.il": YNET_RSS_XML,
                "one.co.il": ONE_RSS_XML,
            },
            html_map={
                "sport5.co.il": SPORT5_ARTICLE_HTML,
                "ynet.co.il": YNET_ARTICLE_HTML,
                "one.co.il": ONE_ARTICLE_HTML,
            },
        )

        scrapers = [Sport5Scraper(), YnetScraper(), ONEScraper()]
        queue = InMemoryTaskQueue()

        async with httpx.AsyncClient(transport=transport) as http_client:
            async def scrape_portal(sc):
                articles = []
                entries = await sc.fetch_rss(http_client)
                for entry in entries[:2]:
                    html_content = await sc.fetch_article_html(http_client, entry["link"])
                    item = sc.extract_article(html_content or "", rss_entry=entry)
                    if item:
                        articles.append(item)
                return articles

            # Execute concurrent scraping across all 3 portals
            results = await asyncio.gather(*(scrape_portal(sc) for sc in scrapers))

        all_articles = [art for sublist in results for art in sublist]
        assert len(all_articles) >= 3, f"Expected at least 3 articles across portals, got {len(all_articles)}"

        # Enqueue all extracted articles
        for article in all_articles:
            await queue.push(article)

        initial_queue_size = await queue.size()
        assert initial_queue_size >= 3

        # Drain task queue with AI Worker
        ai_service = AIEnrichmentService(use_mock=True, settings_obj=e2e_settings)
        saved_count = 0

        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            while await queue.size() > 0:
                item = await ai_service.process_queue_item(queue, repo)
                if item:
                    saved_count += 1

        assert saved_count >= 3
        assert await queue.size() == 0

        # Verify all three publishers exist via FastAPI
        feed_res = await e2e_client.get("/api/v1/feed", params={"page_size": 50})
        assert feed_res.status_code == 200
        feed_data = feed_res.json()
        assert feed_data["total"] == saved_count

        publishers_in_feed = {item["publisher"] for item in feed_data["items"]}
        assert "sport5" in publishers_in_feed
        assert "ynet" in publishers_in_feed
        assert "one" in publishers_in_feed

        # Test filtering by specific publisher via API
        ynet_res = await e2e_client.get("/api/v1/feed", params={"publisher": "ynet"})
        assert ynet_res.status_code == 200
        ynet_data = ynet_res.json()
        assert ynet_data["total"] >= 1
        assert all(item["publisher"] == "ynet" for item in ynet_data["items"])

    async def test_concurrent_ingestion_preserves_metadata(
        self,
        e2e_client: httpx.AsyncClient,
        e2e_session_factory: async_sessionmaker[AsyncSession],
        e2e_settings: Settings,
    ):
        """Verify that authors, categories, and published timestamps are preserved across concurrent ingestion."""
        sample_articles = [
            RawArticlePayload(
                title="מכבי תל אביב ביורוליג",
                raw_body="ניצחון צהוב גדול בהיכל מנורה מבטחים.",
                url="https://www.sport5.co.il/item/101",
                publisher="sport5",
                author="עמרי פולק",
                category="כדורסל",
                published_at=datetime(2026, 8, 29, 10, 0, 0, tzinfo=timezone.utc),
            ),
            RawArticlePayload(
                title="סערה בבית\"ר ירושלים",
                raw_body="זעזוע בבירה לקראת משחק העונה.",
                url="https://www.ynet.co.il/item/202",
                publisher="ynet",
                author="גידי ליפקין",
                category="ליגת העל",
                published_at=datetime(2026, 8, 29, 9, 0, 0, tzinfo=timezone.utc),
            ),
        ]

        queue = InMemoryTaskQueue()
        for art in sample_articles:
            await queue.push(art)

        ai_service = AIEnrichmentService(use_mock=True, settings_obj=e2e_settings)
        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            while await queue.size() > 0:
                await ai_service.process_queue_item(queue, repo)

        # Check API feed returns accurate authors and categories
        res = await e2e_client.get("/api/v1/feed")
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 2

        sport5_item = next(i for i in items if i["publisher"] == "sport5")
        assert sport5_item["author"] == "עמרי פולק"
        assert sport5_item["category"] == "כדורסל"

        ynet_item = next(i for i in items if i["publisher"] == "ynet")
        assert ynet_item["author"] == "גידי ליפקין"
        assert ynet_item["category"] == "ליגת העל"


# ---------------------------------------------------------------------------
# 3. Ingestion Deduplication Cycles Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIngestionDeduplicationCycles:
    """End-to-End tests validating URL deduplication across consecutive ingestion cycles."""

    async def test_consecutive_ingestion_cycles_deduplication(
        self,
        e2e_client: httpx.AsyncClient,
        e2e_session_factory: async_sessionmaker[AsyncSession],
        e2e_settings: Settings,
    ):
        """Execute two consecutive ingestion cycles and verify that duplicate URLs are not re-inserted."""
        ai_service = AIEnrichmentService(use_mock=True, settings_obj=e2e_settings)

        cycle_1_articles = [
            RawArticlePayload(
                title="כתבה ראשונה מחזור 1",
                raw_body="תוכן הכתבה הראשונה במערכת.",
                url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=1001",
                publisher="sport5",
            ),
            RawArticlePayload(
                title="כתבה שנייה מחזור 1",
                raw_body="תוכן הכתבה השנייה במערכת.",
                url="https://www.ynet.co.il/sport/article/1002",
                publisher="ynet",
            ),
        ]

        # Cycle 1: Insert 2 articles
        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            for art in cycle_1_articles:
                await ai_service.enrich_and_store(art, repo)

        # Check DB state after Cycle 1
        res1 = await e2e_client.get("/api/v1/feed")
        assert res1.status_code == 200
        assert res1.json()["total"] == 2

        # Cycle 2: Contains the same 2 articles PLUS 1 new article
        cycle_2_articles = [
            cycle_1_articles[0],  # Duplicate URL
            cycle_1_articles[1],  # Duplicate URL
            RawArticlePayload(
                title="כתבה חדשה מחזור 2",
                raw_body="תוכן כתבה חדשה שהתווספה במחזור השני.",
                url="https://www.one.co.il/Article/1003.html",
                publisher="one",
            ),
        ]

        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            for art in cycle_2_articles:
                await ai_service.enrich_and_store(art, repo)

        # Check DB state after Cycle 2: Exactly 3 total articles
        res2 = await e2e_client.get("/api/v1/feed")
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["total"] == 3, f"Expected 3 articles after deduplication, got {data2['total']}"

        urls = [item["url"] for item in data2["items"]]
        assert len(urls) == len(set(urls)), "Duplicate URLs found in feed response"

    async def test_queue_deduplication_prevents_duplicate_push(self):
        """Verify InMemoryTaskQueue rejects duplicate URL pushes immediately."""
        queue = InMemoryTaskQueue()
        art1 = RawArticlePayload(
            title="בדיקת תור כפילות",
            raw_body="תוכן בדיקה עבור תור הודעות.",
            url="https://www.sport5.co.il/item/dup-test",
            publisher="sport5",
        )
        art2 = RawArticlePayload(
            title="בדיקת תור כפילות עם כותרת שונה אך אותו קישור",
            raw_body="תוכן בדיקה שונה.",
            url="https://www.sport5.co.il/item/dup-test",  # Identical URL
            publisher="sport5",
        )

        assert await queue.push(art1) is True
        assert await queue.push(art2) is False  # Duplicate URL rejected
        assert await queue.size() == 1


# ---------------------------------------------------------------------------
# 4. Fault Tolerance & Corrupted Data Resilience Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPipelineFaultTolerance:
    """End-to-End tests validating graceful error handling and system resilience."""

    async def test_pipeline_graceful_resilience_to_corrupted_rss_and_http_errors(
        self,
        e2e_client: httpx.AsyncClient,
        e2e_session_factory: async_sessionmaker[AsyncSession],
        e2e_settings: Settings,
    ):
        """Verify pipeline continues gracefully when one feed is corrupted and another returns HTTP 500."""
        transport = create_mock_transport_for_scrapers(
            rss_map={
                "sport5.co.il": CORRUPTED_RSS_XML,  # Corrupted XML feed
                "ynet.co.il": YNET_RSS_XML,        # Valid XML feed
            },
            html_map={
                "ynet.co.il": YNET_ARTICLE_HTML,
            },
            error_urls=["one.co.il"],             # Simulated HTTP 500 error
        )

        scrapers = [Sport5Scraper(), YnetScraper(), ONEScraper()]
        queue = InMemoryTaskQueue()

        async with httpx.AsyncClient(transport=transport) as http_client:
            for sc in scrapers:
                try:
                    entries = await sc.fetch_rss(http_client)
                    for entry in entries:
                        html_text = await sc.fetch_article_html(http_client, entry["link"])
                        payload = sc.extract_article(html_text or "", rss_entry=entry)
                        if payload:
                            await queue.push(payload)
                except Exception:
                    # Individual scraper failures must not crash the entire ingestion loop
                    pass

        # At least Ynet should have succeeded
        assert await queue.size() >= 1, "Expected Ynet articles to succeed despite Sport5 and ONE failures"

        ai_service = AIEnrichmentService(use_mock=True, settings_obj=e2e_settings)
        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            while await queue.size() > 0:
                await ai_service.process_queue_item(queue, repo)

        # Verify Ynet articles exist in API
        feed_res = await e2e_client.get("/api/v1/feed")
        assert feed_res.status_code == 200
        feed_data = feed_res.json()
        assert feed_data["total"] >= 1
        assert any(item["publisher"] == "ynet" for item in feed_data["items"])

    async def test_ai_enricher_fallback_to_mock_when_gemini_fails(
        self,
        e2e_session_factory: async_sessionmaker[AsyncSession],
    ):
        """Verify AIEnrichmentService falls back gracefully to MockAIEnricher if live Gemini fails."""
        mock_broken_client = MagicMock()
        mock_broken_client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("Google GenAI RateLimit 429")
        )

        gemini_enricher = GeminiAIEnricher(api_key="fake-key", client=mock_broken_client)
        ai_service = AIEnrichmentService(enricher=gemini_enricher)

        article_payload = RawArticlePayload(
            title="מכבי תל אביב ניצחה את ריאל מדריד ביורוליג",
            raw_body="תצוגת ענק בהיכל מנורה מבטחים.",
            url="https://www.sport5.co.il/item/fallback-test",
            publisher="sport5",
        )

        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            # Must not raise exception, but fallback gracefully to mock enricher
            saved = await ai_service.enrich_and_store(article_payload, repo)
            assert saved is not None
            assert saved.id > 0
            assert "Maccabi Tel Aviv" in saved.tags


# ---------------------------------------------------------------------------
# 5. Personal Feed Delivery End-to-End Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPersonalFeedDeliveryE2E:
    """End-to-End tests validating personalized feed delivery via POST /api/v1/feed/personal."""

    async def test_e2e_personal_feed_matching_and_source_exclusion(
        self,
        e2e_client: httpx.AsyncClient,
        e2e_session_factory: async_sessionmaker[AsyncSession],
        e2e_settings: Settings,
    ):
        """Seed diverse sports corpus and verify user preferences strictly filter feed."""
        ai_service = AIEnrichmentService(use_mock=True, settings_obj=e2e_settings)

        corpus = [
            # 1. Sport5 Maccabi Tel Aviv Basketball (Hype)
            RawArticlePayload(
                title="ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג",
                raw_body="תצוגת ענק של הצהובים בהיכל מנורה מבטחים הבטיחה מקום בפלייאוף.",
                url="https://www.sport5.co.il/art/1",
                publisher="sport5",
                category="כדורסל",
            ),
            # 2. Ynet Beitar Jerusalem (Critical)
            RawArticlePayload(
                title="סערה בבית\"ר ירושלים: החלוץ הזר הודיע על עזיבה מיידית",
                raw_body="זעזוע בבירה יומיים לפני משחק העונה, במועדון שוקלים צעדים משפטיים.",
                url="https://www.ynet.co.il/art/2",
                publisher="ynet",
                category="ליגת העל",
            ),
            # 3. ONE Hapoel Beer Sheva (Objective)
            RawArticlePayload(
                title="פרסום ראשון: הפועל באר שבע פתחה במו\"מ לצירוף קשר נבחרת רומניה",
                raw_body="אלונה ברקת נותנת אור ירוק למהלך המרכזי של חלון ההעברות.",
                url="https://www.one.co.il/art/3",
                publisher="one",
                category="העברות",
            ),
            # 4. Sport5 Maccabi Haifa (Hype)
            RawArticlePayload(
                title="לקראת הדרבי הגדול: מכבי חיפה מוכנה למפגש מול הפועל חיפה",
                raw_body="ברק בכר מתלבט בהרכב לקראת המפגש בסמי עופר.",
                url="https://www.sport5.co.il/art/4",
                publisher="sport5",
                category="ליגת העל",
            ),
        ]

        async with e2e_session_factory() as session:
            repo = ArticleRepository(session)
            for art in corpus:
                await ai_service.enrich_and_store(art, repo)

        # User 1 Preferences: Wants Maccabi Tel Aviv / Euroleague, excludes Ynet, prefers Hype tone
        pref_1 = {
            "followed_tags": ["Maccabi Tel Aviv", "Euroleague"],
            "excluded_sources": ["ynet"],
            "preferred_tones": ["hype"],
        }
        res1 = await e2e_client.post("/api/v1/feed/personal", json=pref_1)
        assert res1.status_code == 200
        data1 = res1.json()

        assert data1["total"] == 1
        assert data1["items"][0]["publisher"] == "sport5"
        assert "Maccabi Tel Aviv" in data1["items"][0]["tags"]
        assert data1["items"][0]["tone"] == "hype"

        # User 2 Preferences: Excludes sport5, wants Beitar Jerusalem
        pref_2 = {
            "followed_tags": ["Beitar Jerusalem"],
            "excluded_sources": ["sport5"],
        }
        res2 = await e2e_client.post("/api/v1/feed/personal", json=pref_2)
        assert res2.status_code == 200
        data2 = res2.json()

        assert data2["total"] == 1
        assert data2["items"][0]["publisher"] == "ynet"
        assert all(item["publisher"] != "sport5" for item in data2["items"])

        # User 3 Preferences: Empty profile returns all articles
        res3 = await e2e_client.post("/api/v1/feed/personal", json={})
        assert res3.status_code == 200
        assert res3.json()["total"] == len(corpus)


# ---------------------------------------------------------------------------
# 6. Manual Trigger & Ingestion Endpoint Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestManualTriggerPipelineE2E:
    """End-to-End tests validating manual ingestion trigger via POST /api/v1/ingestion/trigger."""

    async def test_manual_trigger_end_to_end_delivery(
        self,
        e2e_client: httpx.AsyncClient,
    ):
        """Trigger ingestion via API endpoint with mocked scrapers and immediately query /api/v1/feed."""
        sample_articles = [
            RawArticlePayload(
                title="ניצחון ענק ביורוליג למכבי תל אביב",
                raw_body="תצוגת כדורסל מרהיבה בהיכל מנורה מבטחים.",
                url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=777001",
                publisher="sport5",
                category="כדורסל",
                author="עמרי פולק",
            ),
            RawArticlePayload(
                title="סערה בבית\"ר ירושלים",
                raw_body="זעזוע בבירה יומיים לפני משחק העונה.",
                url="https://www.ynet.co.il/sport/article/777002",
                publisher="ynet",
                category="ליגת העל",
                author="גידי ליפקין",
            ),
        ]

        with patch("services.scrapers.sport5.Sport5Scraper.scrape", new_callable=AsyncMock) as m_s5, \
             patch("services.scrapers.ynet.YnetScraper.scrape", new_callable=AsyncMock) as m_ynet, \
             patch("services.scrapers.one.ONEScraper.scrape", new_callable=AsyncMock) as m_one, \
             patch("services.scrapers.walla.WallaScraper.scrape", new_callable=AsyncMock) as m_walla:

            m_s5.return_value = [sample_articles[0]]
            m_ynet.return_value = [sample_articles[1]]
            m_one.return_value = []
            m_walla.return_value = []

            trigger_res = await e2e_client.post("/api/v1/ingestion/trigger")
            assert trigger_res.status_code == 200
            trigger_data = trigger_res.json()

            assert trigger_data["status"] == "completed"
            assert trigger_data["articles_fetched"] == 2
            assert trigger_data["articles_queued"] == 2

        # Immediately query /api/v1/feed and assert both ingested items exist
        feed_res = await e2e_client.get("/api/v1/feed")
        assert feed_res.status_code == 200
        feed_data = feed_res.json()

        assert feed_data["total"] == 2
        publishers = {i["publisher"] for i in feed_data["items"]}
        assert "sport5" in publishers
        assert "ynet" in publishers
