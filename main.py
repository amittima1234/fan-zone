"""FastAPI main application entrypoint for Fan Zone Israeli Sports News Backend."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.api import api_router
from api.v1.endpoints import feed, health
from core.config import settings
from db.session import init_db
from services.scheduler import scheduler

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager handling startup and shutdown events."""
    logger.info("Initializing database tables...")
    try:
        await init_db()
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize database tables: %s", e)

    # Start background scheduler if enabled
    if settings.ENABLE_SCHEDULER:
        logger.info("Starting periodic scraper scheduler...")
        scheduler.start()

    yield

    # Shutdown
    if scheduler.is_running:
        logger.info("Stopping periodic scraper scheduler...")
        await scheduler.stop()
    logger.info("Application shutdown complete.")


def create_application() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="Ad-free, personalized sports news aggregation backend for Israeli sports feeds.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS configuration allowing open access for mobile/web frontends
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include Versioned API Routes (/api/v1)
    app.include_router(api_router, prefix="/api/v1")

    # Include Top-Level Aliases for convenience (/api/feed, /health)
    app.include_router(feed.router, prefix="/api/feed", tags=["feed-alias"])
    app.include_router(health.router, prefix="/health", tags=["health-root"])

    @app.get("/", tags=["root"], summary="Root service discovery")
    async def root():
        """Root endpoint providing service metadata and discovery URLs."""
        return {
            "app_name": settings.APP_NAME,
            "environment": settings.APP_ENV,
            "version": "1.0.0",
            "docs_url": "/docs",
            "health_url": "/health",
            "feed_url": "/api/v1/feed",
        }

    return app


# Application singleton
app: FastAPI = create_application()
