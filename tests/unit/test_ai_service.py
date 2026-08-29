"""Unit tests for AIService, GeminiAIProcessor resilience, fallback chains, and schema validation."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from fan_zone.ai.base import ArticleAnalysisResult, BaseAIProcessor
from fan_zone.ai.fallback import RuleBasedAIProcessor
from fan_zone.ai.gemini_client import GeminiAIProcessor
from fan_zone.ai.mock import MockAIProcessor
from fan_zone.ai.service import AIService, get_ai_processor, get_ai_service
from fan_zone.config import Settings


class TestArticleAnalysisResultSchema:
    """Test suite for Pydantic schema validation, field cleaning, and deduplication."""

    def test_valid_schema_instantiation(self):
        """Verify normal instantiation with clean Hebrew values."""
        result = ArticleAnalysisResult(
            headline="מכבי תל אביב ניצחה 80:85 את הפועל ירושלים",
            subheadline="משחק צמוד בהיכל מנורה הסתיים בניצחון צהוב.",
            sport="כדורסל",
            teams=["מכבי תל אביב", "הפועל ירושלים"],
            players=["עודד קטש"],
            competition="ליגת העל בכדורסל",
            tags=["סיכום משחק", "כדורסל"],
        )
        assert result.headline == "מכבי תל אביב ניצחה 80:85 את הפועל ירושלים"
        assert result.sport == "כדורסל"
        assert len(result.teams) == 2
        assert result.competition == "ליגת העל בכדורסל"

    def test_schema_field_validators_strip_and_deduplicate(self):
        """Verify validators strip whitespace and deduplicate lists."""
        result = ArticleAnalysisResult(
            headline="   כותרת עם רווחים   ",
            subheadline="   כותרת משנה עם רווחים   ",
            sport="  כדורגל  ",
            teams=[" מכבי חיפה ", "מכבי חיפה", " בית\"ר ירושלים "],
            players=[" ערן זהבי ", "ערן זהבי "],
            competition="   ליגת העל   ",
            tags=["העברות", "העברות", " רכש "],
        )
        assert result.headline == "כותרת עם רווחים"
        assert result.subheadline == "כותרת משנה עם רווחים"
        assert result.sport == "כדורגל"
        assert result.teams == ["מכבי חיפה", "בית\"ר ירושלים"]
        assert result.players == ["ערן זהבי"]
        assert result.competition == "ליגת העל"
        assert result.tags == ["העברות", "רכש"]

    def test_schema_default_sport_fallback(self):
        """Verify empty sport defaults safely to 'ענפים נוספים'."""
        result = ArticleAnalysisResult(
            headline="כותרת",
            subheadline="כותרת משנה",
            sport="",
        )
        assert result.sport == "ענפים נוספים"


class TestAIServiceFactory:
    """Test suite for factory functions get_ai_processor and get_ai_service."""

    def test_get_mock_processor_explicit(self):
        """Verify explicit mock provider returns MockAIProcessor."""
        proc = get_ai_processor(provider="mock")
        assert isinstance(proc, MockAIProcessor)

    def test_get_rule_based_processor_explicit(self):
        """Verify rule_based provider returns RuleBasedAIProcessor."""
        proc = get_ai_processor(provider="rule_based")
        assert isinstance(proc, RuleBasedAIProcessor)

    def test_get_gemini_processor_with_key(self):
        """Verify providing API key instantiates GeminiAIProcessor."""
        proc = get_ai_processor(
            api_key="test-api-key-12345",
            model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            provider="gemini",
        )
        assert isinstance(proc, GeminiAIProcessor)
        assert proc.api_key == "test-api-key-12345"
        assert proc.model == "gemini-2.5-flash"
        assert proc.fallback_model == "gemini-1.5-flash"

    def test_get_processor_test_env_fallback(self):
        """Verify test environment with no API key defaults to MockAIProcessor."""
        settings = Settings(ENVIRONMENT="testing", GEMINI_API_KEY="")
        proc = get_ai_processor(settings=settings)
        assert isinstance(proc, MockAIProcessor)

    def test_get_ai_service_instantiation(self):
        """Verify get_ai_service returns configured AIService."""
        svc = get_ai_service(provider="mock")
        assert isinstance(svc, AIService)
        assert isinstance(svc.processor, MockAIProcessor)
        assert svc.provider_name == "mock"


class TestAIServiceMethods:
    """Test suite for AIService high-level orchestration."""

    @pytest.mark.asyncio
    async def test_analyze_article_delegation(self):
        """Verify analyze_article delegates correctly to underlying processor."""
        mock_proc = MockAIProcessor()
        svc = AIService(processor=mock_proc, provider_name="mock")

        result = await svc.analyze_article(
            title="מכבי תל אביב החתימה שחקן חדש",
            subtitle="רכש חדש לצהובים לעונה הקרובה",
            body="השחקן הצטרף היום רשמית לאימונים.",
        )
        assert isinstance(result, ArticleAnalysisResult)
        assert mock_proc.call_count == 1

    @pytest.mark.asyncio
    async def test_analyze_batch_concurrent(self):
        """Verify analyze_batch processes articles concurrently."""
        mock_proc = MockAIProcessor(delay_seconds=0.01)
        svc = AIService(processor=mock_proc, provider_name="mock")

        articles = [
            {"title": "מכבי חיפה ניצחה 1:0", "body": "שער ניצחון של דין דוד בסמי עופר."},
            {"title": "הפועל תל אביב הפסידה 80:75", "body": "משחק צמוד בהיכל שלמה."},
            {"title": "ג'וקוביץ' זכה בטורניר", "body": "ניצחון בשלוש מערכות בגמר."},
        ]

        results = await svc.analyze_batch(articles, concurrency=3)
        assert len(results) == 3
        assert mock_proc.call_count == 3
        assert results[0].sport == "כדורגל"
        assert results[1].sport == "כדורסל"
        assert results[2].sport == "טניס"

    def test_get_provider_info(self):
        """Verify provider metadata and diagnostic information."""
        mock_proc = MockAIProcessor()
        svc = AIService(processor=mock_proc, provider_name="mock")
        info = svc.get_provider_info()
        assert info["provider"] == "mock"
        assert info["processor_class"] == "MockAIProcessor"
        assert "call_count" in info

        gemini_proc = GeminiAIProcessor(api_key="key", model="gemini-2.5-flash")
        svc_gemini = AIService(processor=gemini_proc, provider_name="gemini")
        gemini_info = svc_gemini.get_provider_info()
        assert gemini_info["model"] == "gemini-2.5-flash"
        assert gemini_info["has_api_key"] is True


class TestGeminiAIProcessorResilience:
    """Test suite for GeminiAIProcessor error handling, fallback chains, and recovery."""

    @pytest.mark.asyncio
    async def test_gemini_without_api_key_falls_back_gracefully(self):
        """Verify that a GeminiAIProcessor without client/key falls back to rule-based without crashing."""
        proc = GeminiAIProcessor(api_key=None, client=None)
        result = await proc.analyze_article(
            title="מכבי חיפה גברה 0:3 על בני סכנין",
            body="ניצחון קל לירוקים משערים של דין דוד ודיא סבע.",
        )
        assert isinstance(result, ArticleAnalysisResult)
        assert result.sport == "כדורגל"
        assert "מכבי חיפה" in result.teams

    @pytest.mark.asyncio
    async def test_gemini_primary_success_parsed(self):
        """Verify successful response via response.parsed from google-genai SDK."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        expected = ArticleAnalysisResult(
            headline="מכבי חיפה ניצחה 0:3 את בני סכנין",
            subheadline="הירוקים שלטו במשחק והשיגו 3 נקודות.",
            sport="כדורגל",
            teams=["מכבי חיפה", "בני סכנין"],
            players=["דין דוד"],
            competition="ליגת העל בכדורגל",
            tags=["סיכום משחק"],
        )
        mock_response.parsed = expected
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        proc = GeminiAIProcessor(api_key="test-key", client=mock_client)
        result = await proc.analyze_article(title="מכבי חיפה מנצחת", body="גוף הכתבה")

        assert result == expected
        mock_client.aio.models.generate_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_gemini_primary_success_text_json(self):
        """Verify successful response when SDK returns JSON in response.text."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parsed = None
        mock_response.text = """```json
        {
            "headline": "מכבי תל אביב גברה על ריאל מדריד ביורוליג",
            "subheadline": "ניצחון מרשים בהיכל מנורה.",
            "sport": "כדורסל",
            "teams": ["מכבי תל אביב", "ריאל מדריד"],
            "players": ["עודד קטש"],
            "competition": "יורוליג",
            "tags": ["יורוליג", "סיכום משחק"]
        }
        ```"""
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        proc = GeminiAIProcessor(api_key="test-key", client=mock_client)
        result = await proc.analyze_article(title="ניצחון צהוב", body="גוף כתבה")

        assert result.headline == "מכבי תל אביב גברה על ריאל מדריד ביורוליג"
        assert result.sport == "כדורסל"
        assert "ריאל מדריד" in result.teams

    @pytest.mark.asyncio
    async def test_gemini_primary_fails_fallback_model_succeeds(self):
        """Verify that when primary model fails, fallback model is tried and succeeds."""
        mock_client = MagicMock()
        mock_fallback_response = MagicMock()
        expected = ArticleAnalysisResult(
            headline="הפועל באר שבע ניצחה 0:1 את מ.ס אשדוד",
            subheadline="שער מאוחר העניק ניצחון לאדומים.",
            sport="כדורגל",
            teams=["הפועל באר שבע", "מ.ס. אשדוד"],
            players=[],
            competition="ליגת העל בכדורגל",
            tags=["סיכום משחק"],
        )
        mock_fallback_response.parsed = expected

        # First call (primary) raises exception, second call (fallback model) succeeds
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=[
                RuntimeError("Primary model quota exhausted 429"),
                mock_fallback_response,
            ]
        )

        proc = GeminiAIProcessor(
            api_key="test-key",
            model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            client=mock_client,
        )
        result = await proc.analyze_article(title="הפועל באר שבע מנצחת", body="גוף כתבה")

        assert result == expected
        assert mock_client.aio.models.generate_content.call_count == 2

    @pytest.mark.asyncio
    async def test_gemini_all_models_fail_uses_rule_based_fallback(self):
        """Verify that when both Gemini models fail, rule-based fallback succeeds without crashing."""
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("Google GenAI 503 Service Unavailable")
        )

        proc = GeminiAIProcessor(
            api_key="test-key",
            model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            client=mock_client,
            allow_fallback=True,
        )
        title = "בלעדי: דן ביטון סיכם בהפועל באר שבע"
        body = "הקשר יחתום לשלוש שנים תחת המאמן רן קוז'וך."

        result = await proc.analyze_article(title=title, body=body)

        assert isinstance(result, ArticleAnalysisResult)
        assert "בלעדי:" not in result.headline
        assert result.sport == "כדורגל"
        assert "הפועל באר שבע" in result.teams
        assert "העברות" in result.tags

    @pytest.mark.asyncio
    async def test_gemini_all_models_fail_disallow_fallback_raises(self):
        """Verify that when allow_fallback=False and models fail, an exception is raised."""
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("Google GenAI 503 Service Unavailable")
        )

        proc = GeminiAIProcessor(
            api_key="test-key",
            model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            client=mock_client,
            allow_fallback=False,
        )

        with pytest.raises(RuntimeError, match="Gemini AI processing failed"):
            await proc.analyze_article(title="כותרת", body="גוף")

    @pytest.mark.asyncio
    async def test_set_processor_dynamic_switch(self):
        """Verify dynamic processor switching in AIService."""
        mock_proc1 = MockAIProcessor()
        svc = AIService(processor=mock_proc1)
        assert svc.provider_name == "custom"

        mock_proc2 = MockAIProcessor()
        svc.set_processor(mock_proc2, provider_name="mock_v2")
        assert svc.processor is mock_proc2
        assert svc.provider_name == "mock_v2"

        rule_proc = RuleBasedAIProcessor()
        svc.set_processor(rule_proc)
        assert svc.provider_name == "rule_based"

    @pytest.mark.asyncio
    async def test_analyze_batch_empty_list(self):
        """Verify analyze_batch handles empty list gracefully."""
        mock_proc = MockAIProcessor()
        svc = AIService(processor=mock_proc, provider_name="mock")
        results = await svc.analyze_batch([])
        assert results == []
        assert mock_proc.call_count == 0
