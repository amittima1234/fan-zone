"""Deterministic offline Mock AI processor for hermetic unit testing and CI/CD."""

import asyncio
from typing import Optional

from fan_zone.ai.base import ArticleAnalysisResult, BaseAIProcessor
from fan_zone.ai.fallback import fallback_article_analysis


class MockAIProcessor(BaseAIProcessor):
    """Hermetic mock AI processor requiring no API keys or internet connection.
    
    Provides deterministic responses based on heuristic analysis with configurable
    simulation flags for rate limits, timeouts, errors, and custom responses.
    """

    def __init__(
        self,
        simulate_failure: bool = False,
        simulate_rate_limit: bool = False,
        simulate_timeout: bool = False,
        simulate_invalid_response: bool = False,
        delay_seconds: float = 0.0,
        custom_response: Optional[ArticleAnalysisResult] = None,
    ) -> None:
        self.simulate_failure = simulate_failure
        self.simulate_rate_limit = simulate_rate_limit
        self.simulate_timeout = simulate_timeout
        self.simulate_invalid_response = simulate_invalid_response
        self.delay_seconds = delay_seconds
        self.custom_response = custom_response
        self.call_count: int = 0
        self.last_title: Optional[str] = None
        self.last_body: Optional[str] = None

    async def analyze_article(
        self,
        title: str,
        subtitle: Optional[str] = None,
        body: str = "",
    ) -> ArticleAnalysisResult:
        """Process article with simulated delay, error checking, and deterministic output."""
        self.call_count += 1
        self.last_title = title
        self.last_body = body

        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if self.simulate_rate_limit:
            raise RuntimeError("429 Resource Exhausted: Rate limit exceeded (simulated)")

        if self.simulate_timeout:
            raise TimeoutError("AI request timed out after 20.0s (simulated)")

        if self.simulate_failure:
            raise RuntimeError("AI processing backend error 503: Service Unavailable (simulated)")

        if self.simulate_invalid_response:
            # Return empty or invalid data that triggers downstream schema handling
            return ArticleAnalysisResult(
                headline="",
                subheadline="",
                sport="",
                teams=[],
                players=[],
                competition=None,
                tags=[],
            )

        if self.custom_response is not None:
            return self.custom_response

        # Return realistic, deterministic analysis via the fallback heuristic engine
        return fallback_article_analysis(title=title, subtitle=subtitle, body=body)

    def reset_stats(self) -> None:
        """Reset internal call metrics."""
        self.call_count = 0
        self.last_title = None
        self.last_body = None
