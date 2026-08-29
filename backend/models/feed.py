"""SQLAlchemy 2.0 ORM models for Fan Zone sports articles and enrichment records."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
)
from db.session import Base


def utc_now() -> datetime:
    """Return current timestamp in UTC timezone."""
    return datetime.now(timezone.utc)


class ArticleModel(Base):
    """SQLAlchemy ORM model representing an enriched sports news article."""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), unique=True, index=True, nullable=False)
    publisher = Column(String(50), index=True, nullable=False)
    published_at = Column(DateTime(timezone=True), index=True, nullable=False)
    raw_body = Column(Text, nullable=False)

    # AI-Enriched Fields
    micro_summary = Column(Text, nullable=False)
    tags = Column(JSON, nullable=False, default=list)
    tone = Column(String(20), index=True, nullable=False)
    context_label = Column(String(50), index=True, nullable=False)

    # Metadata & Media
    category = Column(String(100), nullable=True)
    author = Column(String(100), nullable=True)
    image_url = Column(String(1000), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    def __repr__(self) -> str:
        title_snippet = (self.title[:30] + "...") if self.title and len(self.title) > 30 else self.title
        return f"<ArticleModel(id={self.id}, publisher='{self.publisher}', title='{title_snippet}')>"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize model instance to a dictionary representation."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "publisher": self.publisher,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "raw_body": self.raw_body,
            "micro_summary": self.micro_summary,
            "tags": self.tags if self.tags is not None else [],
            "tone": self.tone,
            "context_label": self.context_label,
            "category": self.category,
            "author": self.author,
            "image_url": self.image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
