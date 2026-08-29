"""Pydantic schemas for health checks and system statistics."""

from typing import Dict, List
from datetime import datetime
from pydantic import BaseModel, Field

from fan_zone.schemas.source import SourceStatSchema


class HealthResponse(BaseModel):
    status: str = Field("healthy", description="Overall service status")
    database: str = Field("connected", description="Database connection status")
    scheduler_running: bool = Field(False, description="Whether background poller is running")
    timestamp: datetime = Field(..., description="Timestamp of health check")
    version: str = Field("1.0.0", description="API version")


class StatsResponse(BaseModel):
    total_articles: int = Field(0, description="Total articles stored in the database")
    ai_processed_count: int = Field(0, description="Count of articles processed by AI")
    ai_pending_count: int = Field(0, description="Count of articles waiting for AI processing")
    failed_count: int = Field(0, description="Count of articles with failed processing")
    sources_stats: List[SourceStatSchema] = Field(default_factory=list, description="Per-source ingestion statistics")
    sports_breakdown: Dict[str, int] = Field(default_factory=dict, description="Article count grouped by sport")
