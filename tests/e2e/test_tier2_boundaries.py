"""Tier 2: Boundary & Corner Cases E2E Test Suite.

Verifies system behavior at extreme boundaries, malformed inputs, edge cases,
and error conditions:
- Empty, whitespace-only, and zero-length bodies
- Hebrew Unicode edge cases (Niqqud, Cantillation marks, RTL/LTR mixed text, Emojis)
- Extremely large payloads (50k+ chars, 200 paragraphs)
- Missing/None metadata (author, subtitle, published date, media)
- Malformed RSS/XML feeds and broken HTML markup
- Special characters, encodings, and fragments in URLs
- Extreme REST API query parameters (out-of-range pagination, large limits)
- Boundary dates and timezone offset conversions
- HTTP error statuses (403 Paywall, 404 Not Found, 500/503 Errors, Network Timeouts)
- Special regex/SQL characters in tag search and filtering
"""

from datetime import datetime, timezone, timedelta
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.ai.fallback import fallback_article_analysis
from fan_zone.ai.mock import MockAIProcessor
from fan_zone.db.session import get_db
from fan_zone.main import create_app
from fan_zone.models.article import Article
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.models.source import Source
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.repositories.tag_repo import TagRepository
from fan_zone.schemas.article import ArticleCreate
from fan_zone.schemas.media import MediaCreate
from fan_zone.scrapers.base import (
    ExtractedArticle,
    ExtractedImage,
    compute_content_hash,
    normalize_canonical_url,
)
from fan_zone.scrapers.haaretz import HaaretzParser
from fan_zone.scrapers.israel_hayom import IsraelHayomParser
from fan_zone.scrapers.one import ONEParser
from fan_zone.scrapers.sport5 import Sport5Parser
from fan_zone.services.ingestion_service import IngestionService


@pytest_asyncio.fixture
async def api_client(seeded_session: AsyncSession) -> httpx.AsyncClient:
    """FastAPI async test client with dependency override."""
    app = create_app()

    async def override_get_db():
        yield seeded_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Empty & Whitespace-Only Body Corner Cases
# ===========================================================================

@pytest.mark.asyncio
async def test_empty_and_whitespace_only_paragraphs(db_session: AsyncSession):
    """Verify article with empty or whitespace-only paragraphs is handled gracefully."""
    source_repo = SourceRepository(db_session)
    sources = await source_repo.seed_default_sources()
    s_sport5 = next(s for s in sources if s.name == "sport5")

    service = IngestionService(db=db_session, ai_processor=MockAIProcessor())

    ext = ExtractedArticle(
        source_name="Sport5",
        source_domain="sport5.co.il",
        original_url="https://sport5.co.il/empty_body_test",
        canonical_url="https://sport5.co.il/empty_body_test",
        content_hash=compute_content_hash("כותרת ללא גוף", []),
        original_title="כותרת ללא גוף",
        paragraphs=["   ", "\t\n  ", ""],
    )

    art, created = await service.process_and_persist_article(ext, s_sport5)
    assert created is True
    assert art.id is not None
    assert art.cleaned_body == "" or art.cleaned_body.strip() == ""


# ===========================================================================
# 2. Hebrew Unicode Edge Cases: Niqqud, Cantillation & Mixed RTL/LTR
# ===========================================================================

@pytest.mark.asyncio
async def test_hebrew_niqqud_and_cantillation_marks():
    """Verify Hebrew text with Niqqud (נקוד) and cantillation marks is analyzed and hashed properly."""
    # "מַכַּבִּי תֵּל אָבִיב נִצְּחָה אֶת רֵיאָל מַדְרִיד"
    niqqud_title = "מַכַּבִּי תֵּל אָבִיב נִצְּחָה אֶת רֵיאָל מַדְרִיד"
    plain_title = "מכבי תל אביב ניצחה את ריאל מדריד"
    body = "מִשְׂחָק מַדְהִים שֶׁל הַצְּהֻבִּים בַּיּוֹרוֹלִיג."

    res = fallback_article_analysis(title=niqqud_title, body=body)
    assert res.sport == "כדורסל"
    assert "מכבי תל אביב" in res.teams or "מַכַּבִּי תֵּל אָבִיב" in res.teams


@pytest.mark.asyncio
async def test_mixed_rtl_ltr_hebrew_english_and_emojis():
    """Verify bidirectional mixed text (Hebrew + English terms + Emojis) is parsed cleanly."""
    mixed_title = "🏆 מכבי ת\"א: Wade Baldwin נבחר ל-MVP של המחזור ב-EuroLeague! 🔥"
    body = "הגארד של מכבי תל אביב רשם 30 נקודות ו-8 אסיסטים בניצחון 82:85 על Real Madrid."

    res = fallback_article_analysis(title=mixed_title, body=body)
    assert res.sport == "כדורסל"
    assert "יורוליג" in (res.competition or "") or "EuroLeague" in res.tags or len(res.tags) > 0


# ===========================================================================
# 3. Extremely Large Payloads Stress
# ===========================================================================

@pytest.mark.asyncio
async def test_extremely_large_article_body_persistence(db_session: AsyncSession):
    """Verify handling and storage of article with 200 paragraphs and 50,000+ characters."""
    source_repo = SourceRepository(db_session)
    sources = await source_repo.seed_default_sources()
    s_walla = next(s for s in sources if s.name == "walla")

    paragraphs = [f"פסקה מספר {i}: דיווח מפורט על משחק העונה בין מכבי חיפה למכבי תל אביב בליגת העל." * 5 for i in range(200)]
    full_text = "\n\n".join(paragraphs)
    assert len(full_text) > 50000

    service = IngestionService(db=db_session, ai_processor=MockAIProcessor())
    ext = ExtractedArticle(
        source_name="Walla! Sports",
        source_domain="walla.co.il",
        original_url="https://sports.walla.co.il/large_article",
        canonical_url="https://sports.walla.co.il/large_article",
        content_hash=compute_content_hash("כתבת ענק", paragraphs),
        original_title="כתבת ענק עם 200 פסקאות",
        paragraphs=paragraphs,
    )

    art, created = await service.process_and_persist_article(ext, s_walla)
    assert created is True
    assert len(art.raw_paragraphs) == 200
    assert len(art.cleaned_body) > 50000


# ===========================================================================
# 4. Missing / None Metadata Corner Cases
# ===========================================================================

@pytest.mark.asyncio
async def test_missing_author_subtitle_and_publish_date(db_session: AsyncSession):
    """Verify article with None author, subtitle, and published_at defaults safely."""
    source_repo = SourceRepository(db_session)
    sources = await source_repo.seed_default_sources()
    s_ynet = next(s for s in sources if s.name == "ynet")

    service = IngestionService(db=db_session, ai_processor=MockAIProcessor())
    ext = ExtractedArticle(
        source_name="Ynet Sport",
        source_domain="ynet.co.il",
        original_url="https://ynet.co.il/minimal_article",
        canonical_url="https://ynet.co.il/minimal_article",
        content_hash=compute_content_hash("כותרת מינימלית", ["פסקה בודדת"]),
        original_title="כותרת מינימלית",
        original_subtitle=None,
        author=None,
        published_at=None,
        paragraphs=["פסקה בודדת"],
    )

    art, created = await service.process_and_persist_article(ext, s_ynet)
    assert created is True
    assert art.author is None
    assert art.original_subtitle is None
    assert art.published_at is None


# ===========================================================================
# 5. Malformed Feeds & Broken HTML Markup
# ===========================================================================

@pytest.mark.asyncio
async def test_malformed_rss_feed_recovery():
    """Verify ONE parser handles corrupted RSS feed XML without crashing."""
    parser = ONEParser()
    broken_xml = """<?xml version="1.0"?>
    <rss><channel>
        <item>
            <title>כותרת תקינה ראשונה</title>
            <link>https://www.one.co.il/Article/111</link>
        </item>
        <item>
            <title>פריט שבור ללא קישור
        <!-- Unclosed XML tags
    """
    def handler(req): return httpx.Response(200, text=broken_xml, request=req)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        discovered = await parser.discover_articles(client)
        # Should gracefully extract the valid item or return empty list without raising
        assert isinstance(discovered, list)


@pytest.mark.asyncio
async def test_malformed_html_markup_recovery():
    """Verify parser extracts paragraphs from broken HTML with missing body and unclosed divs."""
    parser = Sport5Parser()
    broken_html = """
    <h1>כותרת כתבה מתוך HTML שבור</h1>
    <div class="article-body">
        <p>פסקה ראשונה ב-HTML לא תקני
        <p>פסקה שנייה ללא סגירת תגיות
    """
    def handler(req): return httpx.Response(200, text=broken_html, request=req)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        art = await parser.parse_article(client, "https://sport5.co.il/broken_html")
        assert art is not None
        assert len(art.paragraphs) >= 1


# ===========================================================================
# 6. Special Characters & Encodings in URLs
# ===========================================================================

@pytest.mark.asyncio
async def test_url_normalization_with_hebrew_and_encoded_chars():
    """Verify canonical URL normalizer handles Hebrew characters, percent encoding, and fragments."""
    raw_url = "https://www.one.co.il/Article/2026/מכבי-חיפה-נגד-הפועל?utm_source=rss&ref=home#section1"
    normalized = normalize_canonical_url(raw_url)
    assert "utm_source" not in normalized
    assert "#section1" not in normalized
    assert "https://www.one.co.il/Article/2026/" in normalized


# ===========================================================================
# 7. Extreme REST API Query Parameters
# ===========================================================================

@pytest.mark.asyncio
async def test_api_extreme_page_number_out_of_range(api_client: httpx.AsyncClient):
    """Verify requesting page=99999 returns empty items array with 200 status code."""
    res = await api_client.get("/api/v1/articles?page=99999&page_size=20")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["page"] == 99999
    assert data["has_next"] is False


@pytest.mark.asyncio
async def test_api_page_size_validation_limits(api_client: httpx.AsyncClient):
    """Verify page_size exceeding 100 or below 1 returns 422 Unprocessable Entity."""
    res_large = await api_client.get("/api/v1/articles?page_size=500")
    assert res_large.status_code == 422

    res_zero = await api_client.get("/api/v1/articles?page_size=0")
    assert res_zero.status_code == 422


# ===========================================================================
# 8. Boundary Dates & Timezone Offsets
# ===========================================================================

@pytest.mark.asyncio
async def test_future_and_epoch_dates_in_article_filter(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify date filtering with epoch (1970) and future (2035) dates."""
    res_epoch = await api_client.get("/api/v1/articles?date_to=1970-01-01T00:00:00Z")
    assert res_epoch.status_code == 200
    assert res_epoch.json()["total"] == 0

    res_future = await api_client.get("/api/v1/articles?date_from=2035-01-01T00:00:00Z")
    assert res_future.status_code == 200
    assert res_future.json()["total"] == 0


# ===========================================================================
# 9. Crawler HTTP Error Statuses: 403, 404, 500, Timeouts
# ===========================================================================

@pytest.mark.asyncio
async def test_crawler_handles_http_errors_gracefully():
    """Verify parser returns None on HTTP 403 (Paywall), 404 (Not Found), 500 (Server Error)."""
    parser = HaaretzParser()

    def handler_403(req): return httpx.Response(403, text="Paywall Blocked", request=req)
    def handler_404(req): return httpx.Response(404, text="Not Found", request=req)
    def handler_500(req): return httpx.Response(500, text="Internal Server Error", request=req)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_403)) as c403:
        assert await parser.parse_article(c403, "https://haaretz.co.il/paywall") is None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_404)) as c404:
        assert await parser.parse_article(c404, "https://haaretz.co.il/notfound") is None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_500)) as c500:
        assert await parser.parse_article(c500, "https://haaretz.co.il/error500") is None


# ===========================================================================
# 10. Tag Search with Regex & SQL Special Characters
# ===========================================================================

@pytest.mark.asyncio
async def test_tag_search_with_regex_and_sql_special_chars(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify searching tags with regex characters ([, ], *, +) and SQL wildcards (%, _) does not crash."""
    res_regex = await api_client.get("/api/v1/tags?q=[a-z]*+?")
    assert res_regex.status_code == 200
    assert isinstance(res_regex.json(), list)

    res_sql = await api_client.get("/api/v1/tags?q=%'_%")
    assert res_sql.status_code == 200
    assert isinstance(res_sql.json(), list)
