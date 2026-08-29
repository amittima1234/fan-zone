"""Pydantic schemas for news sources."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class SourceBase(BaseModel):
    name: str = Field(..., description="Unique machine identifier for the source (e.g. sport5, one)")
    display_name: str = Field(..., description="Human-friendly display name (e.g. Sport5, ONE)")
    base_url: str = Field(..., description="Base website URL")
    feed_url: Optional[str] = Field(None, description="RSS/Atom feed URL if available")
    is_active: bool = Field(True, description="Whether this source is currently being polled")
    poll_interval_seconds: int = Field(300, description="Polling interval in seconds")


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    display_name: Optional[str] = None
    base_url: Optional[str] = None
    feed_url: Optional[str] = None
    is_active: Optional[bool] = None
    poll_interval_seconds: Optional[int] = None


class SourceRead(SourceBase):
    id: int
    code: Optional[str] = None
    last_polled_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    error_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceSummarySchema(BaseModel):
    id: int
    name: str
    display_name: str
    code: Optional[str] = None
    base_url: str

    model_config = ConfigDict(from_attributes=True)


class SourceStatSchema(BaseModel):
    code: str
    name: str
    display_name: Optional[str] = None
    total_articles: int = 0
    last_polled_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    error_count: int = 0

    model_config = ConfigDict(from_attributes=True)
