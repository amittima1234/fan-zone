"""Main API v1 router combining all resource sub-routers."""

from fastapi import APIRouter

from fan_zone.api.v1.articles import router as articles_router
from fan_zone.api.v1.feed import router as feed_router
from fan_zone.api.v1.ingest import router as ingest_router
from fan_zone.api.v1.sources import router as sources_router
from fan_zone.api.v1.stories import router as stories_router
from fan_zone.api.v1.system import router as system_router
from fan_zone.api.v1.tags import router as tags_router

v1_router = APIRouter()

# Primary Synthesis-First Fan Endpoints
v1_router.include_router(stories_router, prefix="/stories", tags=["Stories"])
v1_router.include_router(feed_router, prefix="/feed", tags=["Feed"])

# News Outlets & Admin Articles Endpoints
v1_router.include_router(articles_router, prefix="/articles", tags=["Articles"])
v1_router.include_router(sources_router, prefix="/sources", tags=["Sources"])
v1_router.include_router(tags_router, prefix="/tags", tags=["Tags"])
v1_router.include_router(ingest_router, prefix="/ingest", tags=["Ingestion"])
v1_router.include_router(system_router, tags=["System"])
