"""In-process background polling scheduler for FanZone sports news ingestion."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fan_zone.ai.service import get_ai_processor
from fan_zone.config import Settings, get_settings
from fan_zone.db.session import get_session_factory
from fan_zone.schemas.ingest import IngestionRunStats
from fan_zone.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


class IngestionScheduler:
    """In-process background polling worker that periodically triggers sports news
    crawling, parsing, AI entity extraction, and persistence with concurrency locking.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        ai_processor: Optional[Any] = None,
        settings: Optional[Settings] = None,
        poll_interval: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self.ai_processor = ai_processor
        self.poll_interval = poll_interval if poll_interval is not None else self.settings.POLL_INTERVAL_SECONDS
        self.enabled = enabled if enabled is not None else self.settings.ENABLE_SCHEDULER

        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._is_running = False
        self._last_run_at: Optional[datetime] = None
        self._last_run_stats: Optional[IngestionRunStats] = None
        self._run_count: int = 0

    @property
    def is_running(self) -> bool:
        """Returns True if the background polling loop is active."""
        return self._is_running and self._task is not None and not self._task.done()

    @property
    def last_run_at(self) -> Optional[datetime]:
        """Returns timestamp of the last executed ingestion cycle."""
        return self._last_run_at

    @property
    def last_run_stats(self) -> Optional[IngestionRunStats]:
        """Returns stats from the most recent ingestion cycle."""
        return self._last_run_stats

    @property
    def run_count(self) -> int:
        """Returns the total number of ingestion cycles executed."""
        return self._run_count

    async def start(self) -> None:
        """Starts the background asyncio polling worker task."""
        if self._is_running and self._task and not self._task.done():
            logger.warning("IngestionScheduler is already running.")
            return

        if not self.enabled:
            logger.info("IngestionScheduler is disabled via configuration (ENABLE_SCHEDULER=False).")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._run_loop(), name="fanzone_ingestion_poller")
        logger.info(
            f"IngestionScheduler started background poller (interval={self.poll_interval}s, "
            f"enabled={self.enabled})."
        )

    async def stop(self) -> None:
        """Gracefully stops and cancels the background poller task."""
        if not self._is_running and (not self._task or self._task.done()):
            return

        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Error during scheduler task cancellation: {e}")

        self._task = None
        logger.info("IngestionScheduler stopped gracefully.")

    async def run_now(
        self,
        source_name: Optional[str] = None,
        max_articles: int = 10,
    ) -> IngestionRunStats:
        """Immediately executes an ingestion cycle protected by the mutex lock.
        
        Args:
            source_name: Specific source code/name to ingest (e.g. 'sport5'), or None for all active.
            max_articles: Maximum number of articles per source to discover and ingest.
            
        Returns:
            IngestionRunStats recording discovered, ingested, skipped, and failed metrics.
        """
        if self._lock.locked():
            logger.warning("Ingestion run already in progress. Skipping overlapping trigger.")
            skipped_stats = IngestionRunStats(
                source_name=source_name or "ALL_SOURCES",
                total_skipped=1,
                errors=["Concurrent ingestion run already in progress; skipped."],
            )
            return skipped_stats

        async with self._lock:
            start_ts = datetime.now(timezone.utc)
            self._last_run_at = start_ts
            logger.info(f"Starting ingestion cycle (source={source_name or 'ALL_SOURCES'}) at {start_ts.isoformat()}")

            factory = self.session_factory or get_session_factory()
            processor = self.ai_processor or get_ai_processor()

            stats: IngestionRunStats
            async with factory() as session:
                try:
                    service = IngestionService(db=session, ai_processor=processor)
                    if source_name:
                        stats = await service.ingest_source(source_name, max_articles=max_articles)
                    else:
                        stats = await service.ingest_all_sources(max_articles_per_source=max_articles)
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    logger.error(f"Ingestion run failed with exception: {e}", exc_info=True)
                    stats = IngestionRunStats(
                        source_name=source_name or "ALL_SOURCES",
                        total_failed=1,
                        total_errors=1,
                        duration_seconds=(datetime.now(timezone.utc) - start_ts).total_seconds(),
                        errors=[f"Ingestion cycle exception: {str(e)}"],
                    )

            self._last_run_stats = stats
            self._run_count += 1
            logger.info(
                f"Ingestion cycle finished in {stats.duration_seconds:.2f}s: "
                f"ingested={stats.total_ingested}, skipped={stats.total_skipped}, failed={stats.total_failed}."
            )
            return stats

    async def _run_loop(self) -> None:
        """Continuous background loop executing poll ticks at poll_interval seconds."""
        logger.info(f"Entering IngestionScheduler loop with interval of {self.poll_interval}s.")
        while self._is_running:
            try:
                await self.run_now()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in IngestionScheduler tick: {e}", exc_info=True)

            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break


# Global singleton holder
_global_scheduler: Optional[IngestionScheduler] = None


def get_scheduler(
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ai_processor: Optional[Any] = None,
    settings: Optional[Settings] = None,
) -> IngestionScheduler:
    """Returns or creates the global IngestionScheduler instance."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = IngestionScheduler(
            session_factory=session_factory,
            ai_processor=ai_processor,
            settings=settings,
        )
    return _global_scheduler


def set_scheduler(scheduler: Optional[IngestionScheduler]) -> None:
    """Sets or resets the global scheduler instance (primarily for tests)."""
    global _global_scheduler
    _global_scheduler = scheduler
