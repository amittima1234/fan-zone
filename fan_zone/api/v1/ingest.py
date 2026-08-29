"""FastAPI REST endpoints for triggering and monitoring ingestion jobs."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.ai.service import get_ai_processor
from fan_zone.db.session import get_db
from fan_zone.schemas.ingest import IngestTriggerRequest, IngestTriggerResponse
from fan_zone.scheduler.poller import get_scheduler
from fan_zone.services.ingestion_service import IngestionService

router = APIRouter()


@router.post("/trigger", response_model=IngestTriggerResponse, summary="Trigger manual article or source ingestion")
async def trigger_ingestion(
    request: Optional[IngestTriggerRequest] = None,
    db: AsyncSession = Depends(get_db),
) -> IngestTriggerResponse:
    """Triggers on-demand ingestion for either:
    1. A single article URL (crawling, parsing, AI rewriting, persisting).
    2. A specific news source outlet (Sport5, ONE, Walla, Ynet, etc.).
    3. All configured active sources if no target is specified.
    """
    req = request or IngestTriggerRequest()
    ai_proc = get_ai_processor()
    service = IngestionService(db=db, ai_processor=ai_proc)

    # 1. Single article URL ingestion
    if req.url and req.url.strip():
        source_target = req.source_name or req.source_code
        article, is_new = await service.ingest_url(url=req.url.strip(), source_name=source_target)
        if not article:
            return IngestTriggerResponse(
                status="failed",
                message=f"Failed to extract or ingest article from URL: {req.url}",
                articles_ingested=0,
                article_id=None,
            )

        msg = "Article successfully ingested and enriched with AI" if is_new else "Article already exists (deduplicated per source)"
        return IngestTriggerResponse(
            status="success",
            message=msg,
            articles_ingested=1 if is_new else 0,
            article_id=article.id,
        )

    # 2. Source-specific ingestion
    target_source = req.source_name or req.source_code
    if target_source and target_source.strip():
        stats = await service.ingest_source(target_source.strip(), max_articles=10)
        status_str = "success" if stats.total_errors == 0 else ("partial" if stats.total_ingested > 0 else "failed")
        msg = f"Processed {stats.total_processed} items from {target_source}: {stats.total_ingested} ingested, {stats.total_skipped} skipped, {stats.total_failed} failed."
        return IngestTriggerResponse(
            status=status_str,
            message=msg,
            articles_ingested=stats.total_ingested,
        )

    # 3. All sources ingestion
    stats = await service.ingest_all_sources(max_articles_per_source=10)
    status_str = "success" if stats.total_errors == 0 else ("partial" if stats.total_ingested > 0 else "failed")
    msg = f"Processed {stats.total_processed} items across all sources: {stats.total_ingested} ingested, {stats.total_skipped} skipped, {stats.total_failed} failed."
    return IngestTriggerResponse(
        status=status_str,
        message=msg,
        articles_ingested=stats.total_ingested,
    )


@router.get("/status", summary="Get background scheduler and ingestion job status")
async def get_ingestion_status() -> Dict[str, Any]:
    """Returns runtime telemetry for the background ingestion scheduler and last execution stats."""
    scheduler = get_scheduler()
    return {
        "scheduler_running": scheduler.is_running,
        "scheduler_enabled": scheduler.enabled,
        "poll_interval_seconds": scheduler.poll_interval,
        "run_count": scheduler.run_count,
        "last_run_at": scheduler.last_run_at.isoformat() if scheduler.last_run_at else None,
        "last_run_stats": scheduler.last_run_stats.model_dump() if scheduler.last_run_stats else None,
    }
