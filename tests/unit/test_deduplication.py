"""Unit tests for URL canonicalization, content hashing, HTML cleaning, date parsing, and per-source deduplication."""

from datetime import datetime, timezone
import hashlib
import unicodedata
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.article import Article
from fan_zone.models.enums import IngestionStatus
from fan_zone.models.source import Source
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.scrapers.base import (
    clean_html_text,
    compute_content_hash,
    normalize_canonical_url,
    parse_datetime,
)


class TestCanonicalUrlNormalization:
    """Unit tests for URL normalization, tracking parameter stripping, and canonicalization."""

    def test_strip_tracking_parameters(self):
        url = "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450000&utm_source=facebook&utm_medium=cpc&fbclid=IwAR12345&ref=hp"
        normalized = normalize_canonical_url(url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized
        assert "fbclid" not in normalized
        assert "ref=" not in normalized
        assert "folderid=64" in normalized.lower()
        assert "docid=450000" in normalized.lower()
        assert normalized.startswith("https://www.sport5.co.il/articles.aspx?")

    def test_sort_query_parameters(self):
        url1 = "https://sports.walla.co.il/item/123456?b=2&a=1"
        url2 = "https://sports.walla.co.il/item/123456?a=1&b=2"
        assert normalize_canonical_url(url1) == normalize_canonical_url(url2)
        assert normalize_canonical_url(url1) == "https://sports.walla.co.il/item/123456?a=1&b=2"

    def test_lowercase_scheme_and_host(self):
        url = "HTTP://WWW.ONE.CO.IL/Article/2026/1234.html"
        normalized = normalize_canonical_url(url)
        assert normalized.startswith("https://www.one.co.il/Article/2026/1234.html")
        assert "http:/" not in normalized.replace("https://", "")

    def test_strip_trailing_slash_and_fragment(self):
        url = "https://www.ynet.co.il/sport/article/r123456/#comments"
        normalized = normalize_canonical_url(url)
        assert normalized == "https://www.ynet.co.il/sport/article/r123456"

    def test_empty_and_invalid_inputs(self):
        assert normalize_canonical_url("") == ""
        assert normalize_canonical_url(None) == ""
        assert normalize_canonical_url("   ") == ""
        assert normalize_canonical_url(12345) == ""

    def test_multiple_slashes_and_protocol_relative(self):
        assert normalize_canonical_url("//www.walla.co.il/item/123") == "https://www.walla.co.il/item/123"
        assert normalize_canonical_url("https://sports.walla.co.il///item////123///") == "https://sports.walla.co.il/item/123"


class TestContentHashingDeduplication:
    """Unit tests for content fingerprinting and SHA-256 deduplication."""

    def test_deterministic_hash_output(self):
        title = "מכבי תל אביב ניצחה את ריאל מדריד"
        paragraphs = ["משחק מצוין של הצהובים.", "ווייד בולדווין הוביל את הקלעים."]
        h1 = compute_content_hash(title, paragraphs)
        h2 = compute_content_hash(title, paragraphs)
        assert h1 == h2
        assert len(h1) == 64

    def test_unicode_nfc_normalization(self):
        composed = "מכבי חיפה"
        decomposed = unicodedata.normalize("NFD", composed)
        h_composed = compute_content_hash(composed, ["פסקת מבחן"])
        h_decomposed = compute_content_hash(decomposed, ["פסקת מבחן"])
        assert h_composed == h_decomposed

    def test_branding_suffix_stripping(self):
        title1 = "מכבי תל אביב הביסה את הפועל | ספורט 5"
        title2 = "מכבי תל אביב הביסה את הפועל - וואלה! ספורט"
        title3 = "מכבי תל אביב הביסה את הפועל"
        paragraphs = ["ניצחון ענק בדרבי התל אביבי."]
        assert compute_content_hash(title1, paragraphs) == compute_content_hash(title3, paragraphs)
        assert compute_content_hash(title2, paragraphs) == compute_content_hash(title3, paragraphs)

    def test_whitespace_normalization(self):
        title = " כותרת  עם   רווחים  "
        paragraphs = ["  פסקה   ראשונה \t ", "\n\n פסקה   שנייה   "]
        h1 = compute_content_hash(title, paragraphs)
        h2 = compute_content_hash("כותרת עם רווחים", ["פסקה ראשונה", "פסקה שנייה"])
        assert h1 == h2


class TestHtmlSanitization:
    """Unit tests for clean_html_text."""

    def test_html_tag_stripping_preserves_bracketed_entities(self):
        raw = "&quot;<b>ניצחון ענק</b>&quot; &amp; &lt;דרמה גדולה&#62; &nbsp;&nbsp; בדקה ה-90"
        cleaned = clean_html_text(raw)
        assert cleaned == '"ניצחון ענק" & <דרמה גדולה> בדקה ה-90'

    def test_zero_width_and_rtl_markers_removed(self):
        dirty = "\u200bמכבי\u200c \u200dתל\u200e \u200fאביב\ufeff \u00adניצחה"
        cleaned = clean_html_text(dirty)
        assert cleaned == "מכבי תל אביב ניצחה"


class TestDateParsing:
    """Unit tests for parse_datetime."""

    def test_iso_and_hebrew_formats(self):
        dt1 = parse_datetime("2026-08-28T21:30:00Z")
        assert dt1.year == 2026 and dt1.month == 8 and dt1.day == 28
        assert dt1.tzinfo == timezone.utc

        dt2 = parse_datetime("28.08.26 - 22:30")
        assert dt2.year == 2026 and dt2.month == 8 and dt2.day == 28 and dt2.hour == 22 and dt2.minute == 30

        dt3 = parse_datetime("28 באוגוסט 2026, 21:30")
        assert dt3.year == 2026 and dt3.month == 8 and dt3.day == 28 and dt3.hour == 21 and dt3.minute == 30

    def test_fallback_on_corrupt_date(self):
        dt = parse_datetime("תאריך שגוי")
        assert isinstance(dt, datetime)
        assert dt.tzinfo == timezone.utc


@pytest.mark.asyncio
class TestPerSourceDeduplication:
    """Verifies that deduplication is strictly scoped per source."""

    async def test_distinct_sources_can_ingest_same_story(self, db_session: AsyncSession):
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)

        sources = await source_repo.seed_default_sources()
        source_sport5 = next(s for s in sources if s.name == "sport5")
        source_walla = next(s for s in sources if s.name == "walla")

        now = datetime.now(timezone.utc)
        title = "מכבי תל אביב זכתה באליפות המדינה"
        paragraphs = ["הצהובים השלימו סוויפ מרשים בסדרת הגמר."]
        shared_hash = compute_content_hash(title, paragraphs)

        # 1. Ingest for Sport5
        art1, created1 = await article_repo.upsert_article({
            "source_id": source_sport5.id,
            "canonical_url": "https://www.sport5.co.il/articles.aspx?docID=888",
            "content_hash": shared_hash,
            "original_title": title,
            "published_at": now,
            "raw_paragraphs": paragraphs,
        })
        assert created1 is True
        assert art1.id is not None

        # 2. Ingest same story for Walla
        art2, created2 = await article_repo.upsert_article({
            "source_id": source_walla.id,
            "canonical_url": "https://sports.walla.co.il/item/888",
            "content_hash": shared_hash,
            "original_title": title,
            "published_at": now,
            "raw_paragraphs": paragraphs,
        })
        assert created2 is True
        assert art2.id is not None
        assert art2.id != art1.id  # Separate records

        # 3. Re-ingesting for Sport5 with same content hash must return existing Sport5 article
        art3, created3 = await article_repo.upsert_article({
            "source_id": source_sport5.id,
            "canonical_url": "https://www.sport5.co.il/articles.aspx?docID=888_alt",
            "content_hash": shared_hash,
            "original_title": title,
            "published_at": now,
            "raw_paragraphs": paragraphs,
        })
        assert created3 is False
        assert art3.id == art1.id


class TestStoryServiceTimeWindow:
    """Unit tests for timezone-naive, timezone-aware, and ISO string time window calculations in StoryService."""

    def test_time_window_naive_and_aware_comparison(self):
        from fan_zone.services.story_service import StoryService
        from datetime import datetime, timezone, timedelta

        dt_naive = datetime(2026, 8, 29, 12, 0, 0)
        dt_aware = datetime(2026, 8, 29, 12, 30, 0, tzinfo=timezone.utc)

        # Naive vs aware within 48h (default 172800s)
        assert StoryService._is_within_time_window(dt_naive, dt_aware) is True
        assert StoryService._is_within_time_window(dt_aware, dt_naive) is True

        # Outside time window (3 days apart)
        dt_far = dt_naive + timedelta(days=3)
        assert StoryService._is_within_time_window(dt_naive, dt_far) is False
        assert StoryService._is_within_time_window(dt_far, dt_aware) is False

        # None values return True (safe fallback)
        assert StoryService._is_within_time_window(None, dt_aware) is True
        assert StoryService._is_within_time_window(dt_naive, None) is True
        assert StoryService._is_within_time_window(None, None) is True

        # ISO strings
        assert StoryService._is_within_time_window("2026-08-29T12:00:00Z", "2026-08-29T13:00:00Z") is True
        assert StoryService._is_within_time_window("invalid_date", dt_aware) is True
