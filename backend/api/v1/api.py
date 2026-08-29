"""FastAPI v1 root API router aggregating all resource sub-routers."""

from fastapi import APIRouter

from api.v1.endpoints import feed, health, ingestion

api_router = APIRouter()

api_router.include_router(feed.router, prefix="/feed", tags=["feed"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(ingestion.router, prefix="/ingestion", tags=["ingestion"])
