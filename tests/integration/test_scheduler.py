"""Integration tests for IngestionScheduler background poller and lifecycle."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fan_zone.ai.mock import MockAIProcessor
from fan_zone.config import Settings
from fan_zone.scheduler.poller import (
    IngestionScheduler,
    get_scheduler,
    set_scheduler,
)
from fan_zone.schemas.ingest import IngestionRunStats


@pytest.mark.asyncio
async def test_scheduler_initialization_defaults():
    """Verify scheduler properties upon instantiation."""
    custom_settings = Settings(
        POLL_INTERVAL_SECONDS=120,
        ENABLE_SCHEDULER=True,
    )
    scheduler = IngestionScheduler(settings=custom_settings)
    assert scheduler.poll_interval == 120
    assert scheduler.enabled is True
    assert scheduler.is_running is False
    assert scheduler.last_run_at is None
    assert scheduler.last_run_stats is None
    assert scheduler.run_count == 0


@pytest.mark.asyncio
async def test_scheduler_disabled_flag():
    """Verify scheduler does not start a background task when disabled."""
    scheduler = IngestionScheduler(enabled=False, poll_interval=10)
    await scheduler.start()
    assert scheduler.is_running is False
    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_scheduler_start_stop_lifecycle():
    """Verify start and graceful stop of the background polling worker."""
    scheduler = IngestionScheduler(enabled=True, poll_interval=60)
    await scheduler.start()
    assert scheduler.is_running is True

    # Starting again should be a no-op and remain running
    await scheduler.start()
    assert scheduler.is_running is True

    # Stop gracefully
    await scheduler.stop()
    assert scheduler.is_running is False

    # Stopping again should be safe
    await scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.asyncio
async def test_scheduler_mutex_concurrency_lock():
    """Verify that asyncio.Lock prevents overlapping concurrent ingestion runs."""
    scheduler = IngestionScheduler(enabled=False)

    # Acquire lock externally to simulate an in-flight run
    await scheduler._lock.acquire()
    try:
        stats = await scheduler.run_now()
        assert stats.total_skipped == 1
        assert any("progress" in err for err in stats.errors)
    finally:
        scheduler._lock.release()


@pytest.mark.asyncio
async def test_scheduler_run_now_executes_cycle(seeded_session: AsyncSession, async_engine):
    """Verify run_now executes a full ingestion cycle and updates runtime stats."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    mock_ai = MockAIProcessor()
    scheduler = IngestionScheduler(
        session_factory=session_factory,
        ai_processor=mock_ai,
        enabled=False,
    )

    with patch(
        "fan_zone.services.ingestion_service.IngestionService.ingest_all_sources",
        new_callable=AsyncMock,
    ) as mock_ingest:
        mock_ingest.return_value = IngestionRunStats(
            source_name="ALL_SOURCES",
            total_discovered=15,
            total_ingested=12,
            total_skipped=3,
            total_errors=0,
            duration_seconds=1.5,
        )

        stats = await scheduler.run_now()
        assert stats.total_discovered == 15
        assert stats.total_ingested == 12
        assert stats.total_skipped == 3
        assert scheduler.run_count == 1
        assert scheduler.last_run_at is not None
        assert scheduler.last_run_stats == stats


@pytest.mark.asyncio
async def test_scheduler_run_now_source_specific(async_engine):
    """Verify run_now with a specific source name targets that source."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    scheduler = IngestionScheduler(
        session_factory=session_factory,
        ai_processor=MockAIProcessor(),
        enabled=False,
    )

    with patch(
        "fan_zone.services.ingestion_service.IngestionService.ingest_source",
        new_callable=AsyncMock,
    ) as mock_ingest_source:
        mock_ingest_source.return_value = IngestionRunStats(
            source_name="sport5",
            total_discovered=5,
            total_ingested=4,
            total_skipped=1,
        )

        stats = await scheduler.run_now(source_name="sport5", max_articles=5)
        assert stats.source_name == "sport5"
        assert stats.total_ingested == 4
        mock_ingest_source.assert_awaited_once_with("sport5", max_articles=5)


@pytest.mark.asyncio
async def test_scheduler_exception_resilience(async_engine):
    """Verify that internal service errors do not crash the scheduler and are reported in stats."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    scheduler = IngestionScheduler(
        session_factory=session_factory,
        enabled=False,
    )

    with patch(
        "fan_zone.services.ingestion_service.IngestionService.ingest_all_sources",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Database network timeout"),
    ):
        stats = await scheduler.run_now()
        assert stats.total_failed == 1
        assert stats.total_errors == 1
        assert any("Database network timeout" in err for err in stats.errors)
        assert scheduler.run_count == 1


@pytest.mark.asyncio
async def test_scheduler_periodic_tick_loop(async_engine):
    """Verify periodic polling loop triggers multiple times over time."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    scheduler = IngestionScheduler(
        session_factory=session_factory,
        ai_processor=MockAIProcessor(),
        poll_interval=1,  # 1 second for fast test
        enabled=True,
    )

    with patch(
        "fan_zone.services.ingestion_service.IngestionService.ingest_all_sources",
        new_callable=AsyncMock,
    ) as mock_ingest:
        mock_ingest.return_value = IngestionRunStats(total_ingested=1)

        await scheduler.start()
        assert scheduler.is_running is True

        # Wait enough for at least one tick
        await asyncio.sleep(1.2)

        await scheduler.stop()
        assert scheduler.is_running is False
        assert scheduler.run_count >= 1


@pytest.mark.asyncio
async def test_global_scheduler_get_set():
    """Verify singleton get_scheduler and set_scheduler helpers."""
    original = get_scheduler()
    assert original is not None

    custom = IngestionScheduler(poll_interval=555)
    set_scheduler(custom)
    assert get_scheduler() is custom
    assert get_scheduler().poll_interval == 555

    # Reset
    set_scheduler(None)
    new_inst = get_scheduler()
    assert new_inst is not custom
