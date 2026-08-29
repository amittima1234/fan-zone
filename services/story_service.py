"""Story clustering and multi-source synthesis service for copyright-safe news delivery."""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.article import Article
from fan_zone.models.story import Story
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.repositories.story_repo import StoryRepository

logger = logging.getLogger(__name__)


class StoryService:
    """Orchestrates story clustering across Israeli sports news outlets and generates
    concise, multi-source synthesized briefs with outbound citations.
    """

    def __init__(
        self,
        db: AsyncSession,
        story_repo: Optional[StoryRepository] = None,
        article_repo: Optional[ArticleRepository] = None,
    ) -> None:
        self.db = db
        self.story_repo = story_repo or StoryRepository(db)
        self.article_repo = article_repo or ArticleRepository(db)

    async def synthesize_all_pending(self, limit: int = 50) -> Dict[str, int]:
        """Fetches recent articles, clusters them by story, and generates synthesized briefs."""
        articles, total = await self.article_repo.list_articles(
            limit=limit,
            sort_by="published_at",
            sort_desc=True,
            db=self.db,
        )

        if not articles:
            return {"stories_created": 0, "stories_updated": 0}

        clusters = self._cluster_articles(articles)
        created_count = 0
        updated_count = 0

        for cluster in clusters:
            story = await self.synthesize_cluster(cluster)
            if story:
                created_count += 1

        await self.db.commit()
        return {"stories_created": created_count, "stories_updated": updated_count}

    @staticmethod
    def _is_within_time_window(
        dt_a: Optional[Union[datetime, str]],
        dt_b: Optional[Union[datetime, str]],
        max_seconds: float = 172800.0,
    ) -> bool:
        """Compares article timestamps handling timezone-aware/naive and None values safely."""
        if dt_a is None or dt_b is None:
            return True
        if isinstance(dt_a, str):
            try:
                dt_a = datetime.fromisoformat(dt_a.replace("Z", "+00:00"))
            except Exception:
                return True
        if isinstance(dt_b, str):
            try:
                dt_b = datetime.fromisoformat(dt_b.replace("Z", "+00:00"))
            except Exception:
                return True
        try:
            t_a = dt_a if dt_a.tzinfo is None else dt_a.astimezone(timezone.utc).replace(tzinfo=None)
            t_b = dt_b if dt_b.tzinfo is None else dt_b.astimezone(timezone.utc).replace(tzinfo=None)
            return abs((t_a - t_b).total_seconds()) < max_seconds
        except Exception:
            return True

    def _cluster_articles(self, articles: List[Article]) -> List[List[Article]]:
        """Clusters articles covering the same match or event by sport, entity overlap, and timing."""
        clusters: List[List[Article]] = []
        assigned_article_ids: Set[int] = set()

        for i, art_a in enumerate(articles):
            if art_a.id in assigned_article_ids:
                continue

            current_cluster = [art_a]
            assigned_article_ids.add(art_a.id)

            a_teams = set(tm.lower() for tm in (art_a.teams_json or []))
            a_players = set(p.lower() for p in (art_a.players_json or []))
            a_sport = (art_a.sport or "").lower()

            for j in range(i + 1, len(articles)):
                art_b = articles[j]
                if art_b.id in assigned_article_ids:
                    continue

                b_sport = (art_b.sport or "").lower()
                # Must match sport
                if a_sport and b_sport and a_sport != b_sport:
                    continue

                b_teams = set(tm.lower() for tm in (art_b.teams_json or []))
                b_players = set(p.lower() for p in (art_b.players_json or []))

                # Check entity overlap (shared teams or shared players)
                shared_teams = a_teams.intersection(b_teams)
                shared_players = a_players.intersection(b_players)
                is_individual_sport = a_sport in ["ג'ודו", "התעמלות", "התעמלות אומנותית", "טניס", "שחייה", "אתלטיקה", "גלישה", "שייט"]

                should_cluster = False
                if is_individual_sport and shared_players and len(shared_players) >= 1:
                    should_cluster = True
                elif shared_teams and (shared_players or (art_a.competition and art_a.competition == art_b.competition)):
                    should_cluster = True
                elif shared_teams:
                    words_a = set(re.findall(r"\w+", (art_a.cleaned_body or art_a.original_title or "").lower()))
                    words_b = set(re.findall(r"\w+", (art_b.cleaned_body or art_b.original_title or "").lower()))
                    overlap = len(words_a.intersection(words_b)) / max(len(words_a.union(words_b)), 1)
                    if overlap >= 0.08 or (art_a.sport and art_a.sport == art_b.sport):
                        should_cluster = True
                elif shared_players and len(shared_players) >= 1:
                    should_cluster = True

                if should_cluster and self._is_within_time_window(art_a.published_at, art_b.published_at, 172800):
                    current_cluster.append(art_b)
                    assigned_article_ids.add(art_b.id)

            clusters.append(current_cluster)

        return clusters

    async def synthesize_cluster(self, articles: List[Article]) -> Optional[Story]:
        """Synthesizes a cohesive, copyright-safe story brief from one or more articles."""
        if not articles:
            return None

        primary_article = articles[0]

        # Gather citations for all source articles
        citations: List[Dict[str, Any]] = []
        seen_urls = set()

        for art in articles:
            if art.canonical_url in seen_urls:
                continue
            seen_urls.add(art.canonical_url)

            source_name = art.source.display_name if art.source else "מקור חדשות"
            source_code = art.source.name if art.source else None

            citations.append({
                "article_id": art.id,
                "source_name": source_name,
                "source_code": source_code,
                "publisher": source_name,
                "original_title": art.original_title,
                "url": art.canonical_url,
                "published_at": art.published_at.isoformat() if art.published_at else None,
            })

        # Merge entity tags
        all_teams = list({tm for art in articles for tm in (art.teams_json or []) if tm})
        all_players = list({p for art in articles for p in (art.players_json or []) if p})
        all_tags = list({t for art in articles for t in (art.tags_json or []) if t})

        sport = primary_article.sport or "ספורט כללי"
        competition = primary_article.competition

        # Construct synthesized title and summary
        title = primary_article.ai_headline or primary_article.original_title
        
        if len(articles) > 1:
            sources_list_str = ", ".join(c["source_name"] for c in citations)
            base_sub = primary_article.ai_subheadline or primary_article.original_subtitle or ""
            summary = (
                f"{base_sub}\n\n"
                f"דיווח מרוכז המשלב מקורות ספורט מובילים בישראל ({sources_list_str}). "
                f"לפרטים מלאים מכל אחד מהאתרים, ניתן לעיין בקישורי המקור המצורפים."
            )
        else:
            summary = primary_article.ai_subheadline or primary_article.summary or primary_article.original_subtitle or (
                primary_article.raw_paragraphs[0] if primary_article.raw_paragraphs else primary_article.original_title
            )

        # Select lead image if present
        lead_img = None
        for art in articles:
            if art.lead_image:
                lead_img = art.lead_image
                break

        lead_image_url = lead_img.url if lead_img else None
        lead_image_caption = lead_img.caption if lead_img else None
        lead_image_credit = lead_img.credit if lead_img else None

        story = await self.story_repo.upsert_story(
            title=title,
            summary=summary,
            published_at=primary_article.published_at,
            citations_json=citations,
            sport=sport,
            competition=competition,
            teams_json=all_teams,
            players_json=all_players,
            tags_json=all_tags,
            lead_image_url=lead_image_url,
            lead_image_caption=lead_image_caption,
            lead_image_credit=lead_image_credit,
            db=self.db,
        )

        return story
