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
    WallaScraper,
    YnetScraper,
    get_all_scrapers,
    get_scraper,
    is_non_article_content,
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
    SPORT5_NEWSROOM_HTML,
    SPORT5_SECTION_HTML,
    WALLA_ARTICLE_HTML,
    YNET_ARTICLE_HTML,
    YNET_DIRTY_HTML,
    YNET_LONG_ARTICLE_HTML,
)
from tests.fixtures.sample_rss import (
    ONE_RSS_XML,
    SPORT5_RSS_XML,
    WALLA_RSS_XML,
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


class TestNonArticleContentFiltering:
    """Unit tests for filtering out static, legal, contact, and accessibility pages."""

    def test_detects_terms_and_privacy_titles(self):
        assert is_non_article_content(title="תנאי השימוש ומדיניות הפרטיות אתר ספורט 5") is True
        assert is_non_article_content(title="תנאי שימוש באתר") is True
        assert is_non_article_content(title="מדיניות פרטיות") is True
        assert is_non_article_content(title="Privacy Policy") is True
        assert is_non_article_content(title="Terms of Use") is True

    def test_detects_accessibility_and_contact_titles(self):
        assert is_non_article_content(title="הצהרת נגישות") is True
        assert is_non_article_content(title="הסדרי נגישות באתר") is True
        assert is_non_article_content(title="צור קשר עם ערוץ הספורט") is True
        assert is_non_article_content(title="שירות לקוחות ופניות הציבור") is True
        assert is_non_article_content(title="כתבו לנו") is True

    def test_detects_legal_folders_and_urls(self):
        assert is_non_article_content(url="https://sport5.co.il/articles.aspx?FolderID=413&docID=50633") is True
        assert is_non_article_content(url="https://www.sport5.co.il/articles.aspx?FolderID=11202&docID=425839") is True
        assert is_non_article_content(url="https://www.sport5.co.il/articles.aspx?FolderID=11202&docID=425624") is True
        assert is_non_article_content(url="https://www.ynet.co.il/terms") is True

    def test_valid_sports_articles_are_not_filtered(self):
        assert is_non_article_content(title="ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג") is False
        assert is_non_article_content(title="מנור סולומון כבש שער ניצחון בפרמייר ליג") is False
        assert is_non_article_content(url="https://www.sport5.co.il/articles.aspx?FolderID=4467&docID=450101") is False


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

    def test_sport5_discards_static_legal_pages(self):
        scraper = Sport5Scraper()

        # 1. Terms of use
        p1 = scraper.extract_article(
            html="<html><body><h1>תנאי השימוש ומדיניות הפרטיות אתר ספורט 5</h1><p>תקנון האתר...</p></body></html>",
            rss_entry={"link": "https://sport5.co.il/articles.aspx?FolderID=413&docID=50633"},
        )
        assert p1 is None

        # 2. Accessibility declaration
        p2 = scraper.extract_article(
            html="<html><body><h1>הצהרת נגישות</h1><p>אנו פועלים להנגשת האתר...</p></body></html>",
            rss_entry={"link": "https://www.sport5.co.il/articles.aspx?FolderID=11202&docID=425839"},
        )
        assert p2 is None

        # 3. Contact us
        p3 = scraper.extract_article(
            html="<html><body><h1>צור קשר עם ערוץ הספורט</h1><p>כתובת וטלפון...</p></body></html>",
            rss_entry={"link": "https://www.sport5.co.il/articles.aspx?FolderID=11202&docID=425624"},
        )
        assert p3 is None

    def test_sport5_sections_configuration(self):
        scraper = Sport5Scraper()
        assert len(scraper.SECTIONS) == 6
        section_urls = [s["url"] for s in scraper.SECTIONS]
        assert "https://www.sport5.co.il/NewsRoom" in section_urls
        assert "https://www.sport5.co.il/world.aspx?FolderID=4453" in section_urls
        assert "https://www.sport5.co.il/world.aspx?FolderID=4439" in section_urls
        assert "https://www.sport5.co.il/world.aspx?FolderID=4467" in section_urls
        assert "https://nba.sport5.co.il/NBA.aspx?FolderId=402" in section_urls
        assert "https://www.sport5.co.il/world.aspx?FolderID=4498" in section_urls

        categories = {s["category"] for s in scraper.SECTIONS}
        assert "מבזקים" in categories
        assert "כדורגל עולמי" in categories
        assert "כדורגל ישראלי" in categories
        assert "כדורסל" in categories
        assert "NBA" in categories
        assert "ענפים נוספים" in categories

    def test_sport5_extract_links_from_newsroom_html(self):
        scraper = Sport5Scraper()
        seen = set()
        entries = scraper._extract_links_from_section_html(
            SPORT5_NEWSROOM_HTML,
            {"url": "https://www.sport5.co.il/NewsRoom", "category": "מבזקים"},
            seen,
        )
        assert len(entries) == 2
        assert "מנצ'סטר סיטי" in entries[0]["title"]
        assert entries[0]["category"] == "מבזקים"
        assert "5001" in entries[0]["link"]
        assert "מכבי חיפה" in entries[1]["title"]
        assert entries[1]["category"] == "מבזקים"
        assert "5002" in entries[1]["link"]

    def test_sport5_extract_links_from_category_section_html(self):
        scraper = Sport5Scraper()
        seen = set()
        entries = scraper._extract_links_from_section_html(
            SPORT5_SECTION_HTML,
            {"url": "https://www.sport5.co.il/world.aspx?FolderID=4467", "category": "כדורסל"},
            seen,
        )
        assert len(entries) >= 2
        titles = [e["title"] for e in entries]
        assert any("מכבי תל אביב" in t for t in titles)
        assert any("הפועל ירושלים" in t for t in titles)
        assert all(e["category"] == "כדורסל" for e in entries)

    @pytest.mark.asyncio
    async def test_sport5_fetch_sections_mocked(self):
        scraper = Sport5Scraper()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SPORT5_SECTION_HTML

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        entries = await scraper.fetch_section_entries(client=mock_client)
        assert len(entries) >= 2
        assert any("sport5.co.il" in e["link"] for e in entries)


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

    def test_walla_extract_clean_article(self):
        scraper = WallaScraper()
        payload = scraper.extract_article(WALLA_ARTICLE_HTML)

        assert payload is not None
        assert payload.publisher == "walla"
        assert "ג'ודו" in payload.title or "מדליית זהב" in payload.title
        assert len(payload.raw_body) <= 3500

    @pytest.mark.asyncio
    async def test_walla_fetch_rss_mocked(self):
        scraper = WallaScraper()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = WALLA_RSS_XML

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        entries = await scraper.fetch_rss(client=mock_client)
        assert len(entries) == 1
        assert "מדליית זהב" in entries[0]["title"]
        assert "walla.co.il" in entries[0]["link"]


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

        s_walla = get_scraper("walla")
        assert isinstance(s_walla, WallaScraper)
        assert s_walla.publisher_id == "walla"

    def test_case_insensitivity_in_registry(self):
        s1 = get_scraper("SPORT5")
        s2 = get_scraper("  yNeT  ")
        s3 = get_scraper("WaLLa")
        assert isinstance(s1, Sport5Scraper)
        assert isinstance(s2, YnetScraper)
        assert isinstance(s3, WallaScraper)

    def test_unknown_publisher_raises_error(self):
        with pytest.raises(ValueError, match="Unknown publisher 'nonexistent'"):
            get_scraper("nonexistent")

    def test_get_all_scrapers(self):
        scrapers = get_all_scrapers()
        assert len(scrapers) == 4
        pub_ids = {s.publisher_id for s in scrapers}
        assert pub_ids == {"sport5", "ynet", "one", "walla"}

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

        mock_section_response = MagicMock()
        mock_section_response.status_code = 200
        mock_section_response.text = SPORT5_SECTION_HTML

        mock_article_response = MagicMock()
        mock_article_response.status_code = 200
        mock_article_response.text = SPORT5_ARTICLE_HTML

        async def mock_get(url, **kwargs):
            if "articles.aspx" in url:
                return mock_article_response
            return mock_section_response

        with patch("httpx.AsyncClient.get", new=mock_get):
            articles = await scraper.scrape(limit=2)
            assert len(articles) <= 2
            assert all(isinstance(a, RawArticlePayload) for a in articles)
            assert all(a.publisher == "sport5" for a in articles)
            assert all(len(a.raw_body) <= 3500 for a in articles)
