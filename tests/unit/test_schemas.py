"""Unit tests for Pydantic V2 request, response, and filter schemas."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.schemas.source import (
    SourceCreate,
    SourceRead,
    SourceSummarySchema,
    SourceStatSchema,
)
from fan_zone.schemas.media import MediaCreate, MediaRead, MediaSchema
from fan_zone.schemas.tag import TagCreate, TagRead, TagSchema
from fan_zone.schemas.article import (
    ArticleCreate,
    ArticleSummarySchema,
    ArticleDetailSchema,
    ArticleFilter,
    PaginatedArticleResponse,
)
from fan_zone.schemas.ingest import (
    IngestTriggerRequest,
    IngestTriggerResponse,
    IngestionRunStats,
)
from fan_zone.schemas.health import HealthResponse, StatsResponse


def test_source_schemas():
    """Test SourceCreate and SourceRead serialization/validation."""
    create = SourceCreate(
        name="sport5",
        display_name="Sport5",
        base_url="https://www.sport5.co.il",
        feed_url="https://www.sport5.co.il/rss.xml",
        poll_interval_seconds=180,
    )
    assert create.name == "sport5"
    assert create.poll_interval_seconds == 180

    now = datetime.now(timezone.utc)
    read = SourceRead(
        id=1,
        name="sport5",
        display_name="Sport5",
        base_url="https://www.sport5.co.il",
        feed_url="https://www.sport5.co.il/rss.xml",
        is_active=True,
        poll_interval_seconds=180,
        code="sport5",
        last_polled_at=now,
        last_success_at=now,
        error_count=0,
        created_at=now,
        updated_at=now,
    )
    assert read.id == 1
    assert read.code == "sport5"

    summary = SourceSummarySchema.model_validate(read)
    assert summary.id == 1
    assert summary.name == "sport5"

    stat = SourceStatSchema(
        code="sport5",
        name="Sport5",
        total_articles=42,
        error_count=0,
    )
    assert stat.total_articles == 42


def test_media_schemas():
    """Test MediaCreate and MediaRead serialization."""
    media_create = MediaCreate(
        url="https://images.sport5.co.il/pic.jpg",
        media_type=MediaType.IMAGE,
        caption="חגיגות הניצחון",
        credit="עוזי אזולאי",
        is_primary=True,
    )
    assert media_create.url == "https://images.sport5.co.il/pic.jpg"
    assert media_create.is_primary is True

    media_read = MediaRead(
        id=10,
        article_id=5,
        url="https://images.sport5.co.il/pic.jpg",
        media_type=MediaType.IMAGE,
        caption="חגיגות הניצחון",
        credit="עוזי אזולאי",
        is_primary=True,
        is_lead=True,
        position_index=0,
    )
    assert media_read.id == 10
    assert media_read.article_id == 5


def test_tag_schemas():
    """Test TagCreate and TagRead validation."""
    tag_create = TagCreate(name="מכבי חיפה", tag_type=TagType.TEAM)
    assert tag_create.name == "מכבי חיפה"
    assert tag_create.tag_type == TagType.TEAM

    now = datetime.now(timezone.utc)
    tag_read = TagRead(
        id=1,
        name="מכבי חיפה",
        slug="maccabi-haifa",
        tag_type=TagType.TEAM,
        article_count=12,
        created_at=now,
    )
    assert tag_read.slug == "maccabi-haifa"
    assert tag_read.article_count == 12


def test_article_schemas():
    """Test Article schemas and pagination container."""
    now = datetime.now(timezone.utc)
    create = ArticleCreate(
        source_id=1,
        canonical_url="https://one.co.il/article/1",
        original_title="מכבי תל אביב",
        published_at=now,
        raw_paragraphs=["פסקה ראשונה"],
        sport="כדורגל",
    )
    assert create.source_id == 1
    assert create.sport == "כדורגל"

    create_none_pub = ArticleCreate(
        source_id=1,
        canonical_url="https://one.co.il/article/2",
        original_title="מכבי חיפה",
        raw_paragraphs=["פסקה ראשונה"],
    )
    assert create_none_pub.published_at is None

    summary = ArticleSummarySchema(
        id=100,
        source_id=1,
        canonical_url="https://one.co.il/article/1",
        original_title="מכבי תל אביב",
        published_at=now,
        sport="כדורגל",
        teams=["מכבי תל אביב"],
        ingestion_status=IngestionStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    assert summary.id == 100
    assert summary.teams == ["מכבי תל אביב"]

    paginated = PaginatedArticleResponse(
        items=[summary],
        total=1,
        page=1,
        page_size=20,
        total_pages=1,
        has_next=False,
        has_prev=False,
    )
    assert len(paginated.items) == 1
    assert paginated.total == 1

    filter_obj = ArticleFilter(
        sport="כדורגל",
        team="מכבי תל אביב",
        skip=0,
        limit=10,
    )
    assert filter_obj.sport == "כדורגל"
    assert filter_obj.limit == 10


def test_ingest_and_health_schemas():
    """Test ingestion trigger, stats, and health schemas."""
    req = IngestTriggerRequest(url="https://sport5.co.il/1", force_ai=True)
    assert req.url == "https://sport5.co.il/1"
    assert req.force_ai is True

    resp = IngestTriggerResponse(
        status="success",
        message="Article ingested",
        articles_ingested=1,
        article_id=45,
    )
    assert resp.articles_ingested == 1

    run_stats = IngestionRunStats(
        total_discovered=10,
        total_ingested=8,
        total_skipped=2,
        total_errors=0,
        source_counts={"sport5": 8},
    )
    assert run_stats.total_ingested == 8

    now = datetime.now(timezone.utc)
    health = HealthResponse(
        status="healthy",
        database="connected",
        scheduler_running=True,
        timestamp=now,
    )
    assert health.status == "healthy"
    assert health.scheduler_running is True
