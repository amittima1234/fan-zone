"""Pydantic schemas for sports entity tags."""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from fan_zone.models.enums import TagType


class TagBase(BaseModel):
    name: str = Field(..., description="Hebrew entity or topic name")
    tag_type: TagType = Field(default=TagType.GENERAL, description="Entity type: sport, team, player, competition, topic, general")


class TagCreate(TagBase):
    slug: Optional[str] = None


class TagRead(TagBase):
    id: int
    slug: str
    article_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Alias for response schemas
TagSchema = TagRead
