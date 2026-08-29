"""Gemini AI processor using google-genai SDK with structured output and retry resilience."""

import asyncio
import json
import logging
import re
from typing import Optional

from google import genai
from google.genai import errors, types
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from fan_zone.ai.base import ArticleAnalysisResult, BaseAIProcessor
from fan_zone.ai.fallback import fallback_article_analysis
from fan_zone.ai.prompts import SYSTEM_INSTRUCTION, build_article_prompt

logger = logging.getLogger(__name__)

# Exceptions eligible for retry
RETRYABLE_EXCEPTIONS = (
    errors.APIError,
    errors.ServerError,
    TimeoutError,
    asyncio.TimeoutError,
    ConnectionError,
)


class GeminiAIProcessor(BaseAIProcessor):
    """Google Gemini AI processor for Hebrew sports article analysis.
    
    Features:
    - Structured JSON generation directly into ArticleAnalysisResult Pydantic schema.
    - Tenacity exponential backoff for HTTP 429 rate limits, 503 unavailable, and network timeouts.
    - Two-tier model fallback: primary model (default: gemini-2.5-flash) -> fallback model (gemini-1.5-flash).
    - Graceful heuristic rule-based fallback if all Gemini API endpoints are unreachable.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        fallback_model: str = "gemini-1.5-flash",
        temperature: float = 0.2,
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        allow_fallback: bool = True,
        client: Optional[genai.Client] = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.allow_fallback = allow_fallback

        if client is not None:
            self.client = client
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None

    @retry(
        wait=wait_random_exponential(min=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        reraise=True,
    )
    async def _generate_structured_content(
        self,
        model_name: str,
        prompt: str,
    ) -> ArticleAnalysisResult:
        """Call Gemini API asynchronously with structured JSON schema enforcement."""
        if self.client is None:
            raise RuntimeError("Gemini Client is not initialized (missing API key).")

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ArticleAnalysisResult,
            temperature=self.temperature,
            system_instruction=SYSTEM_INSTRUCTION,
        )

        response = await self.client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )

        # 1. Direct parsed Pydantic object from SDK
        if hasattr(response, "parsed") and response.parsed:
            if isinstance(response.parsed, ArticleAnalysisResult):
                return response.parsed
            if isinstance(response.parsed, dict):
                return ArticleAnalysisResult.model_validate(response.parsed)

        # 2. Text response JSON parsing
        raw_text = getattr(response, "text", "") or ""
        raw_text = raw_text.strip()

        # Strip markdown code blocks if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
            raw_text = re.sub(r"\s*```$", "", raw_text)

        parsed_json = json.loads(raw_text)
        return ArticleAnalysisResult.model_validate(parsed_json)

    async def _execute_with_timeout(
        self,
        model_name: str,
        prompt: str,
    ) -> ArticleAnalysisResult:
        """Execute Gemini call wrapped with strict timeout protection."""
        return await asyncio.wait_for(
            self._generate_structured_content(model_name, prompt),
            timeout=self.timeout_seconds,
        )

    async def analyze_article(
        self,
        title: str,
        subtitle: Optional[str] = None,
        body: str = "",
    ) -> ArticleAnalysisResult:
        """Process article with primary Gemini model, fallback model, and heuristic fallback.
        
        Args:
            title: Raw original article headline.
            subtitle: Optional raw article subtitle.
            body: Article text body or paragraphs.
            
        Returns:
            ArticleAnalysisResult with non-clickbait headline and entity tags.
        """
        # If client not initialized or no API key, use rule-based fallback immediately
        if not self.client:
            logger.info("No Gemini API key configured. Using heuristic fallback engine.")
            return fallback_article_analysis(title=title, subtitle=subtitle, body=body)

        prompt = build_article_prompt(title=title, subtitle=subtitle, body=body)

        # Attempt 1: Primary Model (e.g. gemini-2.5-flash)
        try:
            return await self._execute_with_timeout(self.model, prompt)
        except Exception as e:
            logger.warning(
                f"Primary Gemini model '{self.model}' failed for article '{title[:40]}...': {e}. "
                f"Attempting fallback model '{self.fallback_model}'..."
            )

        # Attempt 2: Fallback Model (e.g. gemini-1.5-flash)
        if self.fallback_model and self.fallback_model != self.model:
            try:
                return await self._execute_with_timeout(self.fallback_model, prompt)
            except Exception as e:
                logger.warning(
                    f"Fallback Gemini model '{self.fallback_model}' failed for article '{title[:40]}...': {e}."
                )

        # Attempt 3: Heuristic Rule-based Fallback (Zero-crash guarantee)
        if self.allow_fallback:
            logger.info("All Gemini LLM calls exhausted. Using rule-based heuristic fallback.")
            return fallback_article_analysis(title=title, subtitle=subtitle, body=body)

        raise RuntimeError(f"Gemini AI processing failed for article '{title}' on both primary and fallback models.")
