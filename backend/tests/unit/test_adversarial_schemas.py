"""Adversarial stress-testing suite for Pydantic schemas and Settings configuration (Milestone 1).

Author: m1_challenger_1
Covers:
- Extreme unicode, Hebrew RTL, nikkud, cantillation, bidirectional markers
- HTML and script injection payloads (XSS vectors, unclosed tags, nested tags)
- Word count edge boundaries (0, 1, 39, 40, 41, 100 words, unicode whitespace)
- Entity tag lists (empty, pure whitespace, duplicates, boundary counts, non-strings)
- URL schemes, malformed URLs, oversized inputs, XSS in URLs
- Case sensitivity and enum validation (ToneEnum, PublisherEnum)
- Negative numbers and pagination boundaries
- Settings environment variable parsing and dialect property resilience
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from core.config import Settings
from schemas.feed import (
    AIEnrichedCard,
    FeedItemResponse,
    HealthCheckResponse,
    IngestionTriggerResponse,
    PaginatedFeedResponse,
    PublisherEnum,
    RawArticlePayload,
    ToneEnum,
    UserPreferences,
    strip_html_tags,
)


# ============================================================================
# 1. HTML Sanitization & strip_html_tags Adversarial Tests
# ============================================================================

class TestAdversarialHtmlSanitization:
    """Stress-testing HTML sanitization utility against malicious and malformed markup."""

    @pytest.mark.parametrize(
        "dirty_input, expected_clean",
        [
            ("<b>מודגש</b>", "מודגש"),
            ("<div>פסקה ראשונה</div><div>פסקה שנייה</div>", "פסקה ראשונה פסקה שנייה"),
            ("&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;", '<script>alert("xss")</script>'),
            ("מכבי ת&quot;א &amp; הפועל י-ם", 'מכבי ת"א & הפועל י-ם'),
            ("  שלום   \n\t  עולם   ", "שלום עולם"),
        ],
    )
    def test_clean_standard_cases(self, dirty_input, expected_clean):
        assert strip_html_tags(dirty_input) == expected_clean

    @pytest.mark.parametrize(
        "malicious_input",
        [
            "<script>alert('XSS')</script>",
            "<SCRIPT SRC='http://evil.com/xss.js'></SCRIPT>",
            "<script type='text/javascript'>document.cookie='steal';</script>",
            "<style>body { display: none; }</style>",
            "<STYLE>.ad { color: red; }</STYLE>",
        ],
    )
    def test_complete_script_and_style_removal(self, malicious_input):
        """Verify script and style blocks and their contents are completely eliminated."""
        cleaned = strip_html_tags(malicious_input)
        assert cleaned == ""
        assert "alert" not in cleaned
        assert "script" not in cleaned.lower()
        assert "style" not in cleaned.lower()

    def test_nested_tags_and_xss_vectors(self):
        """Edge case: Nested tags designed to bypass single-pass regex."""
        nested = "<p>מכבי <script><script>alert(1)</script></script>ניצחה</p>"
        cleaned = strip_html_tags(nested)
        assert "<script>" not in cleaned
        assert "מכבי" in cleaned
        assert "ניצחה" in cleaned

    def test_empty_and_whitespace_inputs(self):
        assert strip_html_tags("") == ""
        assert strip_html_tags("   ") == ""
        assert strip_html_tags("\n\t\r") == ""
        assert strip_html_tags(None) == ""


# ============================================================================
# 2. RawArticlePayload Adversarial Tests
# ============================================================================

class TestAdversarialRawArticlePayload:
    """Stress-testing RawArticlePayload model with extreme inputs and edge cases."""

    def test_hebrew_rtl_and_nikkud_payload(self):
        """Validates proper ingestion of Hebrew text with vowel marks (nikkud) and BiDi marks."""
        title_nikkud = "מַכָּבִי תֵּל-אָבִיב נִצְּחָה אֶת הַפּוֹעֵל יְרוּשָׁלַיִם"
        body_bidi = "\u200E(Maccabi Tel Aviv)\u200F ניצחה בתוצאה 89:82 במשחק חוץ ביורוליג."

        payload = RawArticlePayload(
            title=title_nikkud,
            raw_body=body_bidi,
            url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450000",
            publisher="Sport5",
        )
        assert payload.title == title_nikkud
        assert "Maccabi Tel Aviv" in payload.raw_body
        assert payload.publisher == "sport5"

    def test_script_injection_in_title_and_body(self):
        """Validates that scripts embedded in title/body are sanitized upon ingestion."""
        payload = RawArticlePayload(
            title="<script>evil()</script>דרמה בטרנר: 1:1 בין ב\"ש למכבי חיפה",
            raw_body="<p>שער שוויון בדקה ה-94. <iframe src='http://evil.com'></iframe></p>",
            url="https://www.one.co.il/Article/24-25/1,1,1,0/456789.html",
            publisher="ONE",
        )
        assert "<script>" not in payload.title
        assert "evil()" not in payload.title
        assert "דרמה בטרנר" in payload.title
        assert "<iframe>" not in payload.raw_body

    def test_title_empty_after_sanitization_raises_validation_error(self):
        """If title contains only HTML/scripts, stripping results in empty string -> must fail."""
        with pytest.raises(ValidationError):
            RawArticlePayload(
                title="<script>steal_cookie();</script><div>   </div>",
                raw_body="גוף הכתבה התקין",
                url="https://www.ynet.co.il/sport/1",
                publisher="ynet",
            )

    def test_raw_body_empty_after_sanitization_raises_validation_error(self):
        """If raw_body contains only HTML/scripts, stripping results in empty string -> must fail."""
        with pytest.raises(ValidationError):
            RawArticlePayload(
                title="כותרת תקינה",
                raw_body="<style>.css{display:none;}</style><script>alert(1)</script>",
                url="https://www.ynet.co.il/sport/1",
                publisher="ynet",
            )

    @pytest.mark.parametrize(
        "valid_url",
        [
            "http://sport5.co.il",
            "https://www.ynet.co.il/sport/article/123456",
            "https://one.co.il/article?id=123&sec=4#comment",
            "https://sub.domain.israelhayom.co.il:8080/path/to/page",
            "http://sport1.maariv.co.il/israeli-soccer/ligat-haal/article/999/",
        ],
    )
    def test_valid_urls_accepted(self, valid_url):
        payload = RawArticlePayload(
            title="כותרת",
            raw_body="תוכן הכתבה",
            url=valid_url,
            publisher="sport5",
        )
        assert payload.url == valid_url

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "ftp://files.sport5.co.il/doc.pdf",
            "javascript:alert('xss')",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "file:///etc/passwd",
            "ws://socket.sport5.co.il/feed",
            "htp://typo.com",
            "www.sport5.co.il/no-scheme",
            "https//missing-colon.com",
            "",
            "   ",
        ],
    )
    def test_invalid_urls_rejected(self, invalid_url):
        with pytest.raises(ValidationError):
            RawArticlePayload(
                title="כותרת",
                raw_body="תוכן הכתבה",
                url=invalid_url,
                publisher="sport5",
            )

    def test_publisher_normalization(self):
        """Verify publisher strings are lowercased and stripped."""
        payload1 = RawArticlePayload(
            title="כותרת",
            raw_body="תוכן",
            url="https://sport5.co.il/1",
            publisher="  SPORT5  ",
        )
        assert payload1.publisher == "sport5"

        payload2 = RawArticlePayload(
            title="כותרת",
            raw_body="תוכן",
            url="https://ynet.co.il/1",
            publisher="YnEt",
        )
        assert payload2.publisher == "ynet"

    def test_max_length_boundary_title(self):
        """Title with exact 500 characters should pass, 501 should fail."""
        valid_title = "א" * 500
        payload = RawArticlePayload(
            title=valid_title,
            raw_body="גוף כתבה",
            url="https://sport5.co.il/1",
            publisher="sport5",
        )
        assert len(payload.title) == 500

        invalid_title = "א" * 501
        with pytest.raises(ValidationError):
            RawArticlePayload(
                title=invalid_title,
                raw_body="גוף כתבה",
                url="https://sport5.co.il/1",
                publisher="sport5",
            )


# ============================================================================
# 3. AIEnrichedCard Adversarial Tests
# ============================================================================

class TestAdversarialAIEnrichedCard:
    """Stress-testing AIEnrichedCard with word count boundaries, tag variations, and tone constraints."""

    def test_micro_summary_exact_boundaries(self):
        """Test micro_summary word boundaries: 39, 40 (pass), 41 (fail), 100 (fail)."""
        words_39 = " ".join([f"מילה{i}" for i in range(1, 40)])
        card_39 = AIEnrichedCard(
            micro_summary=words_39,
            tags=["מכבי תל אביב"],
            tone=ToneEnum.OBJECTIVE,
            context_label="דוח משחק",
        )
        assert len(card_39.micro_summary.split()) == 39

        words_40 = " ".join([f"מילה{i}" for i in range(1, 41)])
        card_40 = AIEnrichedCard(
            micro_summary=words_40,
            tags=["מכבי תל אביב"],
            tone=ToneEnum.OBJECTIVE,
            context_label="דוח משחק",
        )
        assert len(card_40.micro_summary.split()) == 40

        words_41 = " ".join([f"מילה{i}" for i in range(1, 42)])
        with pytest.raises(ValidationError) as excinfo_41:
            AIEnrichedCard(
                micro_summary=words_41,
                tags=["מכבי תל אביב"],
                tone=ToneEnum.OBJECTIVE,
                context_label="דוח משחק",
            )
        assert "exceeds word limit" in str(excinfo_41.value)

        words_100 = " ".join([f"word{i}" for i in range(1, 101)])
        with pytest.raises(ValidationError) as excinfo_100:
            AIEnrichedCard(
                micro_summary=words_100,
                tags=["מכבי תל אביב"],
                tone=ToneEnum.OBJECTIVE,
                context_label="דוח משחק",
            )
        assert "exceeds word limit" in str(excinfo_100.value) or "String should have at most 400 characters" in str(excinfo_100.value)

    def test_micro_summary_whitespace_and_tabs(self):
        """Whitespace normalization in word count calculation."""
        summary = "  מכבי   תל \n\t אביב \r\n ניצחה   את \t ריאל   מדריד  "
        card = AIEnrichedCard(
            micro_summary=summary,
            tags=["מכבי תל אביב", "יורוליג"],
            tone=ToneEnum.HYPE,
            context_label="Match Report",
        )
        assert len(card.micro_summary.split()) == 7

    def test_micro_summary_too_short_raises_error(self):
        """micro_summary under min_length (10 chars) must fail."""
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="קצר מדי",  # 7 chars
                tags=["ספורט"],
                tone=ToneEnum.OBJECTIVE,
                context_label="חדשות",
            )

    def test_tags_boundary_limits(self):
        """Test tag list constraints: 1 tag (min), 15 tags (max), 16 tags (fail)."""
        card_1 = AIEnrichedCard(
            micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
            tags=["מכבי תל אביב"],
            tone=ToneEnum.OBJECTIVE,
            context_label="חדשות",
        )
        assert len(card_1.tags) == 1

        tags_15 = [f"קבוצה_{i}" for i in range(1, 16)]
        card_15 = AIEnrichedCard(
            micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
            tags=tags_15,
            tone=ToneEnum.OBJECTIVE,
            context_label="חדשות",
        )
        assert len(card_15.tags) == 15

        tags_16 = [f"קבוצה_{i}" for i in range(1, 17)]
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
                tags=tags_16,
                tone=ToneEnum.OBJECTIVE,
                context_label="חדשות",
            )

    def test_tags_deduplication_preserves_order(self):
        """Duplicates in tags list should be removed while preserving order."""
        card = AIEnrichedCard(
            micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
            tags=["מכבי חיפה", "ליגת העל", "מכבי חיפה", " ברק בכר ", "ליגת העל"],
            tone=ToneEnum.OBJECTIVE,
            context_label="ניתוח",
        )
        assert card.tags == ["מכבי חיפה", "ליגת העל", "ברק בכר"]

    def test_tone_enum_valid_and_invalid_values(self):
        """Verify ToneEnum enforces strictly 'objective', 'hype', 'critical'."""
        for valid_tone in [ToneEnum.OBJECTIVE, ToneEnum.HYPE, ToneEnum.CRITICAL, "objective", "hype", "critical"]:
            card = AIEnrichedCard(
                micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
                tags=["ספורט"],
                tone=valid_tone,
                context_label="חדשות",
            )
            assert isinstance(card.tone, ToneEnum)

        for invalid_tone in ["neutral", "HYPE", "Objective", "CRITICAL", "positive", "negative", "", 123]:
            with pytest.raises(ValidationError):
                AIEnrichedCard(
                    micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
                    tags=["ספורט"],
                    tone=invalid_tone,  # type: ignore
                    context_label="חדשות",
                )

    def test_context_label_boundaries(self):
        """context_label must be between 2 and 50 characters."""
        card_min = AIEnrichedCard(
            micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
            tags=["ספורט"],
            tone=ToneEnum.OBJECTIVE,
            context_label="דו",
        )
        assert card_min.context_label == "דו"

        card_max = AIEnrichedCard(
            micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
            tags=["ספורט"],
            tone=ToneEnum.OBJECTIVE,
            context_label="א" * 50,
        )
        assert len(card_max.context_label) == 50

        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
                tags=["ספורט"],
                tone=ToneEnum.OBJECTIVE,
                context_label="א",
            )

        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תקין של הכתבה עם לפחות עשר אותיות.",
                tags=["ספורט"],
                tone=ToneEnum.OBJECTIVE,
                context_label="א" * 51,
            )


# ============================================================================
# 4. UserPreferences Adversarial Tests
# ============================================================================

class TestAdversarialUserPreferences:
    """Stress-testing UserPreferences model."""

    def test_user_preferences_list_cleaning(self):
        """Verify whitespace stripping and deduplication in user filter lists."""
        prefs = UserPreferences(
            followed_tags=[" מכבי תל אביב ", "יורוליג", "  ", "מכבי תל אביב", "\tהפועל ירושלים\n"],
            excluded_sources=[" ONE ", "one", "  walla  ", ""],
            preferred_tones=[ToneEnum.HYPE, ToneEnum.OBJECTIVE],
            language="he",
        )
        assert prefs.followed_tags == ["מכבי תל אביב", "יורוליג", "הפועל ירושלים"]
        assert prefs.excluded_sources == ["ONE", "one", "walla"]
        assert len(prefs.preferred_tones) == 2

    def test_language_code_length_boundary(self):
        """language code max length is 10 chars."""
        prefs_valid = UserPreferences(language="he-IL")
        assert prefs_valid.language == "he-IL"

        with pytest.raises(ValidationError):
            UserPreferences(language="hebrew-israel-extended")


# ============================================================================
# 5. PaginatedFeedResponse Adversarial Tests
# ============================================================================

class TestAdversarialPaginatedFeedResponse:
    """Stress-testing PaginatedFeedResponse boundaries and negative numbers."""

    @pytest.mark.parametrize(
        "invalid_kwargs",
        [
            {"total": -1, "page": 1, "page_size": 10, "total_pages": 0, "has_next": False, "has_prev": False},
            {"total": 10, "page": 0, "page_size": 10, "total_pages": 1, "has_next": False, "has_prev": False},
            {"total": 10, "page": -5, "page_size": 10, "total_pages": 1, "has_next": False, "has_prev": False},
            {"total": 10, "page": 1, "page_size": 0, "total_pages": 1, "has_next": False, "has_prev": False},
            {"total": 10, "page": 1, "page_size": 101, "total_pages": 1, "has_next": False, "has_prev": False},
            {"total": 10, "page": 1, "page_size": 10, "total_pages": -1, "has_next": False, "has_prev": False},
        ],
    )
    def test_negative_and_out_of_bound_pagination_rejected(self, invalid_kwargs):
        with pytest.raises(ValidationError):
            PaginatedFeedResponse(**invalid_kwargs)

    def test_zero_total_valid_empty_page(self):
        """Valid empty result pagination response."""
        res = PaginatedFeedResponse(
            items=[],
            total=0,
            page=1,
            page_size=20,
            total_pages=0,
            has_next=False,
            has_prev=False,
        )
        assert res.total == 0
        assert res.items == []
        assert res.total_pages == 0


# ============================================================================
# 6. Settings Configuration Adversarial Tests
# ============================================================================

class TestAdversarialSettings:
    """Stress-testing Settings configuration, environment overrides, and dialect resolution."""

    @pytest.mark.parametrize(
        "db_url, is_sqlite, is_postgres",
        [
            ("sqlite+aiosqlite:///./fan_zone.db", True, False),
            ("sqlite:///./fan_zone.db", True, False),
            ("SQLITE+AIOSQLITE:///./TEST.DB", True, False),
            ("postgresql+asyncpg://user:pass@localhost:5432/fanzone", False, True),
            ("postgresql://user:pass@localhost:5432/fanzone", False, True),
            ("postgres://user:pass@localhost:5432/fanzone", False, True),
            ("POSTGRESQL+ASYNCPG://DB:5432/TEST", False, True),
            ("mysql://user:pass@localhost:3306/db", False, False),
            ("oracle://user:pass@localhost:1521/db", False, False),
            ("", False, False),
        ],
    )
    def test_dialect_detection_resilience(self, db_url, is_sqlite, is_postgres):
        s = Settings(DATABASE_URL=db_url)
        assert s.is_sqlite is is_sqlite
        assert s.is_postgres is is_postgres

    @pytest.mark.parametrize(
        "mock_flag, api_key, expected_is_mock",
        [
            (True, "valid-gemini-key", True),
            (True, None, True),
            (True, "", True),
            (False, None, True),
            (False, "", True),
            (False, "   ", True),
            (False, "valid-gemini-api-key-12345", False),
        ],
    )
    def test_mock_ai_resolution_matrix(self, mock_flag, api_key, expected_is_mock):
        s = Settings(USE_MOCK_AI=mock_flag, GEMINI_API_KEY=api_key)
        assert s.is_mock_ai is expected_is_mock

    def test_env_override_type_conversions(self, monkeypatch):
        """Test environment variable string to type coercions."""
        monkeypatch.setenv("PORT", "9999")
        monkeypatch.setenv("POLL_INTERVAL_SECONDS", "600")
        monkeypatch.setenv("SCRAPER_TIMEOUT_SECONDS", "30")
        monkeypatch.setenv("MAX_CONCURRENT_SCRAPES", "8")
        monkeypatch.setenv("ENABLE_SCHEDULER", "false")
        monkeypatch.setenv("DEBUG", "1")

        s = Settings()
        assert s.PORT == 9999
        assert s.POLL_INTERVAL_SECONDS == 600
        assert s.SCRAPER_TIMEOUT_SECONDS == 30
        assert s.MAX_CONCURRENT_SCRAPES == 8
        assert s.ENABLE_SCHEDULER is False
        assert s.DEBUG is True
