"""Repository for managing synthesized, copyright-safe sports stories."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.story import Story
from fan_zone.repositories.base import BaseRepository


class StoryRepository(BaseRepository[Story]):
    """Async repository for synthesized sports news stories and fan feed queries."""

    async def get_by_id(
        self,
        story_id: int,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Story]:
        session = self._get_session(db)
        stmt = select(Story).where(Story.id == story_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_stories(
        self,
        sport: Optional[str] = None,
        team: Optional[str] = None,
        competition: Optional[str] = None,
        tag: Optional[str] = None,
        sports: Optional[List[str]] = None,
        teams: Optional[List[str]] = None,
        competitions: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        search_query: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "published_at",
        sort_desc: bool = True,
        db: Optional[AsyncSession] = None,
    ) -> Tuple[List[Story], int]:
        """Lists synthesized stories with single or multi-valued entity filtering and Hebrew search."""
        session = self._get_session(db)
        query = select(Story)
        conditions = []

        # Single sport filter
        if sport:
            conditions.append(Story.sport.ilike(f"%{sport.strip()}%"))

        # Multi-sport filter (for personalized feed)
        if sports:
            sports_clean = [s.strip() for s in sports if s and s.strip()]
            if sports_clean:
                conditions.append(or_(*[Story.sport.ilike(f"%{s}%") for s in sports_clean]))

        # Single competition filter
        if competition:
            conditions.append(Story.competition.ilike(f"%{competition.strip()}%"))

        # Multi-competition filter
        if competitions:
            comps_clean = [c.strip() for c in competitions if c and c.strip()]
            if comps_clean:
                conditions.append(or_(*[Story.competition.ilike(f"%{c}%") for c in comps_clean]))

        # Search query
        if search_query:
            term = f"%{search_query.strip()}%"
            conditions.append(
                or_(
                    Story.title.ilike(term),
                    Story.summary.ilike(term),
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        # Count query before pagination
        count_stmt = select(func.count(Story.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        
        count_res = await session.execute(count_stmt)
        total_count = count_res.scalar() or 0

        # Sorting
        sort_col = getattr(Story, sort_by, Story.published_at)
        order_fn = desc if sort_desc else asc
        query = query.order_by(order_fn(sort_col), desc(Story.id))

        # Pagination
        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        stories = list(result.scalars().all())

        # Post-filter for JSON array fields (teams and tags) in SQLite/Postgres agnostic way
        if team or teams or tag or tags:
            filtered_stories = []
            target_teams = set()
            if team:
                target_teams.add(team.strip().lower())
            if teams:
                target_teams.update(t.strip().lower() for t in teams if t and t.strip())

            target_tags = set()
            if tag:
                target_tags.add(tag.strip().lower())
            if tags:
                target_tags.update(tg.strip().lower() for tg in tags if tg and tg.strip())

            for s in stories:
                s_teams = {tm.lower() for tm in (s.teams_json or [])}
                s_tags = {tg.lower() for tg in (s.tags_json or [])}

                team_match = not target_teams or any(any(t in st or st in t for st in s_teams) for t in target_teams)
                tag_match = not target_tags or any(any(tg in st or st in tg for st in s_tags) for tg in target_tags)

                if team_match and tag_match:
                    filtered_stories.append(s)
            
            return filtered_stories, len(filtered_stories)

        return stories, total_count

    async def upsert_story(
        self,
        title: str,
        summary: str,
        published_at: Optional[datetime] = None,
        citations_json: Optional[List[Dict[str, Any]]] = None,
        sport: Optional[str] = None,
        competition: Optional[str] = None,
        teams_json: Optional[List[str]] = None,
        players_json: Optional[List[str]] = None,
        tags_json: Optional[List[str]] = None,
        lead_image_url: Optional[str] = None,
        lead_image_caption: Optional[str] = None,
        lead_image_credit: Optional[str] = None,
        story_id: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> Story:
        """Inserts a new story or updates an existing story."""
        session = self._get_session(db)

        story = None
        if story_id:
            story = await self.get_by_id(story_id, db=session)

        if not story:
            # Check by exact title match
            stmt = select(Story).where(Story.title == title.strip())
            res = await session.execute(stmt)
            story = res.scalar_one_or_none()

        if story:
            story.title = title.strip()
            story.summary = summary.strip()
            story.sport = sport
            story.competition = competition
            story.teams_json = teams_json or []
            story.players_json = players_json or []
            story.tags_json = tags_json or []
            story.lead_image_url = lead_image_url or story.lead_image_url
            story.lead_image_caption = lead_image_caption or story.lead_image_caption
            story.lead_image_credit = lead_image_credit or story.lead_image_credit
            story.citations_json = citations_json or []
            story.article_count = len(citations_json) if citations_json else 1
            if published_at:
                story.published_at = published_at
            story.updated_at = datetime.now(timezone.utc)
        else:
            story = Story(
                title=title.strip(),
                summary=summary.strip(),
                sport=sport,
                competition=competition,
                teams_json=teams_json or [],
                players_json=players_json or [],
                tags_json=tags_json or [],
                lead_image_url=lead_image_url,
                lead_image_caption=lead_image_caption,
                lead_image_credit=lead_image_credit,
                citations_json=citations_json or [],
                article_count=len(citations_json) if citations_json else 1,
                published_at=published_at or datetime.now(timezone.utc),
            )
            session.add(story)

        await session.flush()
        return story
