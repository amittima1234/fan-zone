"""ArticleMedia model representing images and videos attached to articles."""

from typing import TYPE_CHECKING, Optional
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fan_zone.db.base import Base, utc_now
from fan_zone.models.enums import MediaType

if TYPE_CHECKING:
    from fan_zone.models.article import Article


class ArticleMedia(Base):
    """Represents a media item (image/video) associated with an article."""
    __tablename__ = "article_media"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, native_enum=False),
        default=MediaType.IMAGE,
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credit: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    article: Mapped["Article"] = relationship("Article", back_populates="media", lazy="selectin")

    @property
    def is_lead(self) -> bool:
        """Alias for is_primary."""
        return self.is_primary

    @is_lead.setter
    def is_lead(self, value: bool) -> None:
        self.is_primary = value

    def __repr__(self) -> str:
        return f"<ArticleMedia(id={self.id}, article_id={self.article_id}, type='{self.media_type}', is_primary={self.is_primary})>"
