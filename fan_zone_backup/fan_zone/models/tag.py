"""Tag and ArticleTag models for entity categorization."""

from typing import TYPE_CHECKING, List
from datetime import datetime, timezone
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fan_zone.db.base import Base, utc_now
from fan_zone.models.enums import TagType

if TYPE_CHECKING:
    from fan_zone.models.article import Article


class Tag(Base):
    """Normalized sports entity tag (team, player, sport, competition, topic)."""
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    tag_type: Mapped[TagType] = mapped_column(
        Enum(TagType, native_enum=False),
        default=TagType.GENERAL,
        index=True,
        nullable=False,
    )
    article_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    articles: Mapped[List["Article"]] = relationship(
        "Article",
        secondary="article_tags",
        back_populates="tags",
        lazy="selectin",
        viewonly=True,
    )
    article_tags: Mapped[List["ArticleTag"]] = relationship(
        "ArticleTag",
        back_populates="tag",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}', tag_type='{self.tag_type}', count={self.article_count})>"


class ArticleTag(Base):
    """Many-to-many junction between articles and tags."""
    __tablename__ = "article_tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("article_id", "tag_id", name="uq_article_tag"),
    )

    # Relationships
    article: Mapped["Article"] = relationship("Article", back_populates="article_tags", lazy="selectin")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="article_tags", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ArticleTag(article_id={self.article_id}, tag_id={self.tag_id})>"
