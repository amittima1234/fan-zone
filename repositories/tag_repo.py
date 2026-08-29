"""Repository for entity tags and tag taxonomy."""

import re
from typing import Any, List, Optional, Tuple, Union
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.enums import TagType
from fan_zone.models.tag import Tag
from fan_zone.repositories.base import BaseRepository


def slugify(text: str) -> str:
    """Creates a clean URL/search slug from Hebrew or English text."""
    if not text:
        return ""
    text = text.strip()
    # Remove characters that are not alphanumeric (Hebrew, English, digits), whitespace, or hyphen
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    # Replace spaces and underscores with hyphens
    text = re.sub(r"[\s_]+", "-", text)
    # Collapse multiple hyphens into a single hyphen
    text = re.sub(r"-+", "-", text)
    # Strip leading and trailing hyphens
    text = text.strip("-")
    return text.lower()


class TagRepository(BaseRepository[Tag]):
    """Async repository for entity tags."""

    async def get_by_id(
        self,
        tag_id: int,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Tag]:
        session = self._get_session(db)
        stmt = select(Tag).where(Tag.id == tag_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        name: str,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Tag]:
        session = self._get_session(db)
        clean_name = name.strip()
        stmt = select(Tag).where(func.lower(Tag.name) == func.lower(clean_name))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_tag(
        self,
        name: str,
        tag_type: Union[TagType, str] = TagType.GENERAL,
        db: Optional[AsyncSession] = None,
    ) -> Tag:
        session = self._get_session(db)
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Tag name cannot be empty")

        if isinstance(tag_type, str):
            try:
                tag_type = TagType(tag_type.lower())
            except ValueError:
                tag_type = TagType.GENERAL

        existing = await self.get_by_name(clean_name, db=session)
        if existing:
            return existing

        slug = slugify(clean_name) or "tag"
        tag = Tag(
            name=clean_name,
            slug=slug,
            tag_type=tag_type,
            article_count=0,
        )
        session.add(tag)
        await session.flush()
        return tag

    async def get_or_create_tags(
        self,
        tags: List[Union[str, Tuple[str, Union[TagType, str]]]],
        db: Optional[AsyncSession] = None,
    ) -> List[Tag]:
        """Batch fetches or creates multiple entity tags."""
        session = self._get_session(db)
        results: List[Tag] = []
        seen_names = set()

        for item in tags:
            if isinstance(item, tuple) and len(item) == 2:
                name, t_type = item
            elif isinstance(item, str):
                name, t_type = item, TagType.GENERAL
            else:
                continue
            clean_name = name.strip()
            if not clean_name or clean_name.lower() in seen_names:
                continue
            seen_names.add(clean_name.lower())

            tag = await self.get_or_create_tag(clean_name, tag_type=t_type, db=session)
            results.append(tag)

        return results

    async def get_or_create_batch(
        self,
        tags_or_db: Any = None,
        db_or_tags: Any = None,
        *,
        tags: Optional[List[Tuple[str, Union[TagType, str]]]] = None,
        tag_tuples: Optional[List[Tuple[str, Union[TagType, str]]]] = None,
        db: Optional[AsyncSession] = None,
    ) -> List[Tag]:
        """Flexible batch tag creation accepting (tags, db) or (db, tag_tuples) or keyword args."""
        actual_db = db
        actual_tags = tags if tags is not None else tag_tuples

        if isinstance(tags_or_db, AsyncSession):
            actual_db = tags_or_db
            if isinstance(db_or_tags, list):
                actual_tags = db_or_tags
        elif isinstance(tags_or_db, list):
            actual_tags = tags_or_db
            if isinstance(db_or_tags, AsyncSession):
                actual_db = db_or_tags

        if actual_tags is None:
            actual_tags = []

        return await self.get_or_create_tags(tags=actual_tags, db=actual_db)

    get_or_create_tags_batch = get_or_create_batch

    async def list_tags(
        self,
        tag_type: Optional[Union[TagType, str]] = None,
        search_query: Optional[str] = None,
        limit: int = 50,
        db: Optional[AsyncSession] = None,
    ) -> List[Tag]:
        session = self._get_session(db)
        stmt = select(Tag)

        if tag_type:
            if isinstance(tag_type, str):
                try:
                    tag_type = TagType(tag_type.lower())
                except ValueError:
                    pass
            stmt = stmt.where(Tag.tag_type == tag_type)

        if search_query:
            term = f"%{search_query.strip()}%"
            stmt = stmt.where(Tag.name.ilike(term))

        stmt = stmt.order_by(Tag.article_count.desc(), Tag.name.asc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_popular_tags(
        self,
        limit: int = 20,
        db: Optional[AsyncSession] = None,
    ) -> List[Tag]:
        return await self.list_tags(limit=limit, db=db)
