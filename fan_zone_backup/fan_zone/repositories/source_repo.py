"""Repository for managing news sources."""

from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.source import Source
from fan_zone.models.article import Article
from fan_zone.repositories.base import BaseRepository
from fan_zone.schemas.source import SourceCreate, SourceStatSchema

DEFAULT_SOURCES = [
    {
        "name": "sport5",
        "display_name": "Sport5",
        "base_url": "https://www.sport5.co.il",
        "feed_url": "https://www.sport5.co.il/rss.xml",
        "poll_interval_seconds": 300,
    },
    {
        "name": "one",
        "display_name": "ONE",
        "base_url": "https://www.one.co.il",
        "feed_url": "https://www.one.co.il/cat/coop/xml/rss.aspx",
        "poll_interval_seconds": 300,
    },
    {
        "name": "walla",
        "display_name": "Walla! Sports",
        "base_url": "https://sports.walla.co.il",
        "feed_url": "https://rss.walla.co.il/feed/3",
        "poll_interval_seconds": 300,
    },
    {
        "name": "ynet",
        "display_name": "Ynet Sport",
        "base_url": "https://www.ynet.co.il/sport",
        "feed_url": "https://www.ynet.co.il/Integration/StoryRss3.xml",
        "poll_interval_seconds": 300,
    },
    {
        "name": "sport1",
        "display_name": "Sport1",
        "base_url": "https://sport1.maariv.co.il",
        "feed_url": "https://sport1.maariv.co.il/rss",
        "poll_interval_seconds": 300,
    },
    {
        "name": "israelhayom",
        "display_name": "Israel Hayom",
        "base_url": "https://www.israelhayom.co.il/sport",
        "feed_url": "https://www.israelhayom.co.il/rss.xml",
        "poll_interval_seconds": 300,
    },
    {
        "name": "haaretz",
        "display_name": "Haaretz",
        "base_url": "https://www.haaretz.co.il/sport",
        "feed_url": "https://www.haaretz.co.il/cmlink/1.1617539",
        "poll_interval_seconds": 300,
    },
]


class SourceRepository(BaseRepository[Source]):
    """Async repository for news sources."""

    async def get_by_id(
        self,
        source_id: int,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Source]:
        session = self._get_session(db)
        stmt = select(Source).where(Source.id == source_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        name: str,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Source]:
        session = self._get_session(db)
        clean_name = name.strip().lower()
        stmt = select(Source).where(func.lower(Source.name) == clean_name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        code: str,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Source]:
        """Alias for get_by_name."""
        return await self.get_by_name(code, db=db)

    async def get_all_active(
        self,
        db: Optional[AsyncSession] = None,
    ) -> List[Source]:
        session = self._get_session(db)
        stmt = select(Source).where(Source.is_active == True).order_by(Source.id.asc())  # noqa: E712
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self,
        db: Optional[AsyncSession] = None,
    ) -> List[Source]:
        session = self._get_session(db)
        stmt = select(Source).order_by(Source.id.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create_or_get(
        self,
        source_data: Union[SourceCreate, dict, None] = None,
        db: Optional[AsyncSession] = None,
        **kwargs,
    ) -> Tuple[Source, bool]:
        session = self._get_session(db)
        if source_data is None:
            data = kwargs
        elif isinstance(source_data, SourceCreate):
            data = source_data.model_dump()
        else:
            data = dict(source_data)
            if kwargs:
                data.update(kwargs)
        
        name = data["name"].strip().lower()
        existing = await self.get_by_name(name, db=session)
        if existing:
            return existing, False

        source = Source(
            name=name,
            display_name=data.get("display_name") or data["name"],
            base_url=data.get("base_url") or f"https://{name}.co.il",
            feed_url=data.get("feed_url"),
            is_active=data.get("is_active", True),
            poll_interval_seconds=data.get("poll_interval_seconds", 300),
        )
        session.add(source)
        await session.flush()
        return source, True

    async def update_poll_status(
        self,
        source_id: int,
        success: bool,
        error_message: Optional[str] = None,
        error_msg: Optional[str] = None,
        articles_added: int = 0,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Source]:
        session = self._get_session(db)
        source = await self.get_by_id(source_id, db=session)
        if not source:
            return None

        now = datetime.now(timezone.utc)
        source.last_polled_at = now
        if success:
            source.last_success_at = now
            source.error_count = 0
        else:
            source.error_count += 1

        await session.flush()
        return source

    async def seed_default_sources(
        self,
        db: Optional[AsyncSession] = None,
    ) -> List[Source]:
        """Seeds the 7 standard Israeli sports news outlets if missing."""
        session = self._get_session(db)
        seeded = []
        for def_source in DEFAULT_SOURCES:
            source, _ = await self.create_or_get(def_source, db=session)
            seeded.append(source)
        await session.flush()
        return seeded

    async def get_stats(
        self,
        db: Optional[AsyncSession] = None,
    ) -> List[SourceStatSchema]:
        """Calculates per-source article counts and polling metrics."""
        session = self._get_session(db)
        
        # Subquery for article counts per source
        count_stmt = (
            select(Article.source_id, func.count(Article.id).label("article_count"))
            .group_by(Article.source_id)
        )
        counts_res = await session.execute(count_stmt)
        counts_map: Dict[int, int] = {row[0]: row[1] for row in counts_res.all()}

        sources = await self.list_all(db=session)
        stats = []
        for s in sources:
            stats.append(
                SourceStatSchema(
                    code=s.name,
                    name=s.display_name,
                    display_name=s.display_name,
                    total_articles=counts_map.get(s.id, 0),
                    last_polled_at=s.last_polled_at,
                    last_success_at=s.last_success_at,
                    error_count=s.error_count,
                )
            )
        return stats
