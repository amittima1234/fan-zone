"""Asynchronous periodic background news scraper and ingestion scheduler."""

import asyncio
import logging
from typing import Dict, Optional

from core.config import settings
from db.repository import ArticleRepository
from db.session import async_session_factory
from services.ai_worker import AIEnrichmentService, FallbackAIEnrichmentService
from services.scrapers import get_all_scrapers

logger = logging.getLogger(__name__)


class NewsScheduler:
    """Asynchronous background scheduler for periodic Israeli sports news ingestion."""

    def __init__(self, interval_seconds: Optional[int] = None) -> None:
        self.interval_seconds = interval_seconds or settings.POLL_INTERVAL_SECONDS
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        """Return True if background scheduler loop is currently running."""
        return self._running and self._task is not None and not self._task.done()

    async def run_once(self) -> Dict[str, int]:
        """Execute a single ingestion cycle across all registered scrapers.

        Returns:
            Dictionary containing counts of fetched and newly saved articles.
        """
        logger.info("Starting scheduled ingestion cycle...")
        scrapers = get_all_scrapers()

        # Instantiate AI service
        try:
            ai_service = AIEnrichmentService(use_mock=settings.is_mock_ai)
        except Exception:
            ai_service = FallbackAIEnrichmentService(use_mock=True)

        total_fetched = 0
        total_saved = 0

        async with async_session_factory() as session:
            repo = ArticleRepository(session)
            for scraper in scrapers:
                pub_id = getattr(scraper, "publisher_id", "unknown")
                try:
                    raw_articles = await scraper.scrape(limit=15)
                    total_fetched += len(raw_articles)

                    for raw_article in raw_articles:
                        url_str = str(raw_article.url).strip()
                        if await repo.exists_by_url(url_str):
                            continue

                        try:
                            if hasattr(ai_service, "enrich_and_store"):
                                await ai_service.enrich_and_store(raw_article, repo)
                            else:
                                enriched = await ai_service.enrich_article(raw_article)
                                await repo.create_enriched_article(raw_article, enriched)
                            total_saved += 1
                        except Exception as enrich_err:
                            logger.warning(
                                "Scheduler: failed to enrich article from %s: %s",
                                url_str,
                                enrich_err,
                            )
                except Exception as scraper_err:
                    logger.error(
                        "Scheduler: error executing scraper '%s': %s",
                        pub_id,
                        scraper_err,
                    )

        logger.info(
            "Scheduled ingestion finished: fetched %d, saved %d new articles.",
            total_fetched,
            total_saved,
        )
        return {"fetched": total_fetched, "saved": total_saved}

    async def _loop(self) -> None:
        """Internal background loop running ingestion periodically."""
        logger.info(
            "NewsScheduler started with poll interval of %d seconds.",
            self.interval_seconds,
        )
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                logger.info("NewsScheduler task cancelled.")
                break
            except Exception as e:
                logger.error("Unexpected error in NewsScheduler loop: %s", e)

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                logger.info("NewsScheduler sleep interrupted by cancellation.")
                break

    def start(self) -> None:
        """Start the background scheduler task if not already running."""
        if self.is_running:
            logger.warning("NewsScheduler is already running.")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop(), name="news_scheduler_loop")
        logger.info("NewsScheduler background task spawned.")

    async def stop(self) -> None:
        """Gracefully stop the background scheduler task."""
        if not self._running and self._task is None:
            return

        logger.info("Stopping NewsScheduler...")
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("NewsScheduler stopped cleanly.")


# Global scheduler singleton
scheduler = NewsScheduler()
