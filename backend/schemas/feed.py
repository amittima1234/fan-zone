"""Pydantic schemas and contracts for Fan Zone sports feed ingestion and API layer."""

from datetime import datetime, timezone
from enum import Enum
import html
import re
from typing import Any, List, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToneEnum(str, Enum):
    """Journalistic tone classification for sports news articles."""

    OBJECTIVE = "objective"
    HYPE = "hype"
    CRITICAL = "critical"


class PublisherEnum(str, Enum):
    """Standardized publisher identifiers for Israeli sports portals."""

    SPORT5 = "sport5"
    YNET = "ynet"
    ONE = "one"
    WALLA = "walla"
    ISRAEL_HAYOM = "israel_hayom"
    SPORT1 = "sport1"
    HAARETZ = "haaretz"
    OTHER = "other"


def strip_html_tags(text: str) -> str:
    """Strip HTML tags and unescape HTML entities, returning cleaned normalized text."""
    if not text:
        return ""
    # Strip script and style tags completely
    text_clean = re.sub(r"<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Strip all remaining HTML tags
    text_clean = re.sub(r"<[^>]+>", " ", text_clean)
    # Unescape HTML entities
    text_clean = html.unescape(text_clean)
    # Normalize multiple whitespace characters into single space
    text_clean = re.sub(r"\s+", " ", text_clean)
    # Remove spaces preceding punctuation marks
    text_clean = re.sub(r"\s+([.,;:!?])", r"\1", text_clean)
    return text_clean.strip()


class RawArticlePayload(BaseModel):
    """Raw article payload ingested from RSS or web scrapers before AI enrichment."""

    title: str = Field(..., min_length=1, max_length=500, description="Article headline stripped of HTML")
    raw_body: str = Field(..., min_length=1, description="Extracted article body text, clean of HTML tags")
    url: str = Field(..., min_length=1, description="Canonical source URL of the article")
    publisher: str = Field(..., min_length=1, max_length=50, description="Publisher identifier (e.g. 'sport5', 'ynet')")
    published_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Article publication timestamp in UTC"
    )
    category: Optional[str] = Field(default=None, max_length=100, description="Source category/section (e.g. 'football', 'israeli-league')")
    author: Optional[str] = Field(default=None, max_length=100, description="Article author name if available")
    image_url: Optional[str] = Field(default=None, description="Optional metadata link to article cover image")

    @field_validator("title", "raw_body", mode="before")
    @classmethod
    def sanitize_text(cls, v: Any) -> str:
        if v is None:
            return ""
        val_str = str(v)
        cleaned = strip_html_tags(val_str)
        if not cleaned:
            raise ValueError("Field cannot be empty or contain only HTML tags/whitespace")
        return cleaned

    @field_validator("publisher", mode="before")
    @classmethod
    def normalize_publisher(cls, v: Any) -> str:
        if v is None:
            return ""
        val_str = str(v).strip().lower()
        return val_str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v_clean = v.strip()
        parsed = urlparse(v_clean)
        if parsed.scheme not in ("http", "https") or not bool(parsed.netloc):
            raise ValueError("URL must start with http:// or https:// and contain a valid host")
        return v_clean


class AIEnrichedCard(BaseModel):
    """Structured output returned by Gemini structured output enrichment service."""

    micro_summary: str = Field(
        ...,
        min_length=10,
        max_length=400,
        description="Single-sentence factual micro-summary (max 40 words) capturing the core news."
    )
    tags: List[str] = Field(
        ...,
        min_length=1,
        max_length=15,
        description="Entities mentioned in the article: teams, leagues, athletes, or sports."
    )
    tone: ToneEnum = Field(
        ...,
        description="Classified tone of the article: 'objective', 'hype', or 'critical'."
    )
    context_label: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Short journalistic context tag: e.g. 'Match Report', 'Transfer Rumor', 'Injury Update', 'Tactical Analysis'."
    )

    @field_validator("micro_summary")
    @classmethod
    def validate_word_count(cls, v: str) -> str:
        cleaned = v.strip()
        words = cleaned.split()
        if not words:
            raise ValueError("micro_summary cannot be empty")
        if len(words) > 40:
            raise ValueError(f"micro_summary exceeds word limit (got {len(words)} words, max 40 words)")
        return cleaned

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("At least one non-empty tag is required")
        cleaned = [t.strip() for t in v if isinstance(t, str) and t.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty tag is required")
        # Deduplicate preserving insertion order
        return list(dict.fromkeys(cleaned))

    @field_validator("context_label")
    @classmethod
    def clean_context_label(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2 or len(cleaned) > 50:
            raise ValueError("context_label must be between 2 and 50 characters")
        return cleaned


class UserPreferences(BaseModel):
    """User profile and filtering preferences for feed personalization."""

    followed_tags: List[str] = Field(
        default_factory=list,
        description="List of team, league, or sport tags followed by the user."
    )
    excluded_sources: List[str] = Field(
        default_factory=list,
        description="List of publisher IDs to exclude from user feed."
    )
    preferred_tones: Optional[List[ToneEnum]] = Field(
        default=None,
        description="Optional list of tones to include. If None, all tones are included."
    )
    language: Optional[str] = Field(
        default="he",
        max_length=10,
        description="Preferred language code (default 'he' for Hebrew feeds)."
    )

    @field_validator("followed_tags", "excluded_sources")
    @classmethod
    def clean_string_list(cls, v: List[str]) -> List[str]:
        if not v:
            return []
        cleaned = [item.strip() for item in v if isinstance(item, str) and item.strip()]
        return list(dict.fromkeys(cleaned))


class FeedItemResponse(BaseModel):
    """Complete enriched sports article response for API clients."""

    id: int = Field(..., description="Unique database record ID")
    title: str = Field(..., description="Article headline")
    url: str = Field(..., description="Source article URL")
    publisher: str = Field(..., description="Publisher name (e.g. 'sport5')")
    published_at: datetime = Field(..., description="Article publication timestamp")
    micro_summary: str = Field(..., description="AI-generated concise summary")
    tags: List[str] = Field(..., description="Associated team, league, and sport tags")
    tone: ToneEnum = Field(..., description="Article tone")
    context_label: str = Field(..., description="Article context label")
    category: Optional[str] = Field(default=None, description="Sport/Section category")
    author: Optional[str] = Field(default=None, description="Article author")
    created_at: datetime = Field(..., description="Record ingestion timestamp in DB")

    model_config = ConfigDict(from_attributes=True)


class PaginatedFeedResponse(BaseModel):
    """Standardized pagination wrapper for feed article lists."""

    items: List[FeedItemResponse] = Field(default_factory=list, description="List of enriched feed articles for the requested page")
    total: int = Field(..., ge=0, description="Total count of articles matching the filter criteria")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages available")
    has_next: bool = Field(..., description="True if a subsequent page exists")
    has_prev: bool = Field(..., description="True if a previous page exists")

    model_config = ConfigDict(from_attributes=True)


class HealthCheckResponse(BaseModel):
    """Service liveness and dependency readiness health status schema."""

    status: str = Field(..., description="Overall health status: 'healthy', 'degraded', or 'unhealthy'")
    app_name: str = Field(..., description="Application name")
    environment: str = Field(..., description="Deployment environment (development/production/test)")
    database: str = Field(..., description="Database connectivity status: 'connected', 'disconnected', 'error'")
    ai_mode: str = Field(..., description="AI enrichment mode: 'live_gemini' or 'mock'")
    scheduler: str = Field(..., description="Background scheduler status: 'enabled', 'disabled'")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of check"
    )

    model_config = ConfigDict(from_attributes=True)


class IngestionTriggerResponse(BaseModel):
    """Response schema for manual ingestion triggers."""

    status: str = Field(..., description="Trigger status: 'triggered', 'completed', or 'failed'")
    publisher: Optional[str] = Field(default=None, description="Target publisher or 'all'")
    articles_fetched: int = Field(default=0, ge=0, description="Number of raw articles fetched from RSS/HTML")
    articles_queued: int = Field(default=0, ge=0, description="Number of articles pushed to queue / processed")
    message: str = Field(..., description="Status description message")
    errors: Optional[List[str]] = Field(default=None, description="Any warning or error messages encountered during ingestion")

    model_config = ConfigDict(from_attributes=True)
