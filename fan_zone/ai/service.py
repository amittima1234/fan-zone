"""Unified AI Service and processor factory for Fan Zone sports ingestion."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fan_zone.ai.base import ArticleAnalysisResult, BaseAIProcessor
from fan_zone.ai.fallback import RuleBasedAIProcessor
from fan_zone.ai.gemini_client import GeminiAIProcessor
from fan_zone.ai.mock import MockAIProcessor
from fan_zone.config import Settings, get_settings

logger = logging.getLogger(__name__)


class AIService:
    """High-level AI domain service coordinating article analysis and batch operations."""

    def __init__(self, processor: BaseAIProcessor, provider_name: str = "custom") -> None:
        self.processor = processor
        self.provider_name = provider_name

    def set_processor(self, processor: BaseAIProcessor, provider_name: Optional[str] = None) -> None:
        """Dynamically replace the underlying AI processor."""
        self.processor = processor
        if provider_name is not None:
            self.provider_name = provider_name
        elif isinstance(processor, MockAIProcessor):
            self.provider_name = "mock"
        elif isinstance(processor, GeminiAIProcessor):
            self.provider_name = "gemini"
        elif isinstance(processor, RuleBasedAIProcessor):
            self.provider_name = "rule_based"

    async def analyze_article(
        self,
        title: str,
        subtitle: Optional[str] = None,
        body: str = "",
    ) -> ArticleAnalysisResult:
        """Analyze a single sports article and extract non-clickbait headlines and tags."""
        return await self.processor.analyze_article(title=title, subtitle=subtitle, body=body)

    async def analyze_batch(
        self,
        articles: List[Dict[str, Any]],
        concurrency: int = 4,
    ) -> List[ArticleAnalysisResult]:
        """Analyze multiple articles concurrently with bounded parallelism.
        
        Args:
            articles: List of dicts containing keys: 'title', optional 'subtitle', 'body'.
            concurrency: Maximum number of parallel tasks.
            
        Returns:
            List of ArticleAnalysisResult corresponding to input articles.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _process_single(item: Dict[str, Any]) -> ArticleAnalysisResult:
            async with semaphore:
                return await self.analyze_article(
                    title=item.get("title") or item.get("original_title") or "",
                    subtitle=item.get("subtitle") or item.get("original_subtitle"),
                    body=item.get("body") or item.get("cleaned_body") or "",
                )

        tasks = [_process_single(item) for item in articles]
        return await asyncio.gather(*tasks)

    def get_provider_info(self) -> Dict[str, Any]:
        """Return diagnostic info about the active AI processor."""
        info: Dict[str, Any] = {
            "provider": self.provider_name,
            "processor_class": self.processor.__class__.__name__,
        }
        if isinstance(self.processor, GeminiAIProcessor):
            info.update({
                "model": self.processor.model,
                "fallback_model": self.processor.fallback_model,
                "temperature": self.processor.temperature,
                "timeout_seconds": self.processor.timeout_seconds,
                "has_api_key": bool(self.processor.api_key),
            })
        elif isinstance(self.processor, MockAIProcessor):
            info.update({
                "call_count": self.processor.call_count,
                "simulate_failure": self.processor.simulate_failure,
            })
        return info


def get_ai_processor(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    provider: Optional[str] = None,
    use_mock: Optional[bool] = None,
    settings: Optional[Settings] = None,
) -> BaseAIProcessor:
    """Factory function creating the appropriate AI processor based on config or params."""
    cfg = settings or get_settings()

    resolved_api_key = api_key if api_key is not None else cfg.GEMINI_API_KEY
    resolved_model = model or cfg.GEMINI_MODEL or "gemini-2.5-flash"
    resolved_fallback_model = fallback_model or "gemini-1.5-flash"
    resolved_use_mock = use_mock if use_mock is not None else cfg.USE_MOCK_AI

    if provider == "mock" or resolved_use_mock:
        logger.info("Instantiating MockAIProcessor for testing/mock environment.")
        return MockAIProcessor()

    if provider in ("rule_based", "fallback"):
        logger.info("Instantiating RuleBasedAIProcessor.")
        return RuleBasedAIProcessor()

    if resolved_api_key:
        logger.info(f"Instantiating GeminiAIProcessor (model={resolved_model}, fallback={resolved_fallback_model}).")
        return GeminiAIProcessor(
            api_key=resolved_api_key,
            model=resolved_model,
            fallback_model=resolved_fallback_model,
        )

    # When no API key is provided and provider is gemini, default to MockAIProcessor in test or RuleBased
    if cfg.is_testing:
        logger.info("No Gemini API key in test environment: defaulting to MockAIProcessor.")
        return MockAIProcessor()

    logger.info("No Gemini API key provided: defaulting to RuleBasedAIProcessor.")
    return RuleBasedAIProcessor()


def get_ai_service(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    use_mock: Optional[bool] = None,
    settings: Optional[Settings] = None,
) -> AIService:
    """Factory function returning a configured AIService."""
    processor = get_ai_processor(
        api_key=api_key,
        model=model,
        provider=provider,
        use_mock=use_mock,
        settings=settings,
    )
    provider_name = provider or ("mock" if isinstance(processor, MockAIProcessor) else "gemini")
    return AIService(processor=processor, provider_name=provider_name)
