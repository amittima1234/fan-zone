"""Unit tests verifying retry behavior on 503 / overload errors in Gemini AI worker."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from schemas.feed import AIEnrichedCard, RawArticlePayload, ToneEnum
from services.ai_worker import (
    AIEnrichmentError,
    AIEnrichmentService,
    GeminiAIEnricher,
    MockAIEnricher,
    _is_transient_gemini_error,
)


class Mock503Error(Exception):
    """Custom exception simulating a 503 Service Unavailable / Overload error."""

    def __init__(self, message="503 Service Unavailable: The model is overloaded. Please try again later."):
        super().__init__(message)
        self.code = 503
        self.status_code = 503


class Mock400Error(Exception):
    """Custom exception simulating a non-transient 400 Bad Request error."""

    def __init__(self, message="400 Bad Request: Invalid argument supplied."):
        super().__init__(message)
        self.code = 400
        self.status_code = 400


class TestTransientErrorDetector:
    """Tests for _is_transient_gemini_error heuristic function."""

    def test_detects_503_code_and_message(self):
        assert _is_transient_gemini_error(Mock503Error()) is True
        assert _is_transient_gemini_error(Exception("503 Server Error: Model overloaded")) is True
        assert _is_transient_gemini_error(Exception("ResourceExhausted: rate limit exceeded (429)")) is True
        assert _is_transient_gemini_error(asyncio.TimeoutError()) is True
        assert _is_transient_gemini_error(TimeoutError()) is True

    def test_rejects_non_transient_errors(self):
        assert _is_transient_gemini_error(Mock400Error()) is False
        assert _is_transient_gemini_error(ValueError("Invalid response schema format")) is False
        assert _is_transient_gemini_error(Exception("Authentication failed: API key expired")) is False


class TestGemini503RetryMechanism:
    """Tests verifying retry loop and backoff in GeminiAIEnricher."""

    @pytest.fixture
    def sample_article(self) -> RawArticlePayload:
        return RawArticlePayload(
            title="מכבי תל אביב ניצחה את פנאתינייקוס",
            raw_body="ניצחון ענק ודרמטי ביורוליג בהיכל מנורה מבטחים.",
            url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=99901",
            publisher="sport5",
        )

    @pytest.fixture
    def mock_successful_card(self) -> AIEnrichedCard:
        return AIEnrichedCard(
            micro_summary="Maccabi Tel Aviv secured a dramatic victory over Panathinaikos.",
            tags=["Maccabi Tel Aviv", "Panathinaikos", "Euroleague"],
            tone=ToneEnum.HYPE,
            context_label="Match Report",
        )

    @pytest.mark.asyncio
    async def test_retry_on_503_succeeds_on_second_attempt(
        self,
        sample_article: RawArticlePayload,
        mock_successful_card: AIEnrichedCard,
    ):
        """Verify that a 503 error on first call triggers sleep and succeeds on 2nd call."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parsed = mock_successful_card

        mock_generate = AsyncMock(
            side_effect=[
                Mock503Error("503 Service Unavailable: Model overloaded"),
                mock_response,
            ]
        )
        mock_client.aio.models.generate_content = mock_generate

        enricher = GeminiAIEnricher(
            api_key="test-api-key",
            client=mock_client,
            max_retries=2,
            initial_delay=0.01,  # Fast delay for test execution
            backoff_factor=1.5,
        )

        result = await enricher.enrich_article(sample_article)
        assert result == mock_successful_card
        assert mock_generate.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises_error_after_max_retries(
        self,
        sample_article: RawArticlePayload,
    ):
        """Verify that persistent 503 error exhausts retries and raises AIEnrichmentError."""
        mock_client = MagicMock()
        mock_generate = AsyncMock(side_effect=Mock503Error("503 Model Overloaded"))
        mock_client.aio.models.generate_content = mock_generate

        enricher = GeminiAIEnricher(
            api_key="test-api-key",
            client=mock_client,
            max_retries=2,
            initial_delay=0.01,
        )

        with pytest.raises(AIEnrichmentError) as exc_info:
            await enricher.enrich_article(sample_article)

        assert "503" in str(exc_info.value) or "overload" in str(exc_info.value).lower()
        # initial call (1) + 2 retries = 3 calls total
        assert mock_generate.call_count == 3

    @pytest.mark.asyncio
    async def test_non_transient_error_fails_immediately_without_retry(
        self,
        sample_article: RawArticlePayload,
    ):
        """Verify that non-503 permanent errors (like 400 Bad Request) do not waste time retrying."""
        mock_client = MagicMock()
        mock_generate = AsyncMock(side_effect=Mock400Error("400 Bad Request: Invalid input"))
        mock_client.aio.models.generate_content = mock_generate

        enricher = GeminiAIEnricher(
            api_key="test-api-key",
            client=mock_client,
            max_retries=3,
            initial_delay=0.01,
        )

        with pytest.raises(AIEnrichmentError):
            await enricher.enrich_article(sample_article)

        # Fails immediately on 1st call without retries
        assert mock_generate.call_count == 1

    @pytest.mark.asyncio
    async def test_ai_enrichment_service_falls_back_to_mock_after_503_exhaustion(
        self,
        sample_article: RawArticlePayload,
    ):
        """Verify that AIEnrichmentService gracefully degrades to MockAIEnricher when Gemini 503 persists."""
        mock_client = MagicMock()
        mock_generate = AsyncMock(side_effect=Mock503Error("503 Overload"))
        mock_client.aio.models.generate_content = mock_generate

        gemini_enricher = GeminiAIEnricher(
            api_key="test-api-key",
            client=mock_client,
            max_retries=1,
            initial_delay=0.01,
        )

        service = AIEnrichmentService(enricher=gemini_enricher)
        result = await service.enrich_article(sample_article)

        # Fallback produced a valid card
        assert isinstance(result, AIEnrichedCard)
        assert len(result.tags) > 0
        assert mock_generate.call_count == 2
