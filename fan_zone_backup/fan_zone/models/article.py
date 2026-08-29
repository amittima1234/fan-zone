"""Article model representing stored news articles."""

from typing import TYPE_CHECKING, List, Optional
from datetime import datetime
from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fan_zone.db.base import Base, TimestampMixin
from fan_zone.models.enums import IngestionStatus
from fan_zone.models.media import ArticleMedia

if TYPE_CHECKING:
    from fan_zone.models.source import Source
    from fan_zone.models.tag import ArticleTag, Tag


class Article(Base, TimestampMixin):
    """Represents an ingested sports news article with AI enrichment and metadata."""
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Deduplication Columns (Indexed and unique per source)
    canonical_url: Mapped[str] = mapped_column(String(1024), index=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # Original Content
    original_title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        index=True,
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
    )
    raw_paragraphs: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    cleaned_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # AI Enrichment Output
    ai_headline: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ai_subheadline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Primary Categorization
    sport: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    competition: Mapped[Optional[str]] = mapped_column(String(150), index=True, nullable=True)

    # Denormalized JSON arrays for rapid querying and serialization
    teams_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    players_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    tags_json: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    # Processing Status
    ingestion_status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, native_enum=False),
        default=IngestionStatus.PENDING,
        index=True,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    source: Mapped["Source"] = relationship("Source", back_populates="articles", lazy="selectin")
    media: Mapped[List["ArticleMedia"]] = relationship(
        "ArticleMedia",
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="ArticleMedia.position_index",
        lazy="selectin",
    )
    article_tags: Mapped[List["ArticleTag"]] = relationship(
        "ArticleTag",
        back_populates="article",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="article_tags",
        back_populates="articles",
        viewonly=True,
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_articles_source_canonical_url", "source_id", "canonical_url", unique=True),
        Index("ix_articles_source_content_hash", "source_id", "content_hash", unique=True),
        Index("ix_articles_sport_published", "sport", "published_at"),
        Index("ix_articles_source_published", "source_id", "published_at"),
        Index("ix_articles_status_published", "ingestion_status", "published_at"),
    )

    @property
    def paragraphs(self) -> List[str]:
        """Alias for raw_paragraphs."""
        return self.raw_paragraphs

    @paragraphs.setter
    def paragraphs(self, value: List[str]) -> None:
        self.raw_paragraphs = value

    @property
    def original_subheadline(self) -> Optional[str]:
        """Alias for original_subtitle."""
        return self.original_subtitle

    @original_subheadline.setter
    def original_subheadline(self, value: Optional[str]) -> None:
        self.original_subtitle = value

    @property
    def teams(self) -> List[str]:
        """Alias for teams_json."""
        return self.teams_json

    @teams.setter
    def teams(self, value: List[str]) -> None:
        self.teams_json = value

    @property
    def players(self) -> List[str]:
        """Alias for players_json."""
        return self.players_json

    @players.setter
    def players(self, value: List[str]) -> None:
        self.players_json = value

    @property
    def lead_image(self) -> Optional["ArticleMedia"]:
        """Returns the primary lead media or first media item."""
        if not self.media:
            return None
        for m in self.media:
            if m.is_primary or getattr(m, "is_lead", False):
                return m
        return self.media[0]

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, title='{self.original_title[:30]}...', status='{self.ingestion_status}')>"


__all__ = ["Article", "ArticleMedia"]
