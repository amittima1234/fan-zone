"""AI tagging and non-clickbait engine package for Fan Zone."""

from fan_zone.ai.base import ArticleAnalysisResult, BaseAIProcessor
from fan_zone.ai.fallback import RuleBasedAIProcessor, fallback_article_analysis
from fan_zone.ai.gemini_client import GeminiAIProcessor
from fan_zone.ai.mock import MockAIProcessor
from fan_zone.ai.prompts import (
    FEW_SHOT_EXAMPLES,
    SYSTEM_INSTRUCTION,
    build_article_prompt,
    get_few_shot_examples,
    get_system_instruction,
)
from fan_zone.ai.service import AIService, get_ai_processor, get_ai_service

__all__ = [
    "ArticleAnalysisResult",
    "BaseAIProcessor",
    "GeminiAIProcessor",
    "RuleBasedAIProcessor",
    "MockAIProcessor",
    "AIService",
    "get_ai_processor",
    "get_ai_service",
    "fallback_article_analysis",
    "SYSTEM_INSTRUCTION",
    "FEW_SHOT_EXAMPLES",
    "get_system_instruction",
    "get_few_shot_examples",
    "build_article_prompt",
]
