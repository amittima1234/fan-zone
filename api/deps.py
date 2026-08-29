"""FastAPI dependency injection utilities for Fan Zone application.

Provides dependencies for database sessions, configuration settings,
article repository instances, and AI enrichment services.
"""

from typing import AsyncGenerator, Union
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from db.repository import ArticleRepository
from db.session import get_db
from schemas.feed import AIEnrichedCard, RawArticlePayload, ToneEnum
from services.ai_worker import AIEnrichmentService, FallbackAIEnrichmentService


def get_article_repository(
    session: AsyncSession = Depends(get_db),
) -> ArticleRepository:
    """FastAPI dependency yielding an ArticleRepository bound to the current session."""
    return ArticleRepository(session)


def get_ai_service(
    settings: Settings = Depends(get_settings),
) -> Union[AIEnrichmentService, FallbackAIEnrichmentService]:
    """FastAPI dependency yielding the configured AI enrichment service."""
    try:
        return AIEnrichmentService(use_mock=settings.is_mock_ai)
    except Exception:
        return FallbackAIEnrichmentService(use_mock=True)
