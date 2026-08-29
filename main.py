"""FastAPI main application entry point for Fan Zone sports news backend."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fan_zone.api.v1.router import v1_router
from fan_zone.config import Settings, get_settings
from fan_zone.db.session import close_db, init_db
from fan_zone.scheduler.poller import get_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle context manager handling startup and graceful shutdown."""
    settings = getattr(app.state, "settings", None) or get_settings()
    logger.info("Initializing FanZone database schema and seeding default Israeli sources...")
    try:
        await init_db(seed_sources=True)
    except Exception as e:
        logger.error(f"Database initialization error on startup: {e}", exc_info=True)

    # Initialize and start background scheduler if enabled
    scheduler = get_scheduler(settings=settings)
    if settings.ENABLE_SCHEDULER:
        logger.info(f"Starting background ingestion scheduler (interval={settings.POLL_INTERVAL_SECONDS}s)...")
        await scheduler.start()
    else:
        logger.info("Background ingestion scheduler disabled by configuration.")

    yield

    # Shutdown sequence
    logger.info("Shutting down FanZone backend services...")
    if scheduler.is_running:
        await scheduler.stop()

    await close_db()
    logger.info("FanZone backend shutdown complete.")


def create_app(settings: Settings = None) -> FastAPI:
    """Factory function creating and configuring the FastAPI application instance."""
    app_settings = settings or get_settings()

    app = FastAPI(
        title="FanZone — Israeli Sports News Ingestion & Tagging API",
        description=(
            "Automated monitoring, multi-source ingestion, AI non-clickbait headline generation, "
            "entity classification, and structured sports REST API."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.state.settings = app_settings

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global unhandled exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected internal server error occurred.",
                    "detail": str(exc) if app_settings.DEBUG else None,
                }
            },
        )

    # Mount REST API v1 routes
    app.include_router(v1_router, prefix="/api/v1")

    # Root informational endpoint
    @app.get("/", tags=["System"])
    async def root_info():
        return {
            "app": app_settings.APP_NAME,
            "version": "1.0.0",
            "docs": "/docs",
            "api_v1": "/api/v1",
            "health": "/api/v1/health",
        }

    # Root health alias
    @app.get("/health", tags=["System"])
    async def root_health():
        return {
            "status": "healthy",
            "message": "FanZone backend service is online",
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    cfg = get_settings()
    uvicorn.run(
        "fan_zone.main:app",
        host=cfg.HOST,
        port=cfg.PORT,
        reload=cfg.DEBUG,
    )
