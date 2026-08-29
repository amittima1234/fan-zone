"""Unit tests for portal scrapers, text sanitization, and truncation (Milestone 2)."""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from schemas.feed import RawArticlePayload
from services.scrapers import (
    BaseScraper,
    ONEScraper,
    SCRAPER_REGISTRY,
    Sport5Scraper,
    YnetScraper,
    get_all_scrapers,
    get_scraper,
    register_scraper,
    sanitize_article_text,
    truncate_article_text,
)
from tests.fixtures.sample_html import (
    MALICIOUS_XSS_HTML_SAMPLES,
    ONE_ARTICLE_HTML,
    ONE_DIRTY_HTML,
    ONE_LONG_ARTICLE_HTML,
    SPORT5_ARTICLE_HTML,
    SPORT5_DIRTY_HTML,
    SPORT5_LONG_ARTICLE_HTML,
    YNET_ARTICLE_HTML,
    YNET_DIRTY_HTML,
    YNET_LONG_ARTICLE_HTML,
)
from tests.fixtures.sample_rss import (
    ONE_RSS_XML,
    SPORT5_RSS_XML,
    YNET_RSS_XML,
)


class TestSanitizeArticleText:
    """Unit tests for HTML sanitization and text normalization."""

    def test_empty_and_none_text(self):
        assert sanitize_article_text("") == ""
        assert sanitize_article_text(None) == ""

    def test_strip_html_tags(self):
        html_input = "<div><p>שלום <b>עולם</b>!</p></div>"
        cleaned = sanitize_article_text(html_input)
        assert cleaned == "שלום עולם!"
        assert "<" not in cleaned and ">" not in cleaned

    def test_strip_script_and_style_tags(self):
        html_input = """
        <script type="text/javascript">
            var secret = "stolen_data";
            console.log(secret);
        </script>
        <style>body { color: red; }</style>
        <h1>כותרת ראשית</h1>
        <p>תוכן הכתבה.</p>
        <iframe src="http://evil.com"></iframe>
        """
        cleaned = sanitize_article_text(html_input)
        assert "secret" not in cleaned
        assert "stolen_data" not in cleaned
        assert "color: red" not in cleaned
        assert "evil.com" not in cleaned
        assert "כותרת ראשית" in cleaned
        assert "תוכן הכתבה." in cleaned

    def test_unescape_html_entities(self):
        html_input = "מכבי ת&quot;א גברה על בית&quot;ר &amp; הפועל"
        cleaned = sanitize_article_text(html_input)
        assert cleaned == 'מכבי ת"א גברה על בית"ר & הפועל'

    def test_whitespace_normalization(self):
        raw = "   מכבי    תל   אביב \n\n\n\n  ניצחה   ביורוליג.   "
        cleaned = sanitize_article_text(raw)
        assert cleaned == "מכבי תל אביב\n\nניצחה ביורוליג."

    @pytest.mark.parametrize("dirty_html,expected_title,expected_body", MALICIOUS_XSS_HTML_SAMPLES)
    def test_malicious_xss_vectors(self, dirty_html, expected_title, expected_body):
        cleaned = sanitize_article_text(dirty_html)
        assert "alert(" not in cleaned
        assert "<script>" not in cleaned
        assert "<iframe>" not in cleaned
        assert "<style>" not in cleaned
        assert "<svg" not in cleaned
        assert "<img" not in cleaned
        assert "javascript:" not in cleaned


class TestTruncateArticleText:
    """Unit tests for text truncation boundaries."""

    def test_empty_and_short_text(self):
        assert truncate_article_text("") == ""
        assert truncate_article_text(None) == ""
        assert truncate_article_text("Short text") == "Short text"

    def test_strict_3500_char_limit(self):
        long_text = "א" * 5000
        truncated = truncate_article_text(long_text, max_chars=3500)
        assert len(truncated) == 3500
        assert len(truncated) <= 3500

    def test_exact_limit_boundary(self):
        exact_text = "ב" * 3500
        truncated = truncate_article_text(exact_text, max_chars=3500)
        assert len(truncated) == 3500
        assert truncated == exact_text

    def test_custom_max_chars(self):
        text = "Hello Sports Fans!"
        assert truncate_article_text(text, max_chars=5) == "Hello"


class TestSport5Scraper:
    """Unit tests for Sport5 portal scraper."""

    def test_sport5_standard_article_extraction(self):
        scraper = Sport5Scraper()
        payload = scraper.extract_article(SPORT5_ARTICLE_HTML)

        assert payload is not None
        assert isinstance(payload, RawArticlePayload)
        assert payload.publisher == "sport5"
        assert "מכבי תל אביב" in payload.title
        assert "ריאל מדריד" in payload.title
        assert "עודד קטש" in payload.raw_body or "בולדווין" in payload.raw_body
        assert payload.author == "עמרי פולק"
        assert len(payload.raw_body) <= 3500

    def test_sport5_long_article_truncation(self):
        scraper = Sport5Scraper()
        payload = scraper.extract_article(SPORT5_LONG_ARTICLE_HTML)

        assert payload is not None
        assert len(payload.raw_body) <= 3500
        assert "<script>" not in payload.raw_body
        assert "Tracking user" not in payload.raw_body
        assert "<iframe>" not in payload.raw_body

    def test_sport5_dirty_html_sanitization(self):
        scraper = Sport5Scraper()
        payload = scraper.extract_article(SPORT5_DIRTY_HTML)

        assert payload is not None
        assert "malicious_code" not in payload.raw_body
        assert "tracking" not in payload.raw_body.lower()
        assert "<style>" not in payload.raw_body
        assert "ברק בכר" in payload.title or "מכבי חיפה" in payload.title
        assert "עלי מוחמד" in payload.raw_body

    @pytest.mark.asyncio
    async def test_sport5_fetch_rss_mocked(self):
        scraper = Sport5Scraper()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SPORT5_RSS_XML

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        entries = await scraper.fetch_rss(client=mock_client)
        assert len(entries) == 3
        assert entries[0]["title"] == "ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג"
        assert "sport5.co.il" in entries[0]["link"]
        assert entries[0]["author"] == "עמרי פולק"


class TestYnetScraper:
    """Unit tests for Ynet sports portal scraper."""

    def test_ynet_standard_article_extraction(self):
        scraper = YnetScraper()
        payload = scraper.extract_article(YNET_ARTICLE_HTML)

        assert payload is not None
        assert isinstance(payload, RawArticlePayload)
        assert payload.publisher == "ynet"
        assert "בית\"ר ירושלים" in payload.title or 'בית"ר' in payload.title
        assert "ברק אברמוב" in payload.raw_body or "אימון" in payload.raw_body
        assert len(payload.raw_body) <= 3500

    def test_ynet_long_article_truncation(self):
        scraper = YnetScraper()
        payload = scraper.extract_article(YNET_LONG_ARTICLE_HTML)

        assert payload is not None
        assert len(payload.raw_body) <= 3500
        assert "תחקיר" in payload.title

    def test_ynet_dirty_html_sanitization(self):
        scraper = YnetScraper()
        payload = scraper.extract_article(YNET_DIRTY_HTML)

        assert payload is not None
        assert "dataLayer" not in payload.raw_body
        assert "javascript:alert" not in payload.raw_body
        assert "taboola" not in payload.raw_body.lower()
        assert "הפועל תל אביב" in payload.title or "הפועל תל אביב" in payload.raw_body

    @pytest.mark.asyncio
    async def test_ynet_fetch_rss_mocked(self):
        scraper = YnetScraper()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = YNET_RSS_XML

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        entries = await scraper.fetch_rss(client=mock_client)
        assert len(entries) == 2
        assert 'בית"ר ירושלים' in entries[0]["title"]
        assert "ynet.co.il" in entries[0]["link"]


class TestONEScraper:
    """Unit tests for ONE sports portal scraper."""

    def test_one_standard_article_extraction(self):
        scraper = ONEScraper()
        payload = scraper.extract_article(ONE_ARTICLE_HTML)

        assert payload is not None
        assert isinstance(payload, RawArticlePayload)
        assert payload.publisher == "one"
        assert "הפועל באר שבע" in payload.title
        assert "אלונה ברקת" in payload.raw_body or "קשר" in payload.raw_body
        assert len(payload.raw_body) <= 3500

    def test_one_long_article_truncation(self):
        scraper = ONEScraper()
        payload = scraper.extract_article(ONE_LONG_ARTICLE_HTML)

        assert payload is not None
        assert len(payload.raw_body) <= 3500
        assert "הפועל באר שבע" in payload.title

    def test_one_dirty_html_sanitization(self):
        scraper = ONEScraper()
        payload = scraper.extract_article(ONE_DIRTY_HTML)

        assert payload is not None
        assert "document.write" not in payload.raw_body
        assert "sendAnalytics" not in payload.raw_body
        assert "מנור סולומון" in payload.title or "מנור סולומון" in payload.raw_body

    @pytest.mark.asyncio
    async def test_one_fetch_rss_mocked(self):
        scraper = ONEScraper()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ONE_RSS_XML

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        entries = await scraper.fetch_rss(client=mock_client)
        assert len(entries) == 2
        assert "הפועל באר שבע" in entries[0]["title"]
        assert "one.co.il" in entries[0]["link"]


class TestScraperRegistry:
    """Unit tests for scraper registry and factory dispatch."""

    def test_get_registered_scrapers(self):
        s_sport5 = get_scraper("sport5")
        assert isinstance(s_sport5, Sport5Scraper)
        assert s_sport5.publisher_id == "sport5"

        s_ynet = get_scraper("ynet")
        assert isinstance(s_ynet, YnetScraper)
        assert s_ynet.publisher_id == "ynet"

        s_one = get_scraper("one")
        assert isinstance(s_one, ONEScraper)
        assert s_one.publisher_id == "one"

    def test_case_insensitivity_in_registry(self):
        s1 = get_scraper("SPORT5")
        s2 = get_scraper("  yNeT  ")
        assert isinstance(s1, Sport5Scraper)
        assert isinstance(s2, YnetScraper)

    def test_unknown_publisher_raises_error(self):
        with pytest.raises(ValueError, match="Unknown publisher 'nonexistent'"):
            get_scraper("nonexistent")

    def test_get_all_scrapers(self):
        scrapers = get_all_scrapers()
        assert len(scrapers) == 3
        pub_ids = {s.publisher_id for s in scrapers}
        assert pub_ids == {"sport5", "ynet", "one"}

    def test_register_custom_scraper(self):
        class MockCustomScraper(BaseScraper):
            publisher_id = "custom"
            def extract_article(self, html, rss_entry=None):
                return None

        register_scraper("custom", MockCustomScraper)
        custom_inst = get_scraper("custom")
        assert isinstance(custom_inst, MockCustomScraper)
        assert "custom" in SCRAPER_REGISTRY


class TestScraperScrapeOrchestration:
    """Unit tests for full async scraper scrape flow."""

    @pytest.mark.asyncio
    async def test_scrape_orchestration(self):
        scraper = Sport5Scraper()

        mock_rss_response = MagicMock()
        mock_rss_response.status_code = 200
        mock_rss_response.text = SPORT5_RSS_XML

        mock_article_response = MagicMock()
        mock_article_response.status_code = 200
        mock_article_response.text = SPORT5_ARTICLE_HTML

        async def mock_get(url, **kwargs):
            if "rss.aspx" in url:
                return mock_rss_response
            return mock_article_response

        with patch("httpx.AsyncClient.get", new=mock_get):
            articles = await scraper.scrape(limit=2)
            assert len(articles) <= 2
            assert all(isinstance(a, RawArticlePayload) for a in articles)
            assert all(a.publisher == "sport5" for a in articles)
            assert all(len(a.raw_body) <= 3500 for a in articles)
