"""Schemas package re-exporting all Pydantic request, response, and filter models."""

from fan_zone.schemas.source import (
    SourceBase,
    SourceCreate,
    SourceUpdate,
    SourceRead,
    SourceSummarySchema,
    SourceStatSchema,
)
from fan_zone.schemas.media import (
    MediaBase,
    MediaCreate,
    MediaRead,
    MediaSchema,
)
from fan_zone.schemas.tag import (
    TagBase,
    TagCreate,
    TagRead,
    TagSchema,
)
from fan_zone.schemas.article import (
    ArticleBase,
    ArticleCreate,
    ArticleUpdate,
    ArticleSummarySchema,
    ArticleDetailSchema,
    ArticleFilter,
    PaginatedArticleResponse,
)
from fan_zone.schemas.ingest import (
    IngestTriggerRequest,
    IngestTriggerResponse,
    IngestionRunStats,
)
from fan_zone.schemas.health import (
    HealthResponse,
    StatsResponse,
)

__all__ = [
    "SourceBase",
    "SourceCreate",
    "SourceUpdate",
    "SourceRead",
    "SourceSummarySchema",
    "SourceStatSchema",
    "MediaBase",
    "MediaCreate",
    "MediaRead",
    "MediaSchema",
    "TagBase",
    "TagCreate",
    "TagRead",
    "TagSchema",
    "ArticleBase",
    "ArticleCreate",
    "ArticleUpdate",
    "ArticleSummarySchema",
    "ArticleDetailSchema",
    "ArticleFilter",
    "PaginatedArticleResponse",
    "IngestTriggerRequest",
    "IngestTriggerResponse",
    "IngestionRunStats",
    "HealthResponse",
    "StatsResponse",
]
