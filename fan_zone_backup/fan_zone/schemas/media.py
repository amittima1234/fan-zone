"""Pydantic schemas for media items attached to articles."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from fan_zone.models.enums import MediaType


class MediaBase(BaseModel):
    url: str = Field(..., description="Absolute URL to media resource")
    media_type: MediaType = Field(default=MediaType.IMAGE, description="Type of media")
    caption: Optional[str] = Field(None, description="Image/video caption in Hebrew or English")
    credit: Optional[str] = Field(None, description="Photographer or agency credit")
    is_primary: bool = Field(default=False, description="Whether this is the primary lead media")
    position_index: int = Field(default=0, description="Ordering index in article body")


class MediaCreate(MediaBase):
    is_lead: Optional[bool] = None


class MediaRead(MediaBase):
    id: int
    article_id: Optional[int] = None
    is_lead: bool = False
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Alias for response schemas
MediaSchema = MediaRead
