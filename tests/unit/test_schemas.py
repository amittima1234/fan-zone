"""Unit tests for Pydantic schemas and contracts (Milestone 1)."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

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


class TestToneEnum:
    """Tests for journalistic ToneEnum."""

    def test_tone_enum_members(self):
        assert ToneEnum.OBJECTIVE.value == "objective"
        assert ToneEnum.HYPE.value == "hype"
        assert ToneEnum.CRITICAL.value == "critical"

    def test_tone_enum_iteration(self):
        tones = [t.value for t in ToneEnum]
        assert "objective" in tones
        assert "hype" in tones
        assert "critical" in tones
        assert len(tones) == 3


class TestPublisherEnum:
    """Tests for PublisherEnum."""

    def test_publisher_enum_members(self):
        expected_publishers = [
            "sport5",
            "ynet",
            "one",
            "walla",
            "israel_hayom",
            "sport1",
            "haaretz",
            "other",
        ]
        for pub in expected_publishers:
            assert PublisherEnum(pub).value == pub


class TestHtmlSanitization:
    """Tests for strip_html_tags utility."""

    def test_strip_basic_html(self):
        html_input = "<p>מכבי תל אביב ניצחה <b>84:82</b> את פנאתינייקוס.</p>"
        expected = "מכבי תל אביב ניצחה 84:82 את פנאתינייקוס."
        assert strip_html_tags(html_input) == expected

    def test_strip_scripts_and_styles(self):
        html_input = (
            "<style>.hide{display:none;}</style>"
            "<div>חדשות ספורט</div>"
            "<script>alert('xss');</script>"
        )
        assert strip_html_tags(html_input) == "חדשות ספורט"

    def test_strip_scripts_and_styles_with_spaces_in_closing_tags(self):
        html_input = (
            "<script type='text/javascript' >alert('evil');</script >"
            "<style >.hide{display:none;}</style   >"
            "<span>תוכן לאחר סקריפטים</span>"
        )
        assert strip_html_tags(html_input) == "תוכן לאחר סקריפטים"

    def test_strip_html_punctuation_preservation(self):
        html_input = (
            "<p>שלום <b>חברים</b>, מה <i>השלום</i>? הכל <u>מצוין</u>! פרטים: <span>כאן</span>; תודה.</p>"
        )
        expected = "שלום חברים, מה השלום? הכל מצוין! פרטים: כאן; תודה."
        assert strip_html_tags(html_input) == expected

    def test_unescape_html_entities(self):
        html_input = "הפועל &quot;בנק יהב&quot; ירושלים &amp; מכבי ת&quot;א"
        expected = 'הפועל "בנק יהב" ירושלים & מכבי ת"א'
        assert strip_html_tags(html_input) == expected

    def test_empty_or_none(self):
        assert strip_html_tags("") == ""
        assert strip_html_tags(None) == ""


class TestRawArticlePayload:
    """Tests for RawArticlePayload Pydantic model."""

    def test_valid_payload_creation(self):
        payload = RawArticlePayload(
            title="מכבי חיפה העפילה לשלב הבא",
            raw_body="הירוקים מהכרמל גברו 2:0 על הפועל באר שבע במשחק דרמטי.",
            url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450123",
            publisher="Sport5",
            category="israeli-football",
            author="יוסי כהן",
            image_url="https://images.sport5.co.il/pic1.jpg",
        )
        assert payload.title == "מכבי חיפה העפילה לשלב הבא"
        assert payload.raw_body == "הירוקים מהכרמל גברו 2:0 על הפועל באר שבע במשחק דרמטי."
        assert payload.url == "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450123"
        assert payload.publisher == "sport5"
        assert payload.category == "israeli-football"
        assert payload.author == "יוסי כהן"
        assert payload.image_url == "https://images.sport5.co.il/pic1.jpg"
        assert isinstance(payload.published_at, datetime)

    def test_html_sanitization_in_payload(self):
        payload = RawArticlePayload(
            title="<h1>כותרת ראשית</h1><script >steal()</script >",
            raw_body="<p>פסקה ראשונה עם <strong>הדגשה</strong>.</p>",
            url="https://www.ynet.co.il/sport/article/12345",
            publisher="ynet",
        )
        assert payload.title == "כותרת ראשית"
        assert payload.raw_body == "פסקה ראשונה עם הדגשה."

    def test_invalid_url_raises_validation_error(self):
        with pytest.raises(ValidationError) as excinfo:
            RawArticlePayload(
                title="כותרת תקינה",
                raw_body="תוכן גוף הכתבה התקין.",
                url="ftp://invalid-protocol.com/file",
                publisher="one",
            )
        assert "URL must start with http:// or https://" in str(excinfo.value)

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "http://",
            "https://",
            "http:///no-domain-path",
            "https:///article/123",
            "   http://   ",
            "ftp://files.sport5.co.il",
            "javascript:void(0)",
            "not-a-url",
        ],
    )
    def test_validate_url_rejects_empty_netloc_and_malformed_urls(self, invalid_url):
        with pytest.raises(ValidationError):
            RawArticlePayload(
                title="כותרת תקינה",
                raw_body="תוכן גוף הכתבה התקין.",
                url=invalid_url,
                publisher="one",
            )

    def test_empty_title_after_sanitization_raises_validation_error(self):
        with pytest.raises(ValidationError):
            RawArticlePayload(
                title="   <p></p>   ",
                raw_body="תוכן הכתבה",
                url="https://www.sport5.co.il/article/1",
                publisher="sport5",
            )


class TestAIEnrichedCard:
    """Tests for AIEnrichedCard Pydantic model."""

    def test_valid_ai_enriched_card(self):
        card = AIEnrichedCard(
            micro_summary="מכבי תל אביב הבטיחה את מקומה בפלייאוף היורוליג לאחר ניצחון מוחץ על פנאתינייקוס.",
            tags=["מכבי תל אביב", "יורוליג", "כדורסל"],
            tone=ToneEnum.HYPE,
            context_label="Match Report",
        )
        assert card.micro_summary.startswith("מכבי תל אביב")
        assert len(card.tags) == 3
        assert card.tone == ToneEnum.HYPE
        assert card.context_label == "Match Report"

    def test_tag_cleaning_and_deduplication(self):
        card = AIEnrichedCard(
            micro_summary="הפועל ירושלים זכתה בגביע המדינה בכדורסל.",
            tags=[" הפועל ירושלים ", "יורוקאפ", " הפועל ירושלים ", "  "],
            tone=ToneEnum.OBJECTIVE,
            context_label="Championship",
        )
        assert card.tags == ["הפועל ירושלים", "יורוקאפ"]

    def test_empty_tags_raises_validation_error(self):
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תקין של הכתבה ב-15 מילים לפחות לבדיקה מדויקת.",
                tags=[],
                tone=ToneEnum.OBJECTIVE,
                context_label="News",
            )

        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תקין של הכתבה ב-15 מילים לפחות לבדיקה מדויקת.",
                tags=["  ", " \t "],
                tone=ToneEnum.OBJECTIVE,
                context_label="News",
            )

    def test_invalid_tone_raises_validation_error(self):
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תקין של הכתבה ב-15 מילים לפחות לבדיקה מדויקת.",
                tags=["מכבי חיפה"],
                tone="neutral",  # type: ignore
                context_label="Analysis",
            )

    def test_excessive_micro_summary_words_raises_validation_error(self):
        # 45 words summary
        long_summary = " ".join(["מילה"] * 45)
        with pytest.raises(ValidationError) as excinfo:
            AIEnrichedCard(
                micro_summary=long_summary,
                tags=["ספורט"],
                tone=ToneEnum.CRITICAL,
                context_label="Opinion",
            )
        assert "exceeds word limit" in str(excinfo.value)

    def test_short_context_label_raises_validation_error(self):
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תקין של הכתבה ב-15 מילים לפחות לבדיקה מדויקת.",
                tags=["ספורט"],
                tone=ToneEnum.CRITICAL,
                context_label="A",
            )


class TestUserPreferences:
    """Tests for UserPreferences model."""

    def test_default_preferences(self):
        prefs = UserPreferences()
        assert prefs.followed_tags == []
        assert prefs.excluded_sources == []
        assert prefs.preferred_tones is None
        assert prefs.language == "he"

    def test_custom_preferences_and_cleaning(self):
        prefs = UserPreferences(
            followed_tags=[" מכבי תל אביב ", "יורוליג", " מכבי תל אביב "],
            excluded_sources=[" one ", "walla "],
            preferred_tones=[ToneEnum.OBJECTIVE, ToneEnum.HYPE],
            language="he",
        )
        assert prefs.followed_tags == ["מכבי תל אביב", "יורוליג"]
        assert prefs.excluded_sources == ["one", "walla"]
        assert prefs.preferred_tones == [ToneEnum.OBJECTIVE, ToneEnum.HYPE]


class TestFeedItemResponse:
    """Tests for FeedItemResponse model."""

    def test_feed_item_response_serialization(self):
        now = datetime.now(timezone.utc)
        item = FeedItemResponse(
            id=101,
            title="ניצחון דרמטי בדרבי",
            url="https://www.sport5.co.il/articles.aspx?docID=123",
            publisher="sport5",
            published_at=now,
            micro_summary="מכבי גברה על הפועל בדרבי התל אביבי הלוהט.",
            tags=["מכבי תל אביב", "הפועל תל אביב", "ליגת העל"],
            tone=ToneEnum.HYPE,
            context_label="Match Report",
            category="football",
            author="דניאל לוי",
            created_at=now,
        )
        data = item.model_dump()
        assert data["id"] == 101
        assert data["publisher"] == "sport5"
        assert data["tone"] == "hype"
        assert len(data["tags"]) == 3


class TestPaginatedFeedResponse:
    """Tests for PaginatedFeedResponse model."""

    def test_paginated_response(self):
        now = datetime.now(timezone.utc)
        item = FeedItemResponse(
            id=1,
            title="כותרת",
            url="https://sport5.co.il/1",
            publisher="sport5",
            published_at=now,
            micro_summary="תקציר קצר וענייני של הידיעה החדשותית.",
            tags=["כדורסל"],
            tone=ToneEnum.OBJECTIVE,
            context_label="News",
            created_at=now,
        )
        paginated = PaginatedFeedResponse(
            items=[item],
            total=25,
            page=1,
            page_size=10,
            total_pages=3,
            has_next=True,
            has_prev=False,
        )
        assert paginated.total == 25
        assert paginated.page == 1
        assert paginated.page_size == 10
        assert paginated.has_next is True
        assert paginated.has_prev is False
        assert len(paginated.items) == 1


class TestHealthAndIngestionResponses:
    """Tests for HealthCheckResponse and IngestionTriggerResponse."""

    def test_health_check_response(self):
        health = HealthCheckResponse(
            status="healthy",
            app_name="FanZone Israeli Sports Ingestion Backend",
            environment="development",
            database="connected",
            ai_mode="live_gemini",
            scheduler="enabled",
        )
        assert health.status == "healthy"
        assert health.database == "connected"
        assert isinstance(health.timestamp, datetime)

    def test_ingestion_trigger_response(self):
        trigger = IngestionTriggerResponse(
            status="completed",
            publisher="sport5",
            articles_fetched=12,
            articles_queued=10,
            message="Successfully ingested 10 articles from sport5",
            errors=[],
        )
        assert trigger.status == "completed"
        assert trigger.articles_fetched == 12
        assert trigger.articles_queued == 10
