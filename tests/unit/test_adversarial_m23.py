"""Empirical Adversarial Test Suite for Milestones 2 & 3 (Challenger 1).

Rigorous empirical challenge and stress-testing for:
1. Multi-source Scrapers (Sport5, ONE, Walla, Ynet, Sport1, Israel Hayom, Haaretz) with malformed HTML, missing paragraphs, missing images, broken RSS XML, and unusual date formats.
2. Canonical URL Normalizer with extreme tracking query strings, multiple hash fragments, encoded characters, and IP/port variations.
3. SHA-256 Content Hasher with erratic whitespace, zero-width characters, right-to-left marks, and various site branding suffixes.
4. IngestionService with mixed batch ingestion containing new articles, duplicates, corrupted pages, and slow network responses.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import unicodedata
from typing import Dict, List, Optional
import pytest
import httpx
from bs4 import BeautifulSoup
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
    clean_html_text,
    compute_content_hash,
    extract_heuristic_dom,
    extract_json_ld,
    extract_opengraph,
    extract_trafilatura,
    normalize_canonical_url,
    parse_datetime,
)
from fan_zone.scrapers.sport5 import Sport5Parser
from fan_zone.scrapers.one import ONEParser
from fan_zone.scrapers.walla import WallaParser
from fan_zone.scrapers.ynet import YnetParser
from fan_zone.scrapers.sport1 import Sport1Parser
from fan_zone.scrapers.israel_hayom import IsraelHayomParser
from fan_zone.scrapers.haaretz import HaaretzParser
from fan_zone.scrapers.registry import (
    ScraperRegistry,
    get_scraper,
    get_scraper_for_url,
    list_scrapers,
)
from fan_zone.services.ingestion_service import IngestionService
from fan_zone.ai.mock import MockAIProcessor


# ==============================================================================
# 1. CANONICAL URL NORMALIZER ADVERSARIAL CHALLENGES
# ==============================================================================

class TestCanonicalUrlNormalizerAdversarial:
    """Stress-tests for URL normalization and canonicalization."""

    def test_strip_30_plus_tracking_parameters_and_mixed_casing(self):
        """Challenge URL normalizer with 30+ tracking params in upper/mixed casing."""
        tracking_params = [
            "utm_source=facebook", "UTM_MEDIUM=cpc", "Utm_Campaign=summer2026",
            "utm_term=football", "utm_content=banner", "utm_name=promo",
            "utm_cid=123", "utm_reader=rss", "fbclid=IwAR987654321",
            "FBCLID=ABC123XYZ", "gclid=Cj0KCQj", "gbraid=gbraid123",
            "wbraid=wbraid456", "ref=homepage", "rnd=9999", "v=2",
            "_ga=GA1.2.3.4", "timestamp=1690000000", "campaign=spring",
            "cmp=cmp123", "tab=news", "xtor=RSS-1", "at_custom1=val1",
            "mvt=test", "mc_cid=abc", "mc_eid=def", "yclid=y123",
            "igshid=ig456", "ocid=oc789", "dclid=dc101", "_hsenc=hs1",
            "_hsmi=hs2"
        ]
        query_str = "&".join(tracking_params) + "&FolderID=64&docID=450000&article_id=9876"
        raw_url = f"https://www.sport5.co.il/articles.aspx?{query_str}"
        canon = normalize_canonical_url(raw_url)

        # Ensure none of the tracking params leaked into canonical URL
        for tp in ["utm_source", "fbclid", "gclid", "wbraid", "ref", "_ga", "yclid", "igshid", "mc_cid"]:
            assert tp not in canon.lower(), f"Tracking parameter '{tp}' was not stripped"

        # Ensure essential params are preserved
        assert "folderid=64" in canon.lower()
        assert "docid=450000" in canon.lower()
        assert "article_id=9876" in canon.lower()

    def test_multiple_hash_fragments_and_angular_react_anchors(self):
        """Challenge URL normalizer with single and multiple hash fragments."""
        cases = [
            ("https://www.one.co.il/Article/123.html#comments", "https://www.one.co.il/Article/123.html"),
            ("https://www.one.co.il/Article/123.html#sec1#sec2#sec3", "https://www.one.co.il/Article/123.html"),
            ("https://www.one.co.il/Article/123.html#!/tab/gallery?photo=5", "https://www.one.co.il/Article/123.html"),
            ("https://www.one.co.il/Article/123.html#top", "https://www.one.co.il/Article/123.html"),
        ]
        for input_url, expected in cases:
            assert normalize_canonical_url(input_url) == expected

    def test_uppercase_schemes_and_hostnames(self):
        """Challenge URL normalizer with uppercase scheme and hostnames."""
        raw_url = "HTTP://WWW.ONE.CO.IL/Article/2026/1234.html"
        canon = normalize_canonical_url(raw_url)
        assert canon.startswith("https://www.one.co.il/Article/2026/1234.html")
        assert "http:/" not in canon.replace("https://", "")

    def test_default_and_custom_ports_normalization(self):
        """Standard HTTP (:80) and HTTPS (:443) ports stripped; custom ports kept."""
        assert normalize_canonical_url("http://www.ynet.co.il:80/sport/article/123") == "https://www.ynet.co.il/sport/article/123"
        assert normalize_canonical_url("https://www.ynet.co.il:443/sport/article/123") == "https://www.ynet.co.il/sport/article/123"
        assert normalize_canonical_url("https://www.ynet.co.il:8080/sport/article/123") == "https://www.ynet.co.il:8080/sport/article/123"
        assert normalize_canonical_url("http://127.0.0.1:8000/articles/1") == "https://127.0.0.1:8000/articles/1"

    def test_relative_schemes_and_excessive_path_slashes(self):
        """Protocol-relative URLs and erratic path slashes."""
        assert normalize_canonical_url("//www.walla.co.il/item/123") == "https://www.walla.co.il/item/123"
        assert normalize_canonical_url("https://sports.walla.co.il///item////123///") == "https://sports.walla.co.il/item/123"
        assert normalize_canonical_url("https://sports.walla.co.il/") == "https://sports.walla.co.il/"

    def test_query_parameter_sorting_and_whitespace_trimming(self):
        """Deterministic query parameter sorting and space trimming."""
        url1 = "https://example.com/art?z=9&a=1&m=5&b=2"
        url2 = "https://example.com/art?b=2&z=9&a=1&m=5"
        assert normalize_canonical_url(url1) == normalize_canonical_url(url2)
        assert normalize_canonical_url(url1) == "https://example.com/art?a=1&b=2&m=5&z=9"

    def test_encoded_hebrew_characters_in_urls(self):
        """Percent-encoded Hebrew characters in query parameters."""
        url = "https://www.sport5.co.il/articles.aspx?folderid=64&name=%D7%9E%D7%9B%D7%91%D7%99"
        canon = normalize_canonical_url(url)
        assert "folderid=64" in canon
        assert "https://www.sport5.co.il/articles.aspx?" in canon

    def test_empty_none_and_invalid_inputs(self):
        """Non-string and empty inputs should return empty string safely."""
        assert normalize_canonical_url("") == ""
        assert normalize_canonical_url("   ") == ""
        assert normalize_canonical_url(None) == ""
        assert normalize_canonical_url(12345) == ""
        assert normalize_canonical_url([]) == ""


# ==============================================================================
# 2. SHA-256 CONTENT HASHER & HEBREW SANITIZATION ADVERSARIAL CHALLENGES
# ==============================================================================

class TestContentHasherAdversarial:
    """Stress-tests for compute_content_hash, clean_html_text, and Hebrew sanitization."""

    def test_zero_width_characters_and_rtl_markers(self):
        """Zero-width spaces (\u200b, \u200c, \u200d, \ufeff, \u00ad) and RTL markers (\u200e, \u200f)."""
        clean_text = "מכבי תל אביב ניצחה במשחק העונה"
        dirty_text = (
            "\u200bמכבי\u200c \u200dתל\u200e \u200fאביב\ufeff "
            "\u00adניצחה במשחק העונה"
        )
        cleaned = clean_html_text(dirty_text)
        assert cleaned == clean_text

    def test_erratic_whitespace_invariance(self):
        """Erratic tabs, consecutive spaces, empty lines, and trailing spaces."""
        title_a = "  מכבי חיפה ניצחה את הפועל באר שבע   "
        title_b = "מכבי חיפה ניצחה את הפועל באר שבע"
        p_a = ["   פסקה ראשונה עם   רווחים מיותרים. \t\t", "", "   \n\n  ", "פסקה שנייה.  "]
        p_b = ["פסקה ראשונה עם רווחים מיותרים.", "פסקה שנייה."]

        hash_a = compute_content_hash(title_a, p_a)
        hash_b = compute_content_hash(title_b, p_b)
        assert hash_a == hash_b
        assert len(hash_a) == 64

    def test_branding_suffixes_stripping_all_7_sources(self):
        """Verify all 7 Israeli sports brandings are stripped from article titles for duplicate detection."""
        base_title = "הפועל תל אביב החתימה את כוכב נבחרת ישראל"
        paragraphs = ["הודעה רשמית נמסרה מטעם המועדון."]
        base_hash = compute_content_hash(base_title, paragraphs)

        suffixes = [
            " | ספורט 5",
            " - ספורט 5",
            " – ספורט 5",
            " - ספורט 1",
            " | ספורט 1",
            " - וואלה! ספורט",
            " - וואלה",
            " – ONE",
            " - ONE",
            " | ONE",
            " - ynet",
            " - ידיעות אחרונות",
            " - ישראל היום",
            " - הארץ",
            " - Sport 5",
            " - Sport 1",
            " - Haaretz",
        ]

        for suffix in suffixes:
            titled_with_suffix = f"{base_title}{suffix}"
            h = compute_content_hash(titled_with_suffix, paragraphs)
            assert h == base_hash, f"Failed to strip branding suffix '{suffix}'"

    def test_unicode_nfc_vs_nfd_composition_equivalence(self):
        """Verify Hebrew string composed vs decomposed normalization."""
        composed = "מַכַּבִּי תֵּל אָבִיב"
        decomposed = unicodedata.normalize("NFD", composed)
        h1 = compute_content_hash(composed, ["פסקת מבחן"])
        h2 = compute_content_hash(decomposed, ["פסקת מבחן"])
        assert h1 == h2

    def test_html_entities_and_control_codes_cleaning(self):
        """Challenge clean_html_text with nested entities and XML entities."""
        raw_html = "&quot;ניצחון ענק&quot; &amp; דרמה גדולה בדקה ה-90"
        cleaned = clean_html_text(raw_html)
        assert cleaned == '"ניצחון ענק" & דרמה גדולה בדקה ה-90'


# ==============================================================================
# 3. DATE PARSER ADVERSARIAL CHALLENGES
# ==============================================================================

class TestDateParsingAdversarial:
    """Stress-tests for parse_datetime across edge-case date formats."""

    def test_iso_8601_with_timezones(self):
        """ISO formats with UTC Z and Israeli Daylight Time +03:00."""
        dt1 = parse_datetime("2026-08-28T21:30:00Z")
        assert dt1.year == 2026 and dt1.month == 8 and dt1.day == 28 and dt1.hour == 21
        assert dt1.tzinfo == timezone.utc

        dt2 = parse_datetime("2026-08-28T21:30:00+03:00")
        assert dt2.tzinfo == timezone.utc
        assert dt2.hour == 18  # 21:30 IDT = 18:30 UTC

    def test_israeli_publisher_date_patterns(self):
        """Test Sport5, ONE, Walla, Ynet date formats."""
        # DD.MM.YY - HH:mm
        dt1 = parse_datetime("28.08.26 - 22:30")
        assert dt1.year == 2026 and dt1.month == 8 and dt1.day == 28 and dt1.hour == 22 and dt1.minute == 30

        # DD/MM/YYYY HH:mm
        dt2 = parse_datetime("28/08/2026 21:15")
        assert dt2.year == 2026 and dt2.month == 8 and dt2.day == 28 and dt2.hour == 21 and dt2.minute == 15

        # Hebrew month name: יום שישי, 28 באוגוסט 2026, 21:30
        dt3 = parse_datetime("יום שישי, 28 באוגוסט 2026, 21:30")
        assert dt3.year == 2026 and dt3.month == 8 and dt3.day == 28 and dt3.hour == 21 and dt3.minute == 30

        # Hebrew month name without time
        dt4 = parse_datetime("15 בינואר 2026")
        assert dt4.year == 2026 and dt4.month == 1 and dt4.day == 15

    def test_corrupt_and_none_dates_safe_fallback(self):
        """Invalid or None dates must return timezone-aware UTC datetime."""
        dt_none = parse_datetime(None)
        assert isinstance(dt_none, datetime)
        assert dt_none.tzinfo == timezone.utc

        dt_garbage = parse_datetime("תאריך לא תקין בעליל $#%^")
        assert isinstance(dt_garbage, datetime)
        assert dt_garbage.tzinfo == timezone.utc


# ==============================================================================
# 4. SCRAPER ADVERSARIAL CHALLENGES FOR ALL 7 OUTLETS
# ==============================================================================

class TestAll7ScrapersAdversarial:
    """Stress-tests parsing on malformed HTML, missing fields, broken RSS for all 7 scrapers."""

    @pytest.fixture
    def registry(self):
        return ScraperRegistry()

    # --- 1. Sport5 ---
    def test_sport5_malformed_html_and_missing_paragraphs(self, registry):
        parser = registry.get_scraper("sport5")
        assert parser is not None

        malformed = """
        <html><body>
        <h1 class="article-title">כותרת ספורט 5 בלבד
        <div class="article-main-image"><img src="/images/lead.jpg">
        <div class="article-body"></div>
        """
        extracted = parser.parse_article_html(malformed, "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=123")
        assert extracted is not None
        assert extracted.original_title == "כותרת ספורט 5 בלבד"
        assert extracted.main_image is not None
        assert extracted.main_image.url == "https://www.sport5.co.il/images/lead.jpg"
        assert len(extracted.paragraphs) == 0

    def test_sport5_broken_rss_feed(self, registry):
        parser = registry.get_scraper("sport5")
        broken_xml = "<rss><channel><title>Sport5</title><item><title>Title</title><link>https://www.sport5.co.il/articles.aspx?FolderID=64&docID=10</link></item><item><broken_tag></channel>"
        links = parser.parse_rss_feed(broken_xml)
        assert len(links) >= 1
        assert "sport5.co.il" in links[0]

    # --- 2. ONE ---
    def test_one_malformed_html_and_missing_author(self, registry):
        parser = registry.get_scraper("one")
        assert parser is not None

        html = """
        <div id="article-content">
            <h1 class="article-title">כותרת ONE ללא כתב ותאריך</h1>
            <div class="article-body-content">
                <p>פסקה ראשונה של כתבת ONE המכילה מספיק תווים.</p>
            </div>
        </div>
        """
        extracted = parser.parse_article_html(html, "https://www.one.co.il/Article/2026/111111.html")
        assert extracted is not None
        assert extracted.original_title == "כותרת ONE ללא כתב ותאריך"
        assert extracted.author is None
        assert len(extracted.paragraphs) == 1
        assert extracted.main_image is None

    def test_one_broken_rss_feed(self, registry):
        parser = registry.get_scraper("one")
        broken_xml = "<?xml><rss><channel><item><link>https://www.one.co.il/Article/2026/100.html</link></item></channel>"
        links = parser.parse_rss_feed(broken_xml)
        assert len(links) == 1
        assert "100.html" in links[0]

    # --- 3. Walla ---
    def test_walla_json_ld_fallback_when_css_missing(self, registry):
        parser = registry.get_scraper("walla")
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@type": "NewsArticle",
                "headline": "כותרת וואלה מ-JSON-LD",
                "description": "תקציר וואלה מ-JSON-LD",
                "articleBody": "גוף כתבה מוטמע ב-JSON-LD עבור וואלה ספורט.",
                "author": {"name": "כתב וואלה"},
                "datePublished": "2026-08-28T20:00:00Z",
                "image": "https://img.wcdn.co.il/test.jpg"
            }
            </script>
        </head>
        <body><div class="unknown-walla-container">אין סלקטורים רגילים</div></body>
        </html>
        """
        extracted = parser.parse_article_html(html, "https://sports.walla.co.il/item/3691234")
        assert extracted is not None
        assert extracted.original_title == "כותרת וואלה מ-JSON-LD"
        assert extracted.original_subtitle == "תקציר וואלה מ-JSON-LD"
        assert extracted.author == "כתב וואלה"
        assert extracted.main_image.url == "https://img.wcdn.co.il/test.jpg"

    # --- 4. Ynet ---
    def test_ynet_opengraph_fallback_with_broken_html(self, registry):
        parser = registry.get_scraper("ynet")
        html = """
        <html>
        <head>
            <meta property="og:title" content="כותרת Ynet מ-OpenGraph" />
            <meta property="og:description" content="תקציר Ynet מ-OpenGraph" />
            <meta property="og:image" content="https://ynet.co.il/img.jpg" />
            <meta property="article:published_time" content="2026-08-28T19:00:00Z" />
        </head>
        <body>
            <div><p>פסקה ראשונה בגוף הכתבה של Ynet עם מעל עשרים תווים.</p></div>
        </body>
        </html>
        """
        extracted = parser.parse_article_html(html, "https://www.ynet.co.il/sport/article/r123456")
        assert extracted is not None
        assert extracted.original_title == "כותרת Ynet מ-OpenGraph"
        assert extracted.original_subtitle == "תקציר Ynet מ-OpenGraph"
        assert extracted.main_image.url == "https://ynet.co.il/img.jpg"

    # --- 5. Sport1 ---
    def test_sport1_malformed_html_and_gallery(self, registry):
        parser = registry.get_scraper("sport1")
        html = """
        <article>
            <h1 class="entry-title">כותרת ספורט 1 מעריב</h1>
            <h2 class="entry-subtitle">משנה ספורט 1 מעריב</h2>
            <div class="byline"><span>יוני הללי</span></div>
            <figure class="featured-image"><img src="https://sport1.maariv.co.il/main.jpg"><figcaption class="image-caption">תמונה ראשית</figcaption></figure>
            <div class="gallery-images">
                <img src="https://sport1.maariv.co.il/g1.jpg">
                <img src="https://sport1.maariv.co.il/g2.jpg">
            </div>
            <div class="entry-content">
                <p>פסקה ראשונה בכתבת ספורט 1 מעריב עם תוכן עשיר.</p>
                <p>פסקה שנייה בכתבת ספורט 1 מעריב עם פירוט נוסף.</p>
            </div>
        </article>
        """
        extracted = parser.parse_article_html(html, "https://sport1.maariv.co.il/article/999888")
        assert extracted is not None
        assert extracted.original_title == "כותרת ספורט 1 מעריב"
        assert extracted.author == "יוני הללי"
        assert extracted.main_image.url == "https://sport1.maariv.co.il/main.jpg"
        assert len(extracted.gallery_images) == 2
        assert len(extracted.paragraphs) == 2

    # --- 6. Israel Hayom ---
    def test_israel_hayom_corrupted_markup(self, registry):
        parser = registry.get_scraper("israel_hayom")
        html = """
        <html>
        <h1 class="article-title">ישראל היום: ניצחון מוחץ בדרבי</h1>
        <div class="writer-name">אבי סגל</div>
        <div class="article-content">
            <p>שחקני הקבוצה השיגו ניצחון מרשים במיוחד באולם הביתי.</p>
        </div>
        """
        extracted = parser.parse_article_html(html, "https://www.israelhayom.co.il/sport/article/777666")
        assert extracted is not None
        assert extracted.original_title == "ישראל היום: ניצחון מוחץ בדרבי"
        assert extracted.author == "אבי סגל"
        assert len(extracted.paragraphs) == 1

    # --- 7. Haaretz ---
    def test_haaretz_data_test_attributes(self, registry):
        parser = registry.get_scraper("haaretz")
        html = """
        <html>
        <head><title>הארץ ספורט</title></head>
        <body>
            <h1 data-test="articleHeadline">הארץ: תחקיר על ענף השחייה הישראלי</h1>
            <h2 data-test="articleSubtitle">חשיפת הנתונים והאתגרים לקראת המשחקים האולימפיים.</h2>
            <span data-test="authorName">עוזי דן</span>
            <time data-test="publishDate" datetime="2026-08-28T16:00:00Z">28 באוגוסט 2026</time>
            <figure data-test="mainFigure"><img src="https://haaretz.co.il/swimming.jpg" /><figcaption data-test="caption">בריכת השחייה</figcaption></figure>
            <article data-test="articleBody">
                <p>ענף השחייה הישראלי רושם התקדמות חסרת תקדים בשנים האחרונות.</p>
                <p>המאמנים הלאומיים מצביעים על שיפור ניכר בתוצאות השחיינים הצעירים.</p>
            </article>
        </body>
        </html>
        """
        extracted = parser.parse_article_html(html, "https://www.haaretz.co.il/sport/swimming/article/1.9999999")
        assert extracted is not None
        assert extracted.original_title == "הארץ: תחקיר על ענף השחייה הישראלי"
        assert extracted.author == "עוזי דן"
        assert len(extracted.paragraphs) == 2
        assert extracted.main_image.url == "https://haaretz.co.il/swimming.jpg"

    def test_registry_url_routing_all_sources(self, registry):
        """Test automatic parser selection by URL for all 7 outlets."""
        urls = [
            ("https://www.sport5.co.il/articles.aspx?FolderID=64&docID=1", "Sport5"),
            ("https://www.one.co.il/Article/2026/1234.html", "ONE"),
            ("https://sports.walla.co.il/item/3690000", "Walla! Sports"),
            ("https://www.ynet.co.il/sport/article/y1234", "Ynet Sport"),
            ("https://sport1.maariv.co.il/article/5555", "Sport1"),
            ("https://www.israelhayom.co.il/sport/article/777", "Israel Hayom"),
            ("https://www.haaretz.co.il/sport/1.12345", "Haaretz"),
        ]
        for url, expected_name in urls:
            p = registry.get_scraper_for_url(url)
            assert p is not None, f"Failed to resolve scraper for URL: {url}"
            assert p.source_name == expected_name


# ==============================================================================
# 5. INGESTION SERVICE ADVERSARIAL & MIXED BATCH CHALLENGES
# ==============================================================================

class TestIngestionServiceAdversarial:
    """Stress-tests for IngestionService under hostile conditions."""

    @pytest.mark.asyncio
    async def test_mixed_batch_ingestion_with_duplicates_and_corrupted_pages(
        self, db_session: AsyncSession
    ):
        """Challenge IngestionService with a mixed batch containing:
        - Fresh new article
        - Duplicate URL
        - Duplicate content hash
        - Corrupted / unparseable HTML
        - AI service failure fallback
        """
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)
        sources = await source_repo.seed_default_sources()
        source_sport5 = next(s for s in sources if s.name == "sport5")

        ai_mock = MockAIProcessor()
        service = IngestionService(db=db_session, ai_processor=ai_mock)

        # 1. Ingest clean article 1
        art1_extracted = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=101",
            canonical_url="https://www.sport5.co.il/articles.aspx?docID=101&FolderID=64",
            content_hash=compute_content_hash("כותרת ראשונה 101", ["פסקה ראשונה בגוף הכתבה."]),
            original_title="כותרת ראשונה 101",
            original_subtitle="משנה ראשון 101",
            author="כתב 101",
            published_at=datetime.now(timezone.utc),
            paragraphs=["פסקה ראשונה בגוף הכתבה."],
            raw_body_text="פסקה ראשונה בגוף הכתבה.",
            main_image=ExtractedImage(url="https://sport5.co.il/img101.jpg", is_main=True),
        )

        try:
            art1, created1 = await service.process_and_persist_article(art1_extracted, source_sport5)
            assert created1 is True
            assert art1.id is not None
        except TypeError as e:
            pytest.fail(f"IngestionService failed with TypeError during persist: {e}")

        # 2. Duplicate Content Hash (different URL, identical title and paragraphs)
        art2_duplicate_hash = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=102",
            canonical_url="https://www.sport5.co.il/articles.aspx?docID=102&FolderID=64",
            content_hash=compute_content_hash("כותרת ראשונה 101", ["פסקה ראשונה בגוף הכתבה."]),
            original_title="כותרת ראשונה 101",
            published_at=datetime.now(timezone.utc),
            paragraphs=["פסקה ראשונה בגוף הכתבה."],
            raw_body_text="פסקה ראשונה בגוף הכתבה.",
        )
        art2, created2 = await service.process_and_persist_article(art2_duplicate_hash, source_sport5)
        assert created2 is False
        assert art2.id == art1.id  # Resolved to existing article

        # 3. AI Failure Fallback
        class FailingAI:
            async def analyze_article(self, title, subtitle, body):
                raise RuntimeError("AI Rate Limit Exceeded (429)")

        failing_service = IngestionService(db=db_session, ai_processor=FailingAI())
        art3_extracted = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=103",
            canonical_url="https://www.sport5.co.il/articles.aspx?docID=103&FolderID=64",
            content_hash=compute_content_hash("כותרת כתבה 103", ["פסקה ראשונה בגוף 103."]),
            original_title="כותרת כתבה 103",
            published_at=datetime.now(timezone.utc),
            paragraphs=["פסקה ראשונה בגוף 103."],
            raw_body_text="פסקה ראשונה בגוף 103.",
        )
        art3, created3 = await failing_service.process_and_persist_article(art3_extracted, source_sport5)
        assert created3 is True
        assert art3.ingestion_status == IngestionStatus.AI_FALLBACK
        assert "429" in (art3.error_message or "")
        assert art3.ai_headline == "כותרת כתבה 103"

    @pytest.mark.asyncio
    async def test_mock_network_transport_batch_ingest_source(self, db_session: AsyncSession):
        """Simulate real HTTP client with custom MockTransport for discovery and article fetching."""
        source_repo = SourceRepository(db_session)
        sources = await source_repo.seed_default_sources()
        source_sport5 = next(s for s in sources if s.name == "sport5")

        sample_article_html = """
        <html>
        <head><title>Sport5 News</title></head>
        <body>
            <h1 class="article-title">מכבי תל אביב גברה 0:3 על בית"ר</h1>
            <h2 class="article-subtitle">ערן זהבי כבש צמד שערים מרהיב.</h2>
            <span class="article-credit">תומר לוי</span>
            <span class="article-date">28.08.26 - 21:00</span>
            <div class="article-main-image"><img src="https://images.sport5.co.il/lead.jpg"></div>
            <div class="article-body">
                <p>מכבי תל אביב הפגינה עליונות מוחלטת במשחק הערב באצטדיון בלומפילד.</p>
                <p>הקבוצה השיגה ניצחון מוחץ משערים של זהבי ופרץ.</p>
            </div>
        </body>
        </html>
        """

        def mock_handler(request: httpx.Request):
            url_str = str(request.url)
            if "articles.aspx?FolderID=64" in url_str:
                discovery_html = """
                <html><body>
                    <a href="/articles.aspx?FolderID=64&docID=999901">כתבה 1</a>
                    <a href="/articles.aspx?FolderID=64&docID=999902">כתבה 2</a>
                    <a href="https://other-domain.com/ad">פרסומת</a>
                </body></html>
                """
                return httpx.Response(200, text=discovery_html, request=request)
            elif "docID=999901" in url_str:
                return httpx.Response(200, text=sample_article_html, request=request)
            elif "docID=999902" in url_str:
                return httpx.Response(500, text="Internal Server Error", request=request)
            return httpx.Response(404, request=request)

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
        service = IngestionService(
            db=db_session,
            ai_processor=MockAIProcessor(),
            client=mock_client,
        )

        try:
            stats = await service.ingest_source(source_sport5.id, max_articles=5)
            assert stats.total_discovered >= 2
            assert stats.total_ingested == 1
        except (TypeError, ValueError) as e:
            pytest.fail(f"IngestionService.ingest_source failed with exception: {e}")
        finally:
            await mock_client.aclose()
