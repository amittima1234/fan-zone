"""FastAPI REST endpoints for health checks, system metrics, and analytics."""

from datetime import datetime, timezone
import logging
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.db.session import get_db
from fan_zone.models.article import Article
from fan_zone.models.enums import IngestionStatus
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.schemas.health import HealthResponse, StatsResponse
from fan_zone.scheduler.poller import get_scheduler

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="System health check probe")
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """Verifies relational database connectivity and background scheduler worker liveness."""
    db_status = "connected"
    try:
        await db.execute(select(1))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "disconnected"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    scheduler = get_scheduler()
    return HealthResponse(
        status="healthy",
        database=db_status,
        scheduler_running=scheduler.is_running,
        timestamp=datetime.now(timezone.utc),
        version="1.0.0",
    )


@router.get("/stats", response_model=StatsResponse, summary="System analytics and ingestion statistics")
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """Returns aggregated platform metrics, including total articles, processing statuses,
    breakdown by sports discipline, and per-source ingestion statistics.
    """
    # 1. Total articles
    total_res = await db.execute(select(func.count(Article.id)))
    total_articles = total_res.scalar() or 0

    # 2. Status counts
    processed_res = await db.execute(
        select(func.count(Article.id)).where(Article.ingestion_status == IngestionStatus.AI_PROCESSED)
    )
    ai_processed_count = processed_res.scalar() or 0

    pending_res = await db.execute(
        select(func.count(Article.id)).where(Article.ingestion_status == IngestionStatus.PENDING)
    )
    ai_pending_count = pending_res.scalar() or 0

    failed_res = await db.execute(
        select(func.count(Article.id)).where(
            Article.ingestion_status.in_([IngestionStatus.FAILED, IngestionStatus.AI_FALLBACK])
        )
    )
    failed_count = failed_res.scalar() or 0

    # 3. Sports breakdown
    sports_stmt = (
        select(Article.sport, func.count(Article.id))
        .where(Article.sport.isnot(None))
        .group_by(Article.sport)
    )
    sports_res = await db.execute(sports_stmt)
    sports_breakdown: Dict[str, int] = {row[0]: row[1] for row in sports_res.all()}

    # 4. Sources stats
    source_repo = SourceRepository(db)
    sources_stats = await source_repo.get_stats(db=db)

    return StatsResponse(
        total_articles=total_articles,
        ai_processed_count=ai_processed_count,
        ai_pending_count=ai_pending_count,
        failed_count=failed_count,
        sources_stats=sources_stats,
        sports_breakdown=sports_breakdown,
    )
