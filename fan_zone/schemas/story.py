"""Pydantic schemas for synthesized, copyright-safe sports stories and personalized feed."""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class StoryCitation(BaseModel):
    """Outbound publisher attribution and citation for copyright compliance."""
    article_id: Optional[int] = None
    source_name: str = Field(..., description="Publisher name (e.g. Sport5, ONE, Walla)")
    source_code: Optional[str] = Field(None, description="Publisher machine code")
    original_title: str = Field(..., description="Publisher original headline")
    url: str = Field(..., description="Direct link to source article")
    published_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class StorySummarySchema(BaseModel):
    """Synthesized brief sports story with entity tags and source citations."""
    id: int
    title: str = Field(..., description="Objective, non-clickbait Hebrew synthesis headline")
    summary: str = Field(..., description="Synthesized multi-source brief covering the event")
    sport: Optional[str] = None
    competition: Optional[str] = None
    teams: List[str] = Field(default_factory=list)
    players: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    lead_image_url: Optional[str] = None
    lead_image_caption: Optional[str] = None
    lead_image_credit: Optional[str] = None
    citations: List[StoryCitation] = Field(default_factory=list)
    article_count: int = 1
    published_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class StoryDetailSchema(StorySummarySchema):
    """Full detail view for a synthesized story."""
    pass


class PaginatedStoryResponse(BaseModel):
    """Paginated collection of synthesized stories or fan feed."""
    items: List[StorySummarySchema]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class SynthesizeResponse(BaseModel):
    """Response returned when manual multi-source synthesis is executed."""
    status: str
    stories_created: int = 0
    stories_updated: int = 0
    message: str
