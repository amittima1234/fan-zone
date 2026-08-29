"""Empirical stress test suite for Milestone 1 (Schemas, ORM compatibility, and Settings).

Authored by m1_challenger_2.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import List, Optional
import pytest
from pydantic import ValidationError

from core.config import Settings, get_settings
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


# ===========================================================================
# 1. JSON Serialization & Deserialization Tests (All Schemas)
# ===========================================================================

class TestSchemaJsonSerializationDeserialization:
    """Stress-tests model_dump, model_dump_json, model_validate, model_validate_json."""

    def test_raw_article_payload_json_roundtrip(self):
        original = RawArticlePayload(
            title="מכבי תל אביב &quot;אלופה&quot; ביורוליג 2026",
            raw_body="<p>תקציר <b>הניצחון</b> על ריאל מדריד בהיכל מנורה.</p>",
            url="https://www.sport5.co.il/articles.aspx?docID=9999",
            publisher=" SPORT5 ",
            published_at=datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc),
            category="basketball",
            author="עמרי פולק",
            image_url="https://images.sport5.co.il/img1.jpg",
        )

        # 1. model_dump_json
        json_str = original.model_dump_json()
        assert isinstance(json_str, str)
        parsed_json = json.loads(json_str)
        assert parsed_json["title"] == 'מכבי תל אביב "אלופה" ביורוליג 2026'
        assert parsed_json["raw_body"] == "תקציר הניצחון על ריאל מדריד בהיכל מנורה."
        assert parsed_json["publisher"] == "sport5"
        assert parsed_json["url"] == "https://www.sport5.co.il/articles.aspx?docID=9999"

        # 2. model_validate_json
        reconstructed = RawArticlePayload.model_validate_json(json_str)
        assert reconstructed.title == original.title
        assert reconstructed.raw_body == original.raw_body
        assert reconstructed.url == original.url
        assert reconstructed.publisher == original.publisher
        assert reconstructed.published_at == original.published_at
        assert reconstructed.category == original.category
        assert reconstructed.author == original.author
        assert reconstructed.image_url == original.image_url

        # 3. model_validate from dict
        dict_data = original.model_dump()
        reconstructed_dict = RawArticlePayload.model_validate(dict_data)
        assert reconstructed_dict == reconstructed

    def test_raw_article_payload_boundary_and_validation_errors(self):
        # Empty title after sanitization
        with pytest.raises(ValidationError):
            RawArticlePayload(
                title="<div><script>alert(1)</script></div>",
                raw_body="תוכן הכתבה",
                url="https://sport5.co.il/1",
                publisher="sport5",
            )

        # Invalid URL protocols
        invalid_urls = [
            "ftp://files.sport5.co.il/article",
            "javascript:alert('xss')",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "relative/path/to/article",
            "file:///etc/passwd",
        ]
        for inv_url in invalid_urls:
            with pytest.raises(ValidationError):
                RawArticlePayload(
                    title="כותרת תקינה",
                    raw_body="גוף כתבה תקין",
                    url=inv_url,
                    publisher="sport5",
                )

        # Publisher casing and trimming
        payload = RawArticlePayload(
            title="כותרת",
            raw_body="גוף",
            url="http://www.one.co.il/news",
            publisher="  ONE  ",
        )
        assert payload.publisher == "one"

    def test_ai_enriched_card_json_roundtrip_and_word_boundaries(self):
        # 40-word summary (boundary test - maximum allowed)
        words_40 = " ".join([f"מילה{i}" for i in range(1, 41)])
        card_40 = AIEnrichedCard(
            micro_summary=words_40,
            tags=["מכבי תל אביב", "יורוליג", "כדורסל"],
            tone=ToneEnum.HYPE,
            context_label="Match Report",
        )
        json_str = card_40.model_dump_json()
        reconstructed = AIEnrichedCard.model_validate_json(json_str)
        assert reconstructed.micro_summary == words_40
        assert reconstructed.tone == ToneEnum.HYPE
        assert reconstructed.tags == ["מכבי תל אביב", "יורוליג", "כדורסל"]

        # 41-word summary (boundary test - must fail)
        words_41 = " ".join([f"מילה{i}" for i in range(1, 42)])
        with pytest.raises(ValidationError) as exc_info:
            AIEnrichedCard(
                micro_summary=words_41,
                tags=["ספורט"],
                tone=ToneEnum.OBJECTIVE,
                context_label="News",
            )
        assert "exceeds word limit" in str(exc_info.value)

    def test_ai_enriched_card_tag_deduplication_and_order(self):
        card = AIEnrichedCard(
            micro_summary="סיכום תמציתי ומדויק של משחק גמר הגביע בכדורסל.",
            tags=[" מכבי תל אביב ", "הפועל ירושלים", " מכבי תל אביב ", "יורוקאפ", "   "],
            tone=ToneEnum.OBJECTIVE,
            context_label="Championship",
        )
        assert card.tags == ["מכבי תל אביב", "הפועל ירושלים", "יורוקאפ"]

        # Verify JSON serialization preserves clean tags
        data = json.loads(card.model_dump_json())
        assert data["tags"] == ["מכבי תל אביב", "הפועל ירושלים", "יורוקאפ"]

    def test_ai_enriched_card_invalid_inputs(self):
        # Empty tags list
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תמציתי ומדויק של משחק כדורסל.",
                tags=[],
                tone=ToneEnum.OBJECTIVE,
                context_label="News",
            )

        # Tags with only whitespace
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תמציתי ומדויק של משחק כדורסל.",
                tags=["  ", "\t", ""],
                tone=ToneEnum.OBJECTIVE,
                context_label="News",
            )

        # Context label too short (< 2 chars)
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תמציתי ומדויק של משחק כדורסל.",
                tags=["כדורסל"],
                tone=ToneEnum.OBJECTIVE,
                context_label="A",
            )

        # Context label too long (> 50 chars)
        with pytest.raises(ValidationError):
            AIEnrichedCard(
                micro_summary="סיכום תמציתי ומדויק של משחק כדורסל.",
                tags=["כדורסל"],
                tone=ToneEnum.OBJECTIVE,
                context_label="X" * 51,
            )

    def test_user_preferences_json_roundtrip(self):
        prefs = UserPreferences(
            followed_tags=[" כדורגל ישראלי ", "נבחרת ישראל", " כדורגל ישראלי "],
            excluded_sources=[" one ", " walla "],
            preferred_tones=[ToneEnum.OBJECTIVE, ToneEnum.HYPE],
            language="he",
        )
        assert prefs.followed_tags == ["כדורגל ישראלי", "נבחרת ישראל"]
        assert prefs.excluded_sources == ["one", "walla"]

        json_str = prefs.model_dump_json()
        reconstructed = UserPreferences.model_validate_json(json_str)
        assert reconstructed.followed_tags == prefs.followed_tags
        assert reconstructed.excluded_sources == prefs.excluded_sources
        assert reconstructed.preferred_tones == [ToneEnum.OBJECTIVE, ToneEnum.HYPE]
        assert reconstructed.language == "he"

    def test_feed_item_response_json_roundtrip(self):
        now = datetime(2026, 8, 29, 14, 0, 0, tzinfo=timezone.utc)
        item = FeedItemResponse(
            id=42,
            title="ניצחון היסטורי באליפות אירופה בג'ודו",
            url="https://sports.walla.co.il/item/369901",
            publisher="walla",
            published_at=now,
            micro_summary="מדליית זהב קבוצתית לנבחרת ישראל בג'ודו בטביליסי.",
            tags=["ג'ודו", "נבחרת ישראל", "פיטר פלצ'יק"],
            tone=ToneEnum.HYPE,
            context_label="ספורט אולימפי",
            category="ג'ודו",
            author="יניב טוכמן",
            created_at=now,
        )

        json_str = item.model_dump_json()
        reconstructed = FeedItemResponse.model_validate_json(json_str)
        assert reconstructed.id == 42
        assert reconstructed.title == item.title
        assert reconstructed.tone == ToneEnum.HYPE
        assert reconstructed.published_at == now
        assert reconstructed.created_at == now

    def test_paginated_feed_response_json_roundtrip(self):
        now = datetime(2026, 8, 29, 14, 0, 0, tzinfo=timezone.utc)
        item1 = FeedItemResponse(
            id=1,
            title="כותרת 1",
            url="https://sport5.co.il/1",
            publisher="sport5",
            published_at=now,
            micro_summary="סיכום חדשותי ראשון וממצה.",
            tags=["כדורסל"],
            tone=ToneEnum.OBJECTIVE,
            context_label="News",
            created_at=now,
        )
        paginated = PaginatedFeedResponse(
            items=[item1],
            total=100,
            page=2,
            page_size=10,
            total_pages=10,
            has_next=True,
            has_prev=True,
        )

        json_str = paginated.model_dump_json()
        reconstructed = PaginatedFeedResponse.model_validate_json(json_str)
        assert reconstructed.total == 100
        assert reconstructed.page == 2
        assert reconstructed.page_size == 10
        assert reconstructed.total_pages == 10
        assert reconstructed.has_next is True
        assert reconstructed.has_prev is True
        assert len(reconstructed.items) == 1
        assert reconstructed.items[0].id == 1

    def test_health_check_and_ingestion_response_json_roundtrip(self):
        health = HealthCheckResponse(
            status="healthy",
            app_name="FanZone Israeli Sports Ingestion Backend",
            environment="production",
            database="connected",
            ai_mode="live_gemini",
            scheduler="enabled",
        )
        json_health = health.model_dump_json()
        rec_health = HealthCheckResponse.model_validate_json(json_health)
        assert rec_health.status == "healthy"
        assert rec_health.ai_mode == "live_gemini"

        trigger = IngestionTriggerResponse(
            status="completed",
            publisher="sport5",
            articles_fetched=25,
            articles_queued=20,
            message="Ingested 20 new articles",
            errors=[],
        )
        json_trigger = trigger.model_dump_json()
        rec_trigger = IngestionTriggerResponse.model_validate_json(json_trigger)
        assert rec_trigger.status == "completed"
        assert rec_trigger.articles_fetched == 25
        assert rec_trigger.articles_queued == 20


# ===========================================================================
# 2. ORM Compatibility Stress Tests (from_attributes=True)
# ===========================================================================

class TestFeedItemResponseOrmCompatibility:
    """Tests FeedItemResponse.model_validate with various ORM-like dummy objects."""

    def test_orm_dummy_class_instance(self):
        """Simulates an active SQLAlchemy ArticleModel instance with extra internal attributes."""
        class DummySQLAlchemyArticle:
            def __init__(self):
                self.id = 1001
                self.title = "סערה בבית\"ר ירושלים"
                self.url = "https://www.ynet.co.il/sport/article/1"
                self.publisher = "ynet"
                self.published_at = datetime(2026, 8, 29, 10, 0, 0, tzinfo=timezone.utc)
                self.micro_summary = "החלוץ הזר הודיע על עזיבה מיידית לטורקיה."
                self.tags = ["בית\"ר ירושלים", "ליגת העל"]
                self.tone = ToneEnum.CRITICAL
                self.context_label = "משבר במועדון"
                self.category = "football"
                self.author = "גידי ליפקין"
                self.created_at = datetime(2026, 8, 29, 10, 5, 0, tzinfo=timezone.utc)
                # Extra SQLAlchemy internal attributes to test that extra fields are safely ignored
                self._sa_instance_state = "<InstanceState at 0x7f00>"
                self.raw_body = "גוף הכתבה המקורי..."
                self.embedding = [0.1, 0.2, 0.3]

        orm_obj = DummySQLAlchemyArticle()
        response = FeedItemResponse.model_validate(orm_obj, from_attributes=True)

        assert response.id == 1001
        assert response.title == "סערה בבית\"ר ירושלים"
        assert response.publisher == "ynet"
        assert response.tone == ToneEnum.CRITICAL
        assert response.tags == ["בית\"ר ירושלים", "ליגת העל"]
        assert response.category == "football"
        assert response.author == "גידי ליפקין"

    def test_orm_dataclass_instance(self):
        """Simulates a dataclass-based repository DTO or record."""
        @dataclass
        class ArticleDTO:
            id: int
            title: str
            url: str
            publisher: str
            published_at: datetime
            micro_summary: str
            tags: List[str]
            tone: str  # Note: string representation of ToneEnum
            context_label: str
            category: Optional[str]
            author: Optional[str]
            created_at: datetime

        now = datetime(2026, 8, 29, 11, 0, 0, tzinfo=timezone.utc)
        dto = ArticleDTO(
            id=55,
            title="פרסום ראשון: הפועל באר שבע",
            url="https://www.one.co.il/Article/123",
            publisher="one",
            published_at=now,
            micro_summary="מו\"מ מתקדם עם קשר רומני לקונפרנס ליג.",
            tags=["הפועל באר שבע", "קונפרנס ליג"],
            tone="objective",
            context_label="העברות",
            category=None,
            author=None,
            created_at=now,
        )

        response = FeedItemResponse.model_validate(dto, from_attributes=True)
        assert response.id == 55
        assert response.tone == ToneEnum.OBJECTIVE
        assert response.category is None
        assert response.author is None

    def test_orm_with_property_getters(self):
        """Simulates an ORM model where fields are computed properties."""
        class DynamicArticleModel:
            @property
            def id(self): return 99
            @property
            def title(self): return "כותרת דינמית"
            @property
            def url(self): return "https://sport5.co.il/dyn"
            @property
            def publisher(self): return "sport5"
            @property
            def published_at(self): return datetime(2026, 8, 29, 8, 0, 0, tzinfo=timezone.utc)
            @property
            def micro_summary(self): return "סיכום דינמי של המשחק."
            @property
            def tags(self): return ["דינמי", "ספורט"]
            @property
            def tone(self): return "hype"
            @property
            def context_label(self): return "Live Update"
            @property
            def category(self): return "News"
            @property
            def author(self): return "מערכת"
            @property
            def created_at(self): return datetime(2026, 8, 29, 8, 5, 0, tzinfo=timezone.utc)

        response = FeedItemResponse.model_validate(DynamicArticleModel(), from_attributes=True)
        assert response.id == 99
        assert response.title == "כותרת דינמית"
        assert response.tone == ToneEnum.HYPE


# ===========================================================================
# 3. Settings Configuration Stress Tests
# ===========================================================================

class TestSettingsStress:
    """Stress-tests Settings with various environment variables and boundary conditions."""

    def test_settings_sqlite_variants(self):
        s1 = Settings(DATABASE_URL="sqlite+aiosqlite:///./fan_zone.db")
        assert s1.is_sqlite is True
        assert s1.is_postgres is False

        s2 = Settings(DATABASE_URL="SQLITE+AIOSQLITE:///:memory:")
        assert s2.is_sqlite is True
        assert s2.is_postgres is False

        s3 = Settings(DATABASE_URL="sqlite:///./test.db")
        assert s3.is_sqlite is True
        assert s3.is_postgres is False

    def test_settings_postgres_variants(self):
        s1 = Settings(DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/fan_zone")
        assert s1.is_postgres is True
        assert s1.is_sqlite is False

        s2 = Settings(DATABASE_URL="postgres://user:pass@localhost:5432/fan_zone")
        assert s2.is_postgres is True
        assert s2.is_sqlite is False

        s3 = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/fan_zone")
        assert s3.is_postgres is True
        assert s3.is_sqlite is False

    def test_settings_mock_ai_combinations(self):
        # Case A: Explicit USE_MOCK_AI=True with valid key -> True
        assert Settings(USE_MOCK_AI=True, GEMINI_API_KEY="AIzaSyDummyKey").is_mock_ai is True

        # Case B: USE_MOCK_AI=False with None key -> True
        assert Settings(USE_MOCK_AI=False, GEMINI_API_KEY=None).is_mock_ai is True

        # Case C: USE_MOCK_AI=False with empty/whitespace key -> True
        assert Settings(USE_MOCK_AI=False, GEMINI_API_KEY="").is_mock_ai is True
        assert Settings(USE_MOCK_AI=False, GEMINI_API_KEY="   \t  ").is_mock_ai is True

        # Case D: USE_MOCK_AI=False with valid non-empty key -> False
        assert Settings(USE_MOCK_AI=False, GEMINI_API_KEY="AIzaSyValidProductionKey").is_mock_ai is False

    def test_settings_environment_variable_parsing(self, monkeypatch):
        monkeypatch.setenv("APP_NAME", "Fan Zone Production Service")
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("DEBUG", "1")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("HOST", "127.0.0.1")
        monkeypatch.setenv("PORT", "9999")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://prod_user:prod_pass@db.internal:5432/prod_fanzone")
        monkeypatch.setenv("DB_ECHO", "true")
        monkeypatch.setenv("GEMINI_API_KEY", "prod-gemini-key")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.7-flash")
        monkeypatch.setenv("USE_MOCK_AI", "false")
        monkeypatch.setenv("ENABLE_SCHEDULER", "false")
        monkeypatch.setenv("POLL_INTERVAL_SECONDS", "120")
        monkeypatch.setenv("SCRAPER_TIMEOUT_SECONDS", "30")
        monkeypatch.setenv("MAX_CONCURRENT_SCRAPES", "8")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        # Extra unknown environment variables should be safely ignored
        monkeypatch.setenv("UNKNOWN_CUSTOM_VAR", "ignored_value")

        s = Settings()
        assert s.APP_NAME == "Fan Zone Production Service"
        assert s.APP_ENV == "production"
        assert s.DEBUG is True
        assert s.LOG_LEVEL == "DEBUG"
        assert s.HOST == "127.0.0.1"
        assert s.PORT == 9999
        assert s.is_postgres is True
        assert s.is_sqlite is False
        assert s.DB_ECHO is True
        assert s.GEMINI_API_KEY == "prod-gemini-key"
        assert s.is_mock_ai is False
        assert s.ENABLE_SCHEDULER is False
        assert s.POLL_INTERVAL_SECONDS == 120
        assert s.SCRAPER_TIMEOUT_SECONDS == 30
        assert s.MAX_CONCURRENT_SCRAPES == 8
        assert s.REDIS_URL == "redis://localhost:6379/0"

    def test_settings_invalid_integer_type_raises_validation_error(self, monkeypatch):
        monkeypatch.setenv("PORT", "not_a_valid_port_number")
        with pytest.raises(ValidationError):
            Settings()

    def test_settings_case_insensitivity(self, monkeypatch):
        # SettingsConfigDict specifies case_sensitive=False
        monkeypatch.setenv("port", "8888")
        monkeypatch.setenv("app_env", "test")
        monkeypatch.setenv("use_mock_ai", "true")

        s = Settings()
        assert s.PORT == 8888
        assert s.APP_ENV == "test"
        assert s.USE_MOCK_AI is True
