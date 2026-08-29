"""Story model representing synthesized, copyright-safe sports stories."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy import DateTime, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from fan_zone.db.base import Base, TimestampMixin


class Story(Base, TimestampMixin):
    """Represents a synthesized multi-source sports story with full source citations."""
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sport: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    competition: Mapped[Optional[str]] = mapped_column(String(150), index=True, nullable=True)

    # Structured entity arrays
    teams_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    players_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    tags_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # Lead media (optional)
    lead_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lead_image_caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lead_image_credit: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Source Citations array: [{source_name, source_code, original_title, url, published_at, article_id}]
    citations_json: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    article_count: Mapped[int] = mapped_column(default=1, nullable=False)

    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        index=True,
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_stories_sport_published", "sport", "published_at"),
        Index("ix_stories_competition_published", "competition", "published_at"),
    )

    @property
    def teams(self) -> List[str]:
        return self.teams_json

    @property
    def players(self) -> List[str]:
        return self.players_json

    @property
    def tags(self) -> List[str]:
        return self.tags_json

    @property
    def citations(self) -> List[Dict[str, Any]]:
        return self.citations_json
