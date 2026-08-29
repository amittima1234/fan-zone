"""Source model representing news outlets."""

from typing import TYPE_CHECKING, List, Optional
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fan_zone.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from fan_zone.models.article import Article


class Source(Base, TimestampMixin):
    """Represents an Israeli sports news outlet/source."""
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    feed_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    articles: Mapped[List["Article"]] = relationship(
        "Article",
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def code(self) -> str:
        """Alias for name."""
        return self.name

    @code.setter
    def code(self, value: str) -> None:
        self.name = value

    def __repr__(self) -> str:
        return f"<Source(id={self.id}, name='{self.name}', display_name='{self.display_name}')>"
