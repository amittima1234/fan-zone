"""Health check and readiness probe endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, get_settings
from core.config import Settings
from schemas.feed import HealthCheckResponse

router = APIRouter()


@router.get(
    "",
    response_model=HealthCheckResponse,
    responses={
        200: {"description": "System is healthy and database is connected."},
        503: {"description": "System is unhealthy or database is unreachable."},
    },
    summary="Service health and readiness check",
    description="Validates application liveness, database connectivity, AI engine mode, and background scheduler state.",
)
async def check_health(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Execute async health probe and return detailed status."""
    db_connected = False
    try:
        # Ping database with lightweight SELECT query
        result = await session.execute(text("SELECT 1"))
        if result.scalar() == 1:
            db_connected = True
    except Exception:
        db_connected = False

    status_str = "healthy" if db_connected else "unhealthy"
    db_status_str = "connected" if db_connected else "disconnected"
    ai_mode_str = "mock" if settings.is_mock_ai else "live_gemini"
    scheduler_str = "enabled" if settings.ENABLE_SCHEDULER else "disabled"

    response_payload = HealthCheckResponse(
        status=status_str,
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        database=db_status_str,
        ai_mode=ai_mode_str,
        scheduler=scheduler_str,
        timestamp=datetime.now(timezone.utc),
    )

    http_status = status.HTTP_200_OK if db_connected else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=http_status,
        content=jsonable_encoder(response_payload),
    )
