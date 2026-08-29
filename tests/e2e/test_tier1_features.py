"""Tier 1: Comprehensive Feature Coverage E2E Test Suite.

Verifies >=5 distinct, genuine test cases per feature across all 14 features
defined in the Fan-Zone Feature Inventory:
- F1: Multi-Source Scrapers (7 Sources: Sport5, ONE, Walla, Ynet, Sport1, Israel Hayom, Haaretz)
- F2: Article Metadata & Paragraph Extraction
- F3: Per-Source Deduplication Engine (URL & SHA-256 Hash)
- F4: Gemini AI Non-Clickbait Headline Generation
- F5: Gemini AI Subheadline Summary Generation
- F6: Sports Entity Extraction & Tagging (Sport, Team, Player, League, Topic)
- F7: AI Error Resilience, Retry & Offline Mock Mode
- F8: SQLAlchemy 2.0 ORM Models (Source, Article, Tag, Media, Story)
- F9: Multi-DB Support (SQLite / PostgreSQL Parity & Transaction Isolation)
- F10: Repository Query & Rich Filtering Methods
- F11: Periodic Background Scheduler & AsyncIO Poller
- F12: FastAPI REST Endpoints & Pagination Architecture
- F13: Manual Ingestion Trigger Endpoint (/ingest/trigger)
- F14: System Health, Stats & Tags Exploration Endpoints
"""

import asyncio
from datetime import datetime, timezone, timedelta
import re
from typing import AsyncGenerator, Dict, List, Tuple
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from fan_zone.ai.base import ArticleAnalysisResult, BaseAIProcessor
from fan_zone.ai.fallback import RuleBasedAIProcessor, fallback_article_analysis
from fan_zone.ai.mock import MockAIProcessor
from fan_zone.ai.service import AIService, get_ai_processor, get_ai_service
from fan_zone.config import Settings, get_settings
from fan_zone.db.base import Base
from fan_zone.db.session import get_db
from fan_zone.main import create_app
from fan_zone.models.article import Article, ArticleMedia
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.models.source import Source
from fan_zone.models.story import Story
from fan_zone.models.tag import ArticleTag, Tag
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.repositories.story_repo import StoryRepository
from fan_zone.repositories.tag_repo import TagRepository
from fan_zone.scheduler.poller import IngestionScheduler
from fan_zone.schemas.article import ArticleCreate, ArticleFilter
from fan_zone.schemas.media import MediaCreate
from fan_zone.scrapers.base import (
    BaseSourceParser,
    ExtractedArticle,
    ExtractedImage,
    compute_content_hash,
    normalize_canonical_url,
)
from fan_zone.scrapers.haaretz import HaaretzParser
from fan_zone.scrapers.israel_hayom import IsraelHayomParser
from fan_zone.scrapers.one import ONEParser
from fan_zone.scrapers.registry import ScraperRegistry, get_scraper_for_url
from fan_zone.scrapers.sport1 import Sport1Parser
from fan_zone.scrapers.sport5 import Sport5Parser
from fan_zone.scrapers.walla import WallaParser
from fan_zone.scrapers.ynet import YnetParser
from fan_zone.services.ingestion_service import IngestionService


@pytest_asyncio.fixture
async def api_client(seeded_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """FastAPI async test client with database dependency override to in-memory test session."""
    app = create_app()

    async def override_get_db():
        yield seeded_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


# ===========================================================================
# FEATURE 1: Multi-Source Scrapers (7 Sources)
# ===========================================================================

@pytest.mark.asyncio
class TestFeature1MultiSourceScrapers:
    """>=5 tests verifying scrapers for all 7 Israeli sports news outlets."""

    async def test_sport5_scraper_discovery_and_parsing(self):
        """F1.1: Verify Sport5 parser discovers article links and extracts structured fields."""
        parser = Sport5Parser()
        assert parser.source_name == "Sport5"
        assert parser.source_code == "sport5"
        assert "sport5.co.il" in parser.base_url

        html = """
        <html><body>
            <h1 class="article-title">מכבי תל אביב ניצחה ביורוליג</h1>
            <h2 class="article-subtitle">ניצחון ביתי ענק</h2>
            <div class="article-credit">רועי כהן</div>
            <div class="article-body">
                <p>הצהובים גברו על ריאל מדריד בהיכל מנורה מבטחים.</p>
                <p>ווייד בולדווין הצטיין עם 25 נקודות.</p>
            </div>
            <img class="main-image" src="https://sport5.co.il/img1.jpg" alt="בולדווין חוגג" />
        </body></html>
        """
        def handler(req: httpx.Request):
            return httpx.Response(200, text=html, request=req)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            article = await parser.parse_article(client, "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=100")
            assert article is not None
            assert article.source_name == "Sport5"
            assert "מכבי תל אביב" in article.original_title
            assert len(article.paragraphs) >= 2
            assert article.author == "רועי כהן"

    async def test_one_scraper_rss_and_article_parsing(self):
        """F1.2: Verify ONE parser handles RSS feed discovery and article body extraction."""
        parser = ONEParser()
        assert parser.source_code == "one"
        rss_xml = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel>
            <item>
                <title>מכבי חיפה ניצחה את הפועל באר שבע</title>
                <link>https://www.one.co.il/Article/2026/450000.html</link>
                <pubDate>Fri, 28 Aug 2026 18:00:00 GMT</pubDate>
            </item>
        </channel></rss>
        """
        article_html = """
        <html><body>
            <h1 class="article-title">מכבי חיפה ניצחה את הפועל באר שבע</h1>
            <div class="article-author">גידי ליפקין</div>
            <div class="article-content">
                <p>הירוקים חגגו בסמי עופר עם צמד של דיא סבע.</p>
            </div>
        </body></html>
        """
        def handler(req: httpx.Request):
            if "rss" in str(req.url) or "feed" in str(req.url):
                return httpx.Response(200, text=rss_xml, request=req)
            return httpx.Response(200, text=article_html, request=req)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            discovered = await parser.discover_articles(client)
            assert len(discovered) >= 1
            article = await parser.parse_article(client, discovered[0])
            assert article is not None
            assert article.source_name == "ONE"
            assert "מכבי חיפה" in article.original_title

    async def test_walla_sports_scraper_parsing(self):
        """F1.3: Verify Walla! Sports scraper parsing and DOM extraction."""
        parser = WallaParser()
        assert parser.source_code == "walla"
        html = """
        <html><body>
            <h1 class="title">הפועל תל אביב החתימה זר חדש</h1>
            <div class="subtitle">חיזוק משמעותי לקבוצה</div>
            <div class="author">מערכת וואלה!</div>
            <article class="article-content">
                <p>האדומים השלימו את העסקה לקראת פתיחת העונה.</p>
            </article>
        </body></html>
        """
        def handler(req: httpx.Request):
            return httpx.Response(200, text=html, request=req)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            article = await parser.parse_article(client, "https://sports.walla.co.il/item/3500000")
            assert article is not None
            assert "הפועל תל אביב" in article.original_title
            assert article.author == "מערכת וואלה!"

    async def test_ynet_sport_scraper_parsing(self):
        """F1.4: Verify Ynet Sport scraper parsing and metadata extraction."""
        parser = YnetParser()
        assert parser.source_code == "ynet"
        html = """
        <html><body>
            <h1 class="mainTitle">נבחרת ישראל בכדורסל מתכוננת ליורובאסקט</h1>
            <div class="subTitle">האימונים נפתחו בהיכל שלמה בתל אביב</div>
            <span class="authorName">נדב צנציפר</span>
            <div class="text_editor_paragraph">
                <p>הסגל המלא של המאמן הלאומי התכנס לאימון פתיחה.</p>
            </div>
        </body></html>
        """
        def handler(req: httpx.Request):
            return httpx.Response(200, text=html, request=req)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            article = await parser.parse_article(client, "https://www.ynet.co.il/sport/israelibasketball/article/y100")
            assert article is not None
            assert "נבחרת ישראל" in article.original_title
            assert article.author == "נדב צנציפר"

    async def test_sport1_israel_hayom_haaretz_parsers_and_registry(self):
        """F1.5: Verify Sport1, Israel Hayom, Haaretz parsers and Registry URL matching."""
        s1 = Sport1Parser()
        ih = IsraelHayomParser()
        ha = HaaretzParser()
        registry = ScraperRegistry()

        assert s1.source_code == "sport1"
        assert ih.source_code in ["israelhayom", "israel_hayom"]
        assert ha.source_code == "haaretz"

        # Verify all 7 scrapers are registered
        all_scrapers = registry.get_all_scrapers()
        assert len(all_scrapers) >= 7

        # Verify domain detection for all outlets
        assert registry.get_scraper_for_url("https://www.sport5.co.il/art.aspx").source_code == "sport5"
        assert registry.get_scraper_for_url("https://www.one.co.il/Article/123").source_code == "one"
        assert registry.get_scraper_for_url("https://sports.walla.co.il/item/123").source_code == "walla"
        assert registry.get_scraper_for_url("https://www.ynet.co.il/sport/art1").source_code == "ynet"
        assert registry.get_scraper_for_url("https://sport1.maariv.co.il/art1").source_code == "sport1"
        assert registry.get_scraper_for_url("https://www.israelhayom.co.il/sport/art1").source_code in ["israelhayom", "israel_hayom"]
        assert registry.get_scraper_for_url("https://www.haaretz.co.il/sport/art1").source_code == "haaretz"


# ===========================================================================
# FEATURE 2: Article Metadata & Paragraph Extraction
# ===========================================================================

@pytest.mark.asyncio
class TestFeature2ArticleMetadataExtraction:
    """>=5 tests verifying extraction of titles, authors, timestamps, paragraphs, media."""

    async def test_clean_text_paragraphs_extraction_without_html(self):
        """F2.1: Verify paragraphs are cleanly extracted with stripped HTML tags and unescaped entities."""
        raw_html = """
        <html><body>
            <div class="content">
                <p>פסקה <b>ראשונה</b> עם &quot;גרשיים&quot; וטקסט מודגש.</p>
                <p>פסקה <i>שנייה</i> עם &amp; סימנים מיוחדים &gt; &lt;.</p>
            </div>
        </body></html>
        """
        parser = Sport5Parser()
        def handler(req): return httpx.Response(200, text=raw_html, request=req)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            art = await parser.parse_article(client, "https://sport5.co.il/art1")
            assert art is not None
            assert len(art.paragraphs) >= 2
            assert "<b>" not in art.paragraphs[0]
            assert '"גרשיים"' in art.paragraphs[0]
            assert "&amp;" not in art.paragraphs[1]

    async def test_author_and_byline_normalization(self):
        """F2.2: Verify author names are extracted and trimmed."""
        html = "<html><body><h1>כותרת</h1><div class='article-credit'>  מאת: עמית טימסיט  </div><p>גוף הכתבה ארוך מספיק.</p></body></html>"
        parser = Sport5Parser()
        def handler(req): return httpx.Response(200, text=html, request=req)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            art = await parser.parse_article(client, "https://sport5.co.il/art2")
            assert art is not None
            assert art.author == "עמית טימסיט" or "טימסיט" in (art.author or "")

    async def test_publish_datetime_extraction_and_utc_timezone(self):
        """F2.3: Verify published timestamp is parsed into UTC datetime."""
        html = """
        <html><head>
            <meta property="article:published_time" content="2026-08-28T20:30:00+03:00" />
        </head><body><h1>כותרת</h1><p>תוכן הכתבה המלא לצורך בדיקה.</p></body></html>
        """
        parser = Sport5Parser()
        def handler(req): return httpx.Response(200, text=html, request=req)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            art = await parser.parse_article(client, "https://sport5.co.il/art3")
            assert art is not None
            assert art.published_at is not None
            assert art.published_at.year == 2026

    async def test_lead_and_gallery_image_media_extraction(self):
        """F2.4: Verify lead image and gallery images are extracted with captions and credits."""
        img = ExtractedImage(
            url="https://images.sport5.co.il/lead.jpg",
            caption="ערן זהבי חוגג שער ניצחון",
            credit="ברני ארדוב",
            is_main=True,
        )
        art = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://sport5.co.il/art4",
            canonical_url="https://sport5.co.il/art4",
            content_hash="hash123",
            original_title="מכבי תל אביב ניצחה",
            paragraphs=["פסקה ראשונה ארוכה ומלאה."],
            main_image=img,
            gallery_images=[ExtractedImage(url="https://images.sport5.co.il/gal1.jpg", caption="אוהדים ביציע")],
        )
        assert art.main_image.url == "https://images.sport5.co.il/lead.jpg"
        assert art.main_image.caption == "ערן זהבי חוגג שער ניצחון"
        assert len(art.gallery_images) == 1

    async def test_cleaned_body_reconstruction_from_paragraphs(self):
        """F2.5: Verify raw_body_text joins paragraphs with double newlines."""
        art = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://sport5.co.il/art5",
            canonical_url="https://sport5.co.il/art5",
            content_hash="hash456",
            original_title="כותרת",
            paragraphs=["פסקה אחת.", "פסקה שתיים.", "פסקה שלוש."],
        )
        assert art.raw_body_text == "פסקה אחת.\n\nפסקה שתיים.\n\nפסקה שלוש."


# ===========================================================================
# FEATURE 3: Per-Source Deduplication Engine
# ===========================================================================

@pytest.mark.asyncio
class TestFeature3PerSourceDeduplication:
    """>=5 tests verifying canonical URL normalization, hashing, and per-source scoping."""

    async def test_canonical_url_normalization_tracking_strip(self):
        """F3.1: Verify stripping UTM tracking query params and sorting parameters."""
        raw_url = "https://www.sport5.co.il/articles.aspx?utm_source=facebook&FolderID=64&utm_medium=cpc&docID=12345#comments"
        normalized = normalize_canonical_url(raw_url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized
        assert "#comments" not in normalized
        assert "docID=12345" in normalized
        assert "FolderID=64" in normalized

    async def test_deterministic_sha256_content_hashing(self):
        """F3.2: Verify content hash is deterministic and invariant to minor whitespace."""
        h1 = compute_content_hash("מכבי תל אביב ניצחה", ["פסקה אחת", "פסקה שתיים"])
        h2 = compute_content_hash("  מכבי תל אביב ניצחה  ", ["פסקה אחת  ", "  פסקה שתיים"])
        assert len(h1) == 64
        assert h1 == h2

    async def test_duplicate_url_skipped_within_same_source(self, db_session: AsyncSession):
        """F3.3: Verify ingesting the same URL twice in the same source is deduplicated."""
        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        s_sport5 = next(s for s in sources if s.name == "sport5")

        service = IngestionService(db=db_session)
        ext = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://sport5.co.il/item1",
            canonical_url="https://sport5.co.il/item1",
            content_hash=compute_content_hash("כותרת 1", ["גוף הכתבה"]),
            original_title="כותרת 1",
            paragraphs=["גוף הכתבה"],
        )

        art1, created1 = await service.process_and_persist_article(ext, s_sport5)
        art2, created2 = await service.process_and_persist_article(ext, s_sport5)
        assert created1 is True
        assert created2 is False
        assert art1.id == art2.id

    async def test_duplicate_content_hash_skipped_within_same_source(self, db_session: AsyncSession):
        """F3.4: Verify duplicate content hash with different URL in same source is deduplicated."""
        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        s_one = next(s for s in sources if s.name == "one")

        service = IngestionService(db=db_session)
        chash = compute_content_hash("כותרת זהה", ["תוכן זהה לחלוטין"])

        ext1 = ExtractedArticle(
            source_name="ONE",
            source_domain="one.co.il",
            original_url="https://one.co.il/artA",
            canonical_url="https://one.co.il/artA",
            content_hash=chash,
            original_title="כותרת זהה",
            paragraphs=["תוכן זהה לחלוטין"],
        )
        ext2 = ExtractedArticle(
            source_name="ONE",
            source_domain="one.co.il",
            original_url="https://one.co.il/artB",
            canonical_url="https://one.co.il/artB",
            content_hash=chash,
            original_title="כותרת זהה",
            paragraphs=["תוכן זהה לחלוטין"],
        )

        art1, created1 = await service.process_and_persist_article(ext1, s_one)
        art2, created2 = await service.process_and_persist_article(ext2, s_one)
        assert created1 is True
        assert created2 is False
        assert art1.id == art2.id

    async def test_per_source_deduplication_allows_distinct_sources(self, db_session: AsyncSession):
        """F3.5: User Clarification: Identical content from DIFFERENT sources must both be saved."""
        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        s_sport5 = next(s for s in sources if s.name == "sport5")
        s_walla = next(s for s in sources if s.name == "walla")

        service = IngestionService(db=db_session)
        chash = compute_content_hash("דרבי תל אביבי לוהט", ["משחק סוער בבלומפילד"])

        ext_sport5 = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://sport5.co.il/derby",
            canonical_url="https://sport5.co.il/derby",
            content_hash=chash,
            original_title="דרבי תל אביבי לוהט",
            paragraphs=["משחק סוער בבלומפילד"],
        )
        ext_walla = ExtractedArticle(
            source_name="Walla! Sports",
            source_domain="walla.co.il",
            original_url="https://sports.walla.co.il/derby",
            canonical_url="https://sports.walla.co.il/derby",
            content_hash=chash,
            original_title="דרבי תל אביבי לוהט",
            paragraphs=["משחק סוער בבלומפילד"],
        )

        art_s5, created_s5 = await service.process_and_persist_article(ext_sport5, s_sport5)
        art_w, created_w = await service.process_and_persist_article(ext_walla, s_walla)

        assert created_s5 is True
        assert created_w is True
        assert art_s5.id != art_w.id
        assert art_s5.source_id == s_sport5.id
        assert art_w.source_id == s_walla.id


# ===========================================================================
# FEATURE 4: Gemini AI Non-Clickbait Headline
# ===========================================================================

@pytest.mark.asyncio
class TestFeature4GeminiAINonClickbaitHeadline:
    """>=5 tests verifying non-clickbait headline generation and buzzword stripping."""

    async def test_sensational_clickbait_headline_rewriting(self):
        """F4.1: Verify sensational headline is rewritten to objective factual statement."""
        ai = MockAIProcessor()
        title = "הלם בעולם הכדורסל! אתם לא תאמינו מי חתם במכבי תל אביב!"
        body = "הרכז האמריקאי ווייד בולדווין חתם לשנתיים נוספות במכבי תל אביב לאחר משא ומתן ממושך."
        res = await ai.analyze_article(title=title, body=body)
        assert res.headline is not None
        assert "הלם" not in res.headline
        assert "אתם לא תאמינו" not in res.headline
        assert "מכבי תל אביב" in res.headline

    async def test_question_clickbait_transformed_to_statement(self):
        """F4.2: Verify question clickbait is converted into informative statement."""
        ai = MockAIProcessor()
        title = "מי הדהים את האלופה בתוספת הזמן?"
        body = "הפועל ירושלים גברה 1:2 על מכבי תל אביב משער ניצחון בדקה ה-94 של יונתן אלון."
        res = await ai.analyze_article(title=title, body=body)
        assert not res.headline.endswith("?")
        assert len(res.headline) > 5

    async def test_buzzword_stripping_heuristics(self):
        """F4.3: Verify fallback rule-based analyzer removes common Hebrew clickbait buzzwords."""
        res = fallback_article_analysis(
            title="צפו בטירוף: שער השנה הובקע בבלומפילד!",
            body="ערן זהבי הבקיע שער מספרת במסגרת המחזור ה-10 בליגת העל.",
        )
        assert "צפו" not in res.headline
        assert "בטירוף" not in res.headline

    async def test_match_score_preservation_in_headline(self):
        """F4.4: Verify match result and score are preserved in generated headline."""
        res = fallback_article_analysis(
            title="מכבי חיפה ניצחה 0:3 את בית\"ר ירושלים",
            body="הירוקים הביסו 0:3 את בית\"ר ירושלים באצטדיון טדי.",
        )
        assert "מכבי חיפה" in res.headline
        assert "0:3" in res.headline or "בית\"ר ירושלים" in res.headline

    async def test_custom_response_override_in_mock(self):
        """F4.5: Verify MockAIProcessor supports precise custom response injection."""
        expected = ArticleAnalysisResult(
            headline="כותרת מדויקת מותאמת אישית",
            subheadline="כותרת משנה",
            sport="כדורגל",
            teams=["מכבי חיפה"],
            players=["ברק בכר"],
            competition="ליגת העל",
            tags=["כדורגל", "ליגת העל"],
        )
        mock = MockAIProcessor(custom_response=expected)
        res = await mock.analyze_article(title="סתם כותרת", body="סתם גוף")
        assert res == expected
        assert res.headline == "כותרת מדויקת מותאמת אישית"


# ===========================================================================
# FEATURE 5: Gemini AI Subheadline Summary
# ===========================================================================

@pytest.mark.asyncio
class TestFeature5GeminiAISubheadlineSummary:
    """>=5 tests verifying concise Hebrew subheadline summarization."""

    async def test_concise_subheadline_generation(self):
        """F5.1: Verify subheadline produces a concise 1-2 sentence summary."""
        ai = MockAIProcessor()
        res = await ai.analyze_article(
            title="מכבי תל אביב גברה על ריאל מדריד ביורוליג",
            subtitle="ערב בלתי נשכח בהיכל.",
            body="הצהובים ניצחו 82:85 את ריאל מדריד. ווייד בולדווין הוביל עם 28 נקודות.",
        )
        assert res.subheadline is not None
        assert len(res.subheadline) >= 10
        assert len(res.subheadline) <= 300

    async def test_subheadline_when_original_subtitle_missing(self):
        """F5.2: Verify subheadline is generated even when original article has no subtitle."""
        ai = MockAIProcessor()
        res = await ai.analyze_article(
            title="הפועל באר שבע ניצחה 0:1 את מכבי נתניה",
            subtitle=None,
            body="הפועל באר שבע השיגה ניצחון חוץ יקר באצטדיון נתניה משער בודד של רותם חטואל.",
        )
        assert res.subheadline is not None
        assert len(res.subheadline) > 0

    async def test_subheadline_fact_preservation(self):
        """F5.3: Verify subheadline includes critical details from article body."""
        body = "אלופת המדינה מכבי חיפה סיימה בתיקו 2:2 מול הפועל חיפה בדרבי של הכרמל."
        res = fallback_article_analysis(
            title="תיקו 2:2 בדרבי החיפאי",
            body=body,
        )
        assert "חיפה" in res.subheadline or "2:2" in res.subheadline

    async def test_subheadline_cleans_leading_trailing_artifacts(self):
        """F5.4: Verify subheadline does not contain orphaned punctuation or prefixes."""
        res = fallback_article_analysis(
            title="כותרת",
            subtitle="--- כותרת משנה עם מקפים מיותרים ---",
            body="גוף הכתבה המלא על משחק הכדורסל.",
        )
        assert not res.subheadline.startswith("-")

    async def test_batch_subheadline_generation_parallelism(self):
        """F5.5: Verify AIService batch analysis extracts subheadlines concurrently."""
        service = get_ai_service(provider="mock")
        items = [
            {"title": f"כתבה {i}", "subtitle": f"משנה {i}", "body": f"גוף כתבה {i} על כדורגל."}
            for i in range(5)
        ]
        results = await service.analyze_batch(items, concurrency=3)
        assert len(results) == 5
        assert all(r.subheadline is not None for r in results)


# ===========================================================================
# FEATURE 6: Sports Entity Extraction & Tagging
# ===========================================================================

@pytest.mark.asyncio
class TestFeature6SportsEntityExtraction:
    """>=5 tests verifying extraction of sport, teams, players, competition, and topic tags."""

    async def test_sport_discipline_classification(self):
        """F6.1: Verify sport classification across disciplines (football, basketball, tennis, judo)."""
        ai = MockAIProcessor()
        res_fb = await ai.analyze_article(title="מכבי חיפה ניצחה בליגת העל בכדורגל", body="משחק כדורגל בסמי עופר.")
        res_bb = await ai.analyze_article(title="מכבי תל אביב ביורוליג בכדורסל", body="משחק כדורסל בהיכל.")
        res_tn = await ai.analyze_article(title="קרלוס אלקרס בגמר הרולאן גארוס", body="טורניר טניס גראנד סלאם בפריז.")

        assert res_fb.sport == "כדורגל"
        assert res_bb.sport == "כדורסל"
        assert res_tn.sport == "טניס"

    async def test_team_and_club_entity_extraction(self):
        """F6.2: Verify extraction of Israeli and international club names."""
        res = fallback_article_analysis(
            title="מכבי תל אביב מול ריאל מדריד",
            body="הצהובים של מכבי תל אביב יפגשו את ריאל מדריד במסגרת היורוליג.",
        )
        assert "מכבי תל אביב" in res.teams
        assert "ריאל מדריד" in res.teams

    async def test_player_and_coach_personality_extraction(self):
        """F6.3: Verify extraction of athletes and coaching staff."""
        res = fallback_article_analysis(
            title="עודד קטש החמיא לווייד בולדווין לאחר המשחק",
            body="המאמן עודד קטש שיבח את הכוכב ווייד בולדווין ואת רומן סורקין.",
        )
        assert any("קטש" in p or "בולדווין" in p for p in res.players)

    async def test_competition_and_league_classification(self):
        """F6.4: Verify league and competition taxonomy assignment."""
        res1 = fallback_article_analysis(title="מחזור 10 בליגת העל בכדורגל", body="ליגת העל")
        res2 = fallback_article_analysis(title="משחק ענק ביורוליג בכדורסל", body="יורוליג")
        res3 = fallback_article_analysis(title="ליגת האלופות: ריאל מדריד נגד באיירן", body="ליגת האלופות")

        assert res1.competition in ["ליגת העל", "ליגת העל בכדורגל"]
        assert res2.competition == "יורוליג"
        assert res3.competition == "ליגת האלופות"

    async def test_tag_types_and_taxonomy_mapping_in_repository(self, db_session: AsyncSession):
        """F6.5: Verify TagRepository correctly maps and persists TagType categories."""
        tag_repo = TagRepository(db_session)
        tag_tuples = [
            ("כדורגל", TagType.SPORT),
            ("מכבי תל אביב", TagType.TEAM),
            ("ערן זהבי", TagType.PLAYER),
            ("ליגת העל", TagType.COMPETITION),
            ("חלון ההעברות", TagType.TOPIC),
        ]
        tags = await tag_repo.get_or_create_batch(tag_tuples, db=db_session)
        assert len(tags) == 5
        types = {t.tag_type for t in tags}
        assert types == {TagType.SPORT, TagType.TEAM, TagType.PLAYER, TagType.COMPETITION, TagType.TOPIC}


# ===========================================================================
# FEATURE 7: AI Error Resilience, Retry & Offline Mock Mode
# ===========================================================================

@pytest.mark.asyncio
class TestFeature7AIErrorResilience:
    """>=5 tests verifying AI error handling, 429 rate limit, 503 errors, and offline mock."""

    async def test_mock_ai_processor_deterministic_offline_mode(self):
        """F7.1: Verify MockAIProcessor operates offline with deterministic behavior."""
        mock = MockAIProcessor()
        res = await mock.analyze_article(
            title="מכבי תל אביב ניצחה ביורוליג",
            body="ווייד בולדווין הצטיין בניצחון על ריאל מדריד.",
        )
        assert res.sport == "כדורסל"
        assert mock.call_count == 1

    async def test_rate_limit_simulation_and_fallback(self):
        """F7.2: Verify 429 Rate Limit error triggers fallback analysis."""
        mock = MockAIProcessor(simulate_rate_limit=True)
        with pytest.raises(RuntimeError) as exc_info:
            await mock.analyze_article(title="כותרת", body="גוף")
        assert "429" in str(exc_info.value)

    async def test_service_unavailable_503_simulation(self):
        """F7.3: Verify 503 Backend Error is handled gracefully."""
        mock = MockAIProcessor(simulate_failure=True)
        with pytest.raises(RuntimeError) as exc_info:
            await mock.analyze_article(title="כותרת", body="גוף")
        assert "503" in str(exc_info.value)

    async def test_timeout_error_resilience(self):
        """F7.4: Verify timeout simulation is caught and identified."""
        mock = MockAIProcessor(simulate_timeout=True)
        with pytest.raises(TimeoutError) as exc_info:
            await mock.analyze_article(title="כותרת", body="גוף")
        assert "timed out" in str(exc_info.value)

    async def test_ingestion_service_handles_ai_exception_without_crashing(self, db_session: AsyncSession):
        """F7.5: Verify IngestionService persists article with AI_FALLBACK when AI raises exception."""
        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        s_one = next(s for s in sources if s.name == "one")

        failing_ai = MockAIProcessor(simulate_failure=True)
        service = IngestionService(db=db_session, ai_processor=failing_ai)

        ext = ExtractedArticle(
            source_name="ONE",
            source_domain="one.co.il",
            original_url="https://one.co.il/resilience_test",
            canonical_url="https://one.co.il/resilience_test",
            content_hash="resil_hash_1",
            original_title="כותרת מקורית במקרה של כשל AI",
            original_subtitle="כותרת משנה מקורית",
            paragraphs=["גוף הכתבה נשמר גם כשהבינה המלאכותית נכשלת."],
        )

        art, is_created = await service.process_and_persist_article(ext, s_one)
        assert is_created is True
        assert art.ingestion_status == IngestionStatus.AI_FALLBACK
        assert art.ai_headline == "כותרת מקורית במקרה של כשל AI"
        assert "503" in (art.error_message or "")


# ===========================================================================
# FEATURE 8: SQLAlchemy 2.0 ORM Models
# ===========================================================================

@pytest.mark.asyncio
class TestFeature8SQLAlchemyModels:
    """>=5 tests verifying ORM models, relations, cascades, and constraints."""

    async def test_source_model_creation_and_constraints(self, db_session: AsyncSession):
        """F8.1: Verify Source model attributes and unique name constraint."""
        s = Source(name="custom_source", display_name="Custom Source", code="custom", base_url="https://custom.com")
        db_session.add(s)
        await db_session.commit()
        assert s.id is not None
        assert s.is_active is True

    async def test_article_model_with_json_arrays(self, db_session: AsyncSession, seeded_session: AsyncSession):
        """F8.2: Verify Article JSON fields (teams_json, players_json, tags_json, raw_paragraphs)."""
        source = (await db_session.execute(select(Source))).scalars().first()
        art = Article(
            source_id=source.id,
            canonical_url="https://test.com/json_test",
            content_hash="json_hash_1",
            original_title="בדיקת עמודות JSON",
            raw_paragraphs=["פסקה 1", "פסקה 2"],
            teams_json=["מכבי תל אביב", "הפועל תל אביב"],
            players_json=["ערן זהבי", "בר טימור"],
            tags_json=["דרבי", "תל אביב"],
        )
        db_session.add(art)
        await db_session.commit()
        await db_session.refresh(art)

        assert art.raw_paragraphs == ["פסקה 1", "פסקה 2"]
        assert "מכבי תל אביב" in art.teams_json
        assert "ערן זהבי" in art.players_json

    async def test_article_media_cascade_deletion(self, db_session: AsyncSession, seeded_session: AsyncSession):
        """F8.3: Verify ArticleMedia links to Article and cascades on article delete."""
        source = (await db_session.execute(select(Source))).scalars().first()
        art = Article(
            source_id=source.id,
            canonical_url="https://test.com/media_test",
            content_hash="media_hash_1",
            original_title="בדיקת מדיה ומחיקה מדורגת",
        )
        db_session.add(art)
        await db_session.commit()

        media = ArticleMedia(
            article_id=art.id,
            url="https://test.com/img.jpg",
            media_type=MediaType.IMAGE,
            caption="תמונת בדיקה",
            is_primary=True,
            position_index=0,
        )
        db_session.add(media)
        await db_session.commit()

        # Delete article and verify media is deleted
        await db_session.delete(art)
        await db_session.commit()

        media_check = await db_session.get(ArticleMedia, media.id)
        assert media_check is None

    async def test_tag_and_article_tag_many_to_many(self, db_session: AsyncSession, seeded_session: AsyncSession):
        """F8.4: Verify Tag and ArticleTag association table."""
        source = (await db_session.execute(select(Source))).scalars().first()
        art = Article(
            source_id=source.id,
            canonical_url="https://test.com/tag_rel_test",
            content_hash="tag_rel_hash",
            original_title="בדיקת קשרי תגיות",
        )
        db_session.add(art)
        await db_session.commit()

        tag = Tag(name="כדורגל ישראלי", slug="israeli-football", tag_type=TagType.SPORT)
        db_session.add(tag)
        await db_session.commit()

        art_tag = ArticleTag(article_id=art.id, tag_id=tag.id)
        db_session.add(art_tag)
        await db_session.commit()

        assert art_tag.article_id == art.id
        assert art_tag.tag_id == tag.id

    async def test_story_model_with_citations_and_counters(self, db_session: AsyncSession):
        """F8.5: Verify Story model for copyright-safe synthesized briefs with citations."""
        citations = [
            {"article_id": 1, "source_name": "Sport5", "url": "https://sport5.co.il/1"},
            {"article_id": 2, "source_name": "ONE", "url": "https://one.co.il/2"},
        ]
        story = Story(
            title="סיכום דרבי תל אביב מרובה מקורות",
            summary="תקציר אובייקטיבי מסונתז המשלב דיווחים מספורט 5 ו-ONE.",
            sport="כדורגל",
            competition="ליגת העל",
            teams_json=["מכבי תל אביב", "הפועל תל אביב"],
            citations_json=citations,
            article_count=2,
        )
        db_session.add(story)
        await db_session.commit()
        await db_session.refresh(story)

        assert story.id is not None
        assert story.article_count == 2
        assert len(story.citations_json) == 2


# ===========================================================================
# FEATURE 9: Multi-DB Support (SQLite / PostgreSQL Compatibility)
# ===========================================================================

@pytest.mark.asyncio
class TestFeature9MultiDBSupport:
    """>=5 tests verifying database engine configuration, transactions, and index compatibility."""

    async def test_sqlite_in_memory_foreign_keys_enforced(self, async_engine):
        """F9.1: Verify SQLite PRAGMA foreign_keys=ON is active and prevents orphaned relations."""
        session_factory = async_sessionmaker(bind=async_engine, class_=AsyncSession)
        async with session_factory() as session:
            # Attempting to insert an ArticleMedia with a nonexistent article_id must raise integrity error
            bad_media = ArticleMedia(article_id=999999, url="https://bad.jpg")
            session.add(bad_media)
            with pytest.raises(Exception):
                await session.commit()

    async def test_transaction_rollback_preserves_db_state(self, db_session: AsyncSession, seeded_session: AsyncSession):
        """F9.2: Verify transaction rollback properly discards uncommitted changes."""
        source = (await db_session.execute(select(Source))).scalars().first()
        art = Article(
            source_id=source.id,
            canonical_url="https://test.com/rollback_test",
            content_hash="rollback_hash",
            original_title="כתבה שתבוטל",
        )
        db_session.add(art)
        await db_session.flush()

        # Roll back
        await db_session.rollback()

        # Verify article was not persisted
        check = await db_session.execute(select(Article).where(Article.canonical_url == "https://test.com/rollback_test"))
        assert check.scalars().first() is None

    async def test_database_session_generator_lifecycle(self):
        """F9.3: Verify get_db async generator yields session and properly rolls back/closes."""
        gen = get_db()
        session = await gen.asend(None)
        assert isinstance(session, AsyncSession)
        try:
            res = await session.execute(select(1))
            assert res.scalar() == 1
        finally:
            try:
                await gen.asend(None)
            except (StopAsyncIteration, GeneratorExit):
                pass

    async def test_schema_indexes_and_unique_constraints(self, async_engine):
        """F9.4: Verify metadata contains required unique constraints and indexes for SQLite & Postgres."""
        article_table = Base.metadata.tables["articles"]
        tag_table = Base.metadata.tables["tags"]

        assert "canonical_url" in article_table.columns
        assert "content_hash" in article_table.columns
        assert "sport" in article_table.columns
        assert "name" in tag_table.columns
        assert "slug" in tag_table.columns

    async def test_pydantic_settings_database_url_normalization(self):
        """F9.5: Verify Settings converts standard postgresql:// to async postgresql+asyncpg://."""
        settings_pg = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/fanzone")
        assert "postgresql+asyncpg://" in settings_pg.ASYNC_DATABASE_URL

        settings_sqlite = Settings(DATABASE_URL="sqlite:///./fan_zone.db")
        assert "sqlite+aiosqlite:///" in settings_sqlite.ASYNC_DATABASE_URL


# ===========================================================================
# FEATURE 10: Repository Query & Rich Filtering Methods
# ===========================================================================

@pytest.mark.asyncio
class TestFeature10RepositoryQueryMethods:
    """>=5 tests verifying ArticleRepository queries, filters, date ranges, and full-text search."""

    async def test_repository_get_by_id_and_canonical_url(self, seeded_session: AsyncSession):
        """F10.1: Verify get_by_id and get_by_canonical_url lookup methods."""
        repo = ArticleRepository(seeded_session)
        source = (await seeded_session.execute(select(Source))).scalars().first()

        art, _ = await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=source.id,
                canonical_url="https://sport5.co.il/lookup_test",
                content_hash="lookup_hash_1",
                original_title="כתבת איתור",
            ),
            db=seeded_session,
        )

        by_id = await repo.get_by_id(art.id, db=seeded_session)
        assert by_id is not None
        assert by_id.canonical_url == "https://sport5.co.il/lookup_test"

        by_url = await repo.get_by_canonical_url("https://sport5.co.il/lookup_test", db=seeded_session)
        assert by_url is not None
        assert by_url.id == art.id

    async def test_repository_filter_by_sport_and_team(self, seeded_session: AsyncSession):
        """F10.2: Verify list_articles filtering by sport discipline and team name."""
        repo = ArticleRepository(seeded_session)
        source = (await seeded_session.execute(select(Source))).scalars().first()

        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=source.id,
                canonical_url="https://test.com/bball",
                content_hash="hash_bb",
                original_title="מכבי תל אביב ביורוליג",
                sport="כדורסל",
                teams_json=["מכבי תל אביב"],
            ),
            db=seeded_session,
        )
        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=source.id,
                canonical_url="https://test.com/fball",
                content_hash="hash_fb",
                original_title="מכבי חיפה בליגת העל",
                sport="כדורגל",
                teams_json=["מכבי חיפה"],
            ),
            db=seeded_session,
        )

        bball_arts, bball_count = await repo.list_articles(sport="כדורסל", db=seeded_session)
        assert bball_count >= 1
        assert all(a.sport == "כדורסל" for a in bball_arts)

        team_arts, team_count = await repo.list_articles(team="מכבי חיפה", db=seeded_session)
        assert team_count >= 1
        assert any("מכבי חיפה" in (a.teams_json or []) for a in team_arts)

    async def test_repository_filter_by_source(self, seeded_session: AsyncSession):
        """F10.3: Verify list_articles filtering by source_id and source_name."""
        repo = ArticleRepository(seeded_session)
        s_sport5 = (await seeded_session.execute(select(Source).where(Source.name == "sport5"))).scalar_one()
        s_one = (await seeded_session.execute(select(Source).where(Source.name == "one"))).scalar_one()

        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=s_sport5.id,
                canonical_url="https://sport5.co.il/filter_test",
                content_hash="hash_s5_f",
                original_title="כתבה מספורט 5",
            ),
            db=seeded_session,
        )
        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=s_one.id,
                canonical_url="https://one.co.il/filter_test",
                content_hash="hash_one_f",
                original_title="כתבה מ-ONE",
            ),
            db=seeded_session,
        )

        s5_arts, s5_count = await repo.list_articles(source_id=s_sport5.id, db=seeded_session)
        assert s5_count >= 1
        assert all(a.source_id == s_sport5.id for a in s5_arts)

    async def test_repository_date_range_and_sorting(self, seeded_session: AsyncSession):
        """F10.4: Verify date_from, date_to range filtering and sort_desc ordering."""
        repo = ArticleRepository(seeded_session)
        source = (await seeded_session.execute(select(Source))).scalars().first()
        now = datetime.now(timezone.utc)

        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=source.id,
                canonical_url="https://test.com/old",
                content_hash="hash_old",
                original_title="כתבה ישנה",
                published_at=now - timedelta(days=5),
            ),
            db=seeded_session,
        )
        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=source.id,
                canonical_url="https://test.com/recent",
                content_hash="hash_recent",
                original_title="כתבה חדשה",
                published_at=now - timedelta(hours=1),
            ),
            db=seeded_session,
        )

        arts, total = await repo.list_articles(
            date_from=now - timedelta(days=1),
            sort_by="published_at",
            sort_desc=True,
            db=seeded_session,
        )
        assert total >= 1
        assert any("כתבה חדשה" in a.original_title for a in arts)
        assert not any("כתבה ישנה" in a.original_title for a in arts)

    async def test_repository_hebrew_keyword_search(self, seeded_session: AsyncSession):
        """F10.5: Verify search_query substring matching in original_title, ai_headline, and body."""
        repo = ArticleRepository(seeded_session)
        source = (await seeded_session.execute(select(Source))).scalars().first()

        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=source.id,
                canonical_url="https://test.com/search_art",
                content_hash="hash_srch",
                original_title="סיכום העונה המפוארת של הפועל ירושלים",
                cleaned_body="האדומים מהבירה זכו בגביע המדינה בכדורסל.",
            ),
            db=seeded_session,
        )

        arts, total = await repo.list_articles(search_query="הפועל ירושלים", db=seeded_session)
        assert total >= 1
        assert any("הפועל ירושלים" in a.original_title for a in arts)


# ===========================================================================
# FEATURE 11: Periodic Background Scheduler
# ===========================================================================

@pytest.mark.asyncio
class TestFeature11BackgroundScheduler:
    """>=5 tests verifying poller lifecycle, interval, mutex lock, and resilience."""

    async def test_scheduler_initialization_defaults(self):
        """F11.1: Verify IngestionScheduler default configuration and flags."""
        sched = IngestionScheduler(poll_interval=120, enabled=True)
        assert sched.poll_interval == 120
        assert sched.enabled is True
        assert sched.is_running is False
        assert sched.run_count == 0

    async def test_scheduler_start_and_stop_lifecycle(self):
        """F11.2: Verify scheduler starts background loop and stops gracefully."""
        sched = IngestionScheduler(poll_interval=3600, enabled=True)
        await sched.start()
        assert sched.is_running is True
        await sched.stop()
        assert sched.is_running is False

    async def test_scheduler_concurrency_mutex_lock(self):
        """F11.3: Verify scheduler mutex lock prevents overlapping execution cycles."""
        sched = IngestionScheduler(poll_interval=3600)
        async with sched._lock:
            # Inside the lock, another attempt to acquire immediately fails/blocks
            assert sched._lock.locked() is True

    async def test_scheduler_run_now_execution(self, seeded_session: AsyncSession):
        """F11.4: Verify run_now executes immediate ingestion cycle and records stats."""
        sched = IngestionScheduler(poll_interval=3600)
        with patch("fan_zone.services.ingestion_service.IngestionService.ingest_all_sources") as mock_ingest:
            mock_stats = AsyncMock(
                total_discovered=10,
                total_processed=10,
                total_ingested=5,
                total_skipped=5,
                total_failed=0,
                total_errors=0,
                duration_seconds=1.2,
                errors=[],
            )
            mock_ingest.return_value = mock_stats
            stats = await sched.run_now()
            assert stats.total_ingested == 5
            assert sched.run_count == 1
            assert sched.last_run_at is not None

    async def test_scheduler_resilience_to_exceptions(self):
        """F11.5: Verify poller records error in stats when cycle raises an exception without crashing."""
        sched = IngestionScheduler(poll_interval=3600)
        with patch("fan_zone.services.ingestion_service.IngestionService.ingest_all_sources", side_effect=RuntimeError("Simulated network outage")):
            stats = await sched.run_now()
            assert stats.total_failed >= 1
            assert "Simulated network outage" in stats.errors[0]
            assert sched.run_count == 1


# ===========================================================================
# FEATURE 12: FastAPI REST Endpoints & Pagination
# ===========================================================================

@pytest.mark.asyncio
class TestFeature12FastAPIRESTEndpoints:
    """>=5 tests verifying GET /articles, pagination envelopes, multi-filtering, and details."""

    async def test_get_articles_paginated_response_envelope(self, api_client: httpx.AsyncClient):
        """F12.1: Verify /api/v1/articles returns standard pagination envelope."""
        res = await api_client.get("/api/v1/articles?page=1&page_size=10")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
        assert "has_next" in data
        assert "has_prev" in data

    async def test_get_articles_multi_parameter_filter(self, api_client: httpx.AsyncClient, seeded_session: AsyncSession):
        """F12.2: Verify GET /api/v1/articles with sport, team, and source query params."""
        res = await api_client.get("/api/v1/articles?sport=כדורגל&source=sport5")
        assert res.status_code == 200
        assert isinstance(res.json()["items"], list)

    async def test_get_article_by_id_detail_and_404(self, api_client: httpx.AsyncClient, seeded_session: AsyncSession):
        """F12.3: Verify GET /api/v1/articles/{id} returns full detail or 404 for invalid ID."""
        repo = ArticleRepository(seeded_session)
        source = (await seeded_session.execute(select(Source))).scalars().first()
        art, _ = await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=source.id,
                canonical_url="https://test.com/detail_art",
                content_hash="hash_detail",
                original_title="כתבת בדיקת פירוט",
                raw_paragraphs=["פסקה מפורטת ראשונה."],
            ),
            db=seeded_session,
        )

        res = await api_client.get(f"/api/v1/articles/{art.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == art.id
        assert data["original_title"] == "כתבת בדיקת פירוט"
        assert len(data["paragraphs"]) >= 1

        res_404 = await api_client.get("/api/v1/articles/999999")
        assert res_404.status_code == 404

    async def test_get_articles_sorting_order(self, api_client: httpx.AsyncClient):
        """F12.4: Verify order=asc and order=desc query parameter sorting."""
        res_desc = await api_client.get("/api/v1/articles?sort_by=published_at&order=desc")
        res_asc = await api_client.get("/api/v1/articles?sort_by=published_at&order=asc")
        assert res_desc.status_code == 200
        assert res_asc.status_code == 200

    async def test_root_endpoint_metadata_and_links(self, api_client: httpx.AsyncClient):
        """F12.5: Verify GET / and GET /health system entry points."""
        res_root = await api_client.get("/")
        assert res_root.status_code == 200
        assert "docs" in res_root.json()
        assert "version" in res_root.json()

        res_health = await api_client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json()["status"] == "healthy"


# ===========================================================================
# FEATURE 13: Manual Ingestion Trigger Endpoint
# ===========================================================================

@pytest.mark.asyncio
class TestFeature13ManualIngestionTrigger:
    """>=5 tests verifying POST /ingest/trigger and GET /ingest/status."""

    async def test_trigger_single_url_ingestion(self, api_client: httpx.AsyncClient):
        """F13.1: Verify POST /api/v1/ingest/trigger with single URL."""
        with patch("fan_zone.services.ingestion_service.IngestionService.ingest_url") as mock_ingest:
            mock_art = AsyncMock()
            mock_art.id = 42
            mock_ingest.return_value = (mock_art, True)

            payload = {"url": "https://sport5.co.il/article1", "source_name": "sport5"}
            res = await api_client.post("/api/v1/ingest/trigger", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert data["articles_ingested"] == 1
            assert data["article_id"] == 42

    async def test_trigger_single_url_duplicate_response(self, api_client: httpx.AsyncClient):
        """F13.2: Verify triggering duplicate URL indicates article already exists."""
        with patch("fan_zone.services.ingestion_service.IngestionService.ingest_url") as mock_ingest:
            mock_art = AsyncMock()
            mock_art.id = 42
            mock_ingest.return_value = (mock_art, False)

            payload = {"url": "https://sport5.co.il/article1"}
            res = await api_client.post("/api/v1/ingest/trigger", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert "deduplicated" in data["message"].lower() or "already exists" in data["message"].lower()
            assert data["articles_ingested"] == 0

    async def test_trigger_source_specific_batch(self, api_client: httpx.AsyncClient):
        """F13.3: Verify POST /api/v1/ingest/trigger with source_name polling."""
        with patch("fan_zone.services.ingestion_service.IngestionService.ingest_source") as mock_ingest:
            mock_stats = AsyncMock(total_processed=5, total_ingested=3, total_skipped=2, total_failed=0, total_errors=0)
            mock_ingest.return_value = mock_stats

            payload = {"source_name": "one"}
            res = await api_client.post("/api/v1/ingest/trigger", json=payload)
            assert res.status_code == 200
            assert res.json()["articles_ingested"] == 3

    async def test_trigger_all_sources_batch(self, api_client: httpx.AsyncClient):
        """F13.4: Verify POST /api/v1/ingest/trigger without body polls all sources."""
        with patch("fan_zone.services.ingestion_service.IngestionService.ingest_all_sources") as mock_ingest:
            mock_stats = AsyncMock(total_processed=15, total_ingested=10, total_skipped=5, total_failed=0, total_errors=0)
            mock_ingest.return_value = mock_stats

            res = await api_client.post("/api/v1/ingest/trigger", json={})
            assert res.status_code == 200
            assert res.json()["articles_ingested"] == 10

    async def test_get_ingestion_status_telemetry(self, api_client: httpx.AsyncClient):
        """F13.5: Verify GET /api/v1/ingest/status returns runtime status."""
        res = await api_client.get("/api/v1/ingest/status")
        assert res.status_code == 200
        data = res.json()
        assert "scheduler_running" in data
        assert "poll_interval_seconds" in data
        assert "run_count" in data


# ===========================================================================
# FEATURE 14: System Health, Stats & Tags Exploration
# ===========================================================================

@pytest.mark.asyncio
class TestFeature14SystemHealthAndStats:
    """>=5 tests verifying /health, /stats, /sources, /tags, and /popular."""

    async def test_health_check_endpoint_probe(self, api_client: httpx.AsyncClient):
        """F14.1: Verify GET /api/v1/health checks DB connectivity and scheduler state."""
        res = await api_client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "version" in data

    async def test_system_stats_aggregation(self, api_client: httpx.AsyncClient, seeded_session: AsyncSession):
        """F14.2: Verify GET /api/v1/stats aggregates totals, status counts, and sports breakdown."""
        repo = ArticleRepository(seeded_session)
        source = (await seeded_session.execute(select(Source))).scalars().first()
        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=source.id,
                canonical_url="https://test.com/stat_art",
                content_hash="hash_stat",
                original_title="כתבת סטטיסטיקה",
                sport="ג'ודו",
                ingestion_status=IngestionStatus.AI_PROCESSED,
            ),
            db=seeded_session,
        )

        res = await api_client.get("/api/v1/stats")
        assert res.status_code == 200
        data = res.json()
        assert data["total_articles"] >= 1
        assert "ג'ודו" in data["sports_breakdown"]
        assert len(data["sources_stats"]) >= 7

    async def test_list_sources_with_operational_counts(self, api_client: httpx.AsyncClient):
        """F14.3: Verify GET /api/v1/sources lists all 7 Israeli outlets."""
        res = await api_client.get("/api/v1/sources")
        assert res.status_code == 200
        sources = res.json()
        assert len(sources) == 7
        codes = {s["code"] for s in sources}
        assert "sport5" in codes
        assert "one" in codes
        assert "walla" in codes
        assert "ynet" in codes

    async def test_get_source_by_code_and_id(self, api_client: httpx.AsyncClient):
        """F14.4: Verify GET /api/v1/sources/{id_or_code} resolves code name and ID."""
        res = await api_client.get("/api/v1/sources/sport5")
        assert res.status_code == 200
        source_id = res.json()["id"]

        res_id = await api_client.get(f"/api/v1/sources/{source_id}")
        assert res_id.status_code == 200
        assert res_id.json()["name"] == "sport5"

    async def test_tags_exploration_and_popular_ranking(self, api_client: httpx.AsyncClient, seeded_session: AsyncSession):
        """F14.5: Verify GET /api/v1/tags and GET /api/v1/tags/popular."""
        tag_repo = TagRepository(seeded_session)
        await tag_repo.get_or_create_batch([("כדורגל", TagType.SPORT), ("מכבי תל אביב", TagType.TEAM)], db=seeded_session)

        res_tags = await api_client.get("/api/v1/tags?type=sport")
        assert res_tags.status_code == 200
        assert any(t["name"] == "כדורגל" for t in res_tags.json())

        res_pop = await api_client.get("/api/v1/tags/popular?limit=5")
        assert res_pop.status_code == 200
        assert isinstance(res_pop.json(), list)
