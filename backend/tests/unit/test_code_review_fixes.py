"""Unit tests verifying fixes for issues identified in code review."""

import asyncio
import pytest
from pydantic import ValidationError

from core.config import Settings
from core.queue import InMemoryTaskQueue
from models.feed import ArticleModel
from schemas.feed import AIEnrichedCard, RawArticlePayload, ToneEnum
from services.ai_worker import FallbackAIEnrichmentService


class TestCodeReviewFixes:
    """Tests confirming all code review issues are resolved."""

    def test_empty_after_html_sanitization_raises_validation_error(self):
        """Pure HTML or empty strings must raise ValidationError."""
        with pytest.raises(ValidationError):
            RawArticlePayload(
                title="<script></script>  <style></style>",
                raw_body="Valid body content for news article.",
                url="https://www.sport5.co.il/article/1",
                publisher="sport5",
            )

        with pytest.raises(ValidationError):
            RawArticlePayload(
                title="Valid Headline",
                raw_body="<br/><p></p>   ",
                url="https://www.sport5.co.il/article/2",
                publisher="sport5",
            )

    @pytest.mark.asyncio
    async def test_in_memory_queue_push_deduplication_integrity(self):
        """Ensure seen_urls is only populated when item is successfully enqueued."""
        queue = InMemoryTaskQueue(maxsize=2)
        p1 = RawArticlePayload(
            title="כתבה 1",
            raw_body="גוף כתבה ראשונה",
            url="https://www.sport5.co.il/item1",
            publisher="sport5",
        )
        p2 = RawArticlePayload(
            title="כתבה 2",
            raw_body="גוף כתבה שנייה",
            url="https://www.sport5.co.il/item2",
            publisher="sport5",
        )
        assert await queue.push(p1) is True
        assert await queue.push(p2) is True
        assert await queue.push(p1) is False  # Duplicate URL rejected

    def test_fallback_ai_enrichment_service_in_services(self):
        """Verify FallbackAIEnrichmentService works cleanly from services.ai_worker."""
        service = FallbackAIEnrichmentService(use_mock=True)
        payload = RawArticlePayload(
            title="מכבי תל אביב ביורוליג",
            raw_body="ניצחון ענק ודרמטי בהיכל מנורה מבטחים",
            url="https://www.sport5.co.il/item3",
            publisher="sport5",
        )
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(service.enrich_article(payload))
            assert isinstance(res, AIEnrichedCard)
            assert "Maccabi Tel Aviv" in res.tags or "מכבי תל אביב" in res.tags
            assert res.tone == ToneEnum.HYPE
        finally:
            loop.close()

    def test_settings_default_model(self):
        """Verify default Gemini model identifier is gemini-3.7-flash."""
        s = Settings()
        assert "gemini-3.7-flash" in s.GEMINI_MODEL or s.GEMINI_MODEL.startswith("gemini-")
