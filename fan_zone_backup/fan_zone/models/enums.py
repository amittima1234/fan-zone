"""Domain enums for fan-zone models and schemas."""

import enum


class IngestionStatus(str, enum.Enum):
    """Status of an article in the ingestion & AI enrichment pipeline."""
    PENDING = "PENDING"
    AI_PROCESSED = "AI_PROCESSED"
    AI_FALLBACK = "AI_FALLBACK"
    FAILED = "FAILED"


class TagType(str, enum.Enum):
    """Categorization type of an entity tag."""
    SPORT = "sport"
    TEAM = "team"
    PLAYER = "player"
    COMPETITION = "competition"
    TOPIC = "topic"
    GENERAL = "general"


class MediaType(str, enum.Enum):
    """Type of media attached to an article."""
    IMAGE = "image"
    VIDEO = "video"
