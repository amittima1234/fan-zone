"""Pydantic schemas for manual ingestion triggers and run statistics."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class IngestTriggerRequest(BaseModel):
    url: Optional[str] = Field(None, description="Direct URL of an article to scrape and ingest")
    source_name: Optional[str] = Field(None, description="Source machine name (e.g. sport5, one) to trigger polling for")
    source_code: Optional[str] = Field(None, description="Alias for source_name")
    force_ai: bool = Field(False, description="Whether to force re-enrichment with AI even if already processed")


class IngestTriggerResponse(BaseModel):
    status: str = Field(..., description="Execution status: success, partial, failed, skipped")
    message: str = Field(..., description="Human-readable result summary")
    articles_ingested: int = Field(0, description="Count of newly ingested articles")
    article_id: Optional[int] = Field(None, description="ID of ingested article if single URL trigger")


class IngestionRunStats(BaseModel):
    source_name: Optional[str] = None
    total_discovered: int = 0
    total_processed: int = 0
    total_ingested: int = 0
    total_skipped: int = 0
    total_skipped_duplicate: int = 0
    total_failed: int = 0
    total_errors: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = Field(default_factory=list)
    source_counts: Dict[str, int] = Field(default_factory=dict)
