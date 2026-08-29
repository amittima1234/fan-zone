"""Tier 3: Cross-Feature Combinations E2E Test Suite.

Verifies pairwise and multi-feature end-to-end interactions across the platform:
1. Ingestion Pipeline: Scraper -> Deduplication -> AI Tagging -> Persistence
2. Idempotent Ingestion: Re-Ingest -> URL/Hash Match -> Skip AI -> Return Existing
3. Multi-Source Ingestion: Per-source deduplication across different outlets
4. Ingestion to REST API: Ingest -> AI Tag -> Query via REST with complex filters
5. Ingestion to Story Clustering: Multi-source articles clustered into Story with citations
6. Story Synthesis to Personalized Fan Feed: Clustered stories surfaced in fan feed
7. Ingestion Trigger to Telemetry: Ingestion trigger updates source stats & system metrics
8. AI Failure Cascade to REST Detail: Failing AI persists with fallback & exposes via API
9. Ingestion to Tag Aggregation: Ingest multiple articles -> verify popular tags ranking
10. Complete End-to-End System Cycle: Ingest -> Process -> Cluster -> Fan Feed -> Outbound Citations
"""

from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.ai.mock import MockAIProcessor
from fan_zone.db.session import get_db
from fan_zone.main import create_app
from fan_zone.models.article import Article, ArticleMedia
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.models.source import Source
from fan_zone.models.story import Story
from fan_zone.models.tag import ArticleTag, Tag
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.repositories.story_repo import StoryRepository
from fan_zone.repositories.tag_repo import TagRepository
from fan_zone.schemas.article import ArticleCreate
from fan_zone.schemas.media import MediaCreate
from fan_zone.scrapers.base import ExtractedArticle, ExtractedImage, compute_content_hash
from fan_zone.services.ingestion_service import IngestionService
from fan_zone.services.story_service import StoryService


@pytest_asyncio.fixture
async def api_client(seeded_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """FastAPI async test client with database dependency override to in-memory test session."""
    app = create_app()

    async def override_get_db():
        yield seeded_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Pipeline 1: Scraper -> Deduplication -> AI Tagging -> Persistence
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_scraper_to_persistence(db_session: AsyncSession):
    """Verify full linear pipeline from extracted article to rich DB relations."""
    source_repo = SourceRepository(db_session)
    sources = await source_repo.seed_default_sources()
    s_sport5 = next(s for s in sources if s.name == "sport5")

    ai_processor = MockAIProcessor()
    service = IngestionService(db=db_session, ai_processor=ai_processor)

    ext = ExtractedArticle(
        source_name="Sport5",
        source_domain="sport5.co.il",
        original_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=8001",
        canonical_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=8001",
        content_hash=compute_content_hash("ניצחון ענק ביורוליג", ["פסקה 1", "פסקה 2"]),
        original_title="ניצחון ענק ביורוליג למכבי תל אביב",
        original_subtitle="ווייד בולדווין להט",
        author="רועי כהן",
        published_at=datetime.now(timezone.utc),
        paragraphs=["מכבי תל אביב השיגה ניצחון יוקרתי על ריאל מדריד ביורוליג.", "ווייד בולדווין הצטיין."],
        main_image=ExtractedImage(url="https://sport5.co.il/img_lead.jpg", caption="בולדווין חוגג", is_main=True),
        tags=["יורוליג"],
    )

    art, created = await service.process_and_persist_article(ext, s_sport5)
    assert created is True
    assert art is not None
    assert art.ingestion_status == IngestionStatus.AI_PROCESSED
    assert art.sport == "כדורסל"
    assert "מכבי תל אביב" in art.teams_json
    assert len(art.media) == 1
    assert art.media[0].is_primary is True

    # Verify Tag repository associations
    tag_repo = TagRepository(db_session)
    tags = await tag_repo.get_tags_for_article(art.id, db=db_session)
    assert len(tags) >= 2
    tag_names = {t.name for t in tags}
    assert "כדורסל" in tag_names or "מכבי תל אביב" in tag_names


# ===========================================================================
# 2. Pipeline 2: Idempotent Re-Ingestion (Skip AI & Return Existing)
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_idempotent_reingestion(db_session: AsyncSession):
    """Verify re-ingesting the exact same article skips AI calls and returns existing article."""
    source_repo = SourceRepository(db_session)
    sources = await source_repo.seed_default_sources()
    s_one = next(s for s in sources if s.name == "one")

    ai_processor = MockAIProcessor()
    service = IngestionService(db=db_session, ai_processor=ai_processor)

    ext = ExtractedArticle(
        source_name="ONE",
        source_domain="one.co.il",
        original_url="https://www.one.co.il/Article/2026/9001.html",
        canonical_url="https://www.one.co.il/Article/2026/9001.html",
        content_hash=compute_content_hash("כותרת ONE", ["פסקה 1"]),
        original_title="כותרת ONE",
        paragraphs=["פסקה 1"],
    )

    # First ingestion
    art1, created1 = await service.process_and_persist_article(ext, s_one)
    assert created1 is True
    assert ai_processor.call_count == 1

    # Second ingestion
    art2, created2 = await service.process_and_persist_article(ext, s_one)
    assert created2 is False
    assert art2.id == art1.id
    # AI processor should NOT be invoked again
    assert ai_processor.call_count == 1


# ===========================================================================
# 3. Pipeline 3: Multi-Source Same Event (Per-Source Deduplication)
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_multisource_per_source_deduplication(db_session: AsyncSession):
    """Verify Sport5, ONE, and Walla reports on the same match are all ingested independently."""
    source_repo = SourceRepository(db_session)
    sources = await source_repo.seed_default_sources()
    s_sport5 = next(s for s in sources if s.name == "sport5")
    s_one = next(s for s in sources if s.name == "one")
    s_walla = next(s for s in sources if s.name == "walla")

    service = IngestionService(db=db_session, ai_processor=MockAIProcessor())
    shared_title = "מכבי חיפה ניצחה 0:3 את בית\"ר ירושלים"
    shared_paragraphs = ["משחק ענק באצטדיון סמי עופר במסגרת ליגת העל בכדורגל."]
    shared_hash = compute_content_hash(shared_title, shared_paragraphs)

    ext_sport5 = ExtractedArticle(
        source_name="Sport5", source_domain="sport5.co.il",
        original_url="https://sport5.co.il/match_s5", canonical_url="https://sport5.co.il/match_s5",
        content_hash=shared_hash, original_title=shared_title, paragraphs=shared_paragraphs,
    )
    ext_one = ExtractedArticle(
        source_name="ONE", source_domain="one.co.il",
        original_url="https://one.co.il/match_one", canonical_url="https://one.co.il/match_one",
        content_hash=shared_hash, original_title=shared_title, paragraphs=shared_paragraphs,
    )
    ext_walla = ExtractedArticle(
        source_name="Walla! Sports", source_domain="walla.co.il",
        original_url="https://walla.co.il/match_walla", canonical_url="https://walla.co.il/match_walla",
        content_hash=shared_hash, original_title=shared_title, paragraphs=shared_paragraphs,
    )

    art1, c1 = await service.process_and_persist_article(ext_sport5, s_sport5)
    art2, c2 = await service.process_and_persist_article(ext_one, s_one)
    art3, c3 = await service.process_and_persist_article(ext_walla, s_walla)

    assert c1 is True and c2 is True and c3 is True
    assert len({art1.id, art2.id, art3.id}) == 3
    assert {art1.source_id, art2.source_id, art3.source_id} == {s_sport5.id, s_one.id, s_walla.id}


# ===========================================================================
# 4. Pipeline 4: Ingestion -> AI Tagging -> REST API Complex Filter
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_ingestion_to_rest_api_search_and_filters(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify ingested articles are instantly searchable and filterable via REST API."""
    source_repo = SourceRepository(seeded_session)
    s_ynet = await source_repo.get_by_name("ynet", db=seeded_session)

    service = IngestionService(db=seeded_session, ai_processor=MockAIProcessor())
    ext = ExtractedArticle(
        source_name="Ynet Sport",
        source_domain="ynet.co.il",
        original_url="https://ynet.co.il/tennis_final",
        canonical_url="https://ynet.co.il/tennis_final",
        content_hash="tennis_hash_combo",
        original_title="נובאק ג'וקוביץ' זכה בווימבלדון",
        paragraphs=["הטניסאי הסרבי נובאק ג'וקוביץ' ניצח בגמר ווימבלדון בלונדון."],
    )
    await service.process_and_persist_article(ext, s_ynet)
    await seeded_session.commit()

    # Query via REST API
    res = await api_client.get("/api/v1/articles?sport=טניס&q=ג'וקוביץ'")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert any("ג'וקוביץ'" in a["original_title"] or "ג'וקוביץ'" in (a["ai_headline"] or "") for a in data["items"])


# ===========================================================================
# 5. Pipeline 5: Ingestion -> Story Clustering -> Multi-Source Synthesis
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_ingestion_to_story_clustering_and_synthesis(seeded_session: AsyncSession):
    """Verify multiple articles on the same EuroLeague game are clustered into a synthesized Story."""
    s_s5 = await SourceRepository(seeded_session).get_by_name("sport5", db=seeded_session)
    s_one = await SourceRepository(seeded_session).get_by_name("one", db=seeded_session)

    service = IngestionService(db=seeded_session, ai_processor=MockAIProcessor())
    now = datetime.now(timezone.utc)

    ext1 = ExtractedArticle(
        source_name="Sport5", source_domain="sport5.co.il",
        original_url="https://sport5.co.il/euroleague_maccabi", canonical_url="https://sport5.co.il/euroleague_maccabi",
        content_hash="el_hash_1", original_title="מכבי תל אביב גברה 82:85 על ריאל מדריד",
        published_at=now, paragraphs=["מכבי תל אביב ניצחה את ריאל מדריד ביורוליג בכדורסל."],
    )
    ext2 = ExtractedArticle(
        source_name="ONE", source_domain="one.co.il",
        original_url="https://one.co.il/euroleague_maccabi", canonical_url="https://one.co.il/euroleague_maccabi",
        content_hash="el_hash_2", original_title="ניצחון ענק למכבי תל אביב על ריאל מדריד",
        published_at=now, paragraphs=["הצהובים של מכבי תל אביב גברו על ריאל מדריד ביורוליג."],
    )

    art1, _ = await service.process_and_persist_article(ext1, s_s5)
    art2, _ = await service.process_and_persist_article(ext2, s_one)
    await seeded_session.commit()

    # Trigger Story synthesis
    story_service = StoryService(db=seeded_session)
    synth_stats = await story_service.synthesize_all_pending(limit=20)
    assert synth_stats["stories_created"] >= 1

    # Query stories repository
    story_repo = StoryRepository(seeded_session)
    stories, total = await story_repo.list_stories(sport="כדורסל", db=seeded_session)
    assert total >= 1
    target_story = next((s for s in stories if "מכבי תל אביב" in (s.teams_json or [])), None)
    assert target_story is not None
    assert target_story.article_count >= 2
    assert len(target_story.citations_json) >= 2


# ===========================================================================
# 6. Pipeline 6: Story Synthesis -> Personalized Fan Feed API
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_story_synthesis_to_fan_feed_endpoint(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify synthesized multi-source stories are delivered to fan feed with outbound citations."""
    # Synthesize all stories
    synth_res = await api_client.post("/api/v1/stories/synthesize")
    assert synth_res.status_code == 200

    # Query fan feed filtered by favorite team
    feed_res = await api_client.get("/api/v1/feed?teams=מכבי תל אביב")
    assert feed_res.status_code == 200
    feed_data = feed_res.json()
    assert "items" in feed_data
    assert "total" in feed_data
    if feed_data["total"] > 0:
        story_item = feed_data["items"][0]
        assert "title" in story_item
        assert "summary" in story_item
        assert "citations" in story_item
        assert len(story_item["citations"]) >= 1


# ===========================================================================
# 7. Pipeline 7: Ingestion Trigger -> Source Stats -> System Metrics
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_ingest_trigger_to_system_stats_update(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify manual ingestion trigger updates source article count and system metrics."""
    # Get initial stats
    initial_stats = (await api_client.get("/api/v1/stats")).json()
    initial_count = initial_stats["total_articles"]

    # Ingest a new article
    s_walla = await SourceRepository(seeded_session).get_by_name("walla", db=seeded_session)
    service = IngestionService(db=seeded_session, ai_processor=MockAIProcessor())
    ext = ExtractedArticle(
        source_name="Walla! Sports", source_domain="walla.co.il",
        original_url="https://sports.walla.co.il/new_stat_item", canonical_url="https://sports.walla.co.il/new_stat_item",
        content_hash="stat_update_hash", original_title="כתבה חדשה לעדכון סטטיסטיקה",
        paragraphs=["פסקה לעדכון."],
    )
    await service.process_and_persist_article(ext, s_walla)
    await seeded_session.commit()

    # Verify updated stats
    updated_stats = (await api_client.get("/api/v1/stats")).json()
    assert updated_stats["total_articles"] == initial_count + 1


# ===========================================================================
# 8. Pipeline 8: AI Fallback Cascade -> Persistence -> REST Detail View
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_ai_fallback_to_rest_detail_view(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify failing AI processor stores AI_FALLBACK status and renders properly in REST detail."""
    s_haaretz = await SourceRepository(seeded_session).get_by_name("haaretz", db=seeded_session)
    failing_ai = MockAIProcessor(simulate_rate_limit=True)
    service = IngestionService(db=seeded_session, ai_processor=failing_ai)

    ext = ExtractedArticle(
        source_name="Haaretz", source_domain="haaretz.co.il",
        original_url="https://haaretz.co.il/fallback_article", canonical_url="https://haaretz.co.il/fallback_article",
        content_hash="fallback_rest_hash", original_title="כותרת הארץ במצב נפילה",
        original_subtitle="כותרת משנה הארץ",
        paragraphs=["תוכן מלא של הכתבה שנשמר חרף כשל בבינה המלאכותית."],
    )

    art, _ = await service.process_and_persist_article(ext, s_haaretz)
    await seeded_session.commit()

    # Query detail endpoint
    res = await api_client.get(f"/api/v1/articles/{art.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["ingestion_status"] == "AI_FALLBACK"
    assert data["ai_headline"] == "כותרת הארץ במצב נפילה"
    assert len(data["paragraphs"]) >= 1


# ===========================================================================
# 9. Pipeline 9: Ingestion -> Tag Aggregation -> Popular Tags API
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_ingestion_to_popular_tags_ranking(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify popular tags endpoint accurately ranks tags by total article association frequency."""
    repo = ArticleRepository(seeded_session)
    s_sport1 = await SourceRepository(seeded_session).get_by_name("sport1", db=seeded_session)

    # Ingest 3 articles with common tag "ליגת האלופות"
    for i in range(3):
        await repo.upsert_article(
            article_data=ArticleCreate(
                source_id=s_sport1.id,
                canonical_url=f"https://sport1.co.il/cl_{i}",
                content_hash=f"cl_hash_{i}",
                original_title=f"כתבת ליגת האלופות {i}",
                competition="ליגת האלופות",
            ),
            tag_names=[("ליגת האלופות", TagType.COMPETITION), ("ריאל מדריד", TagType.TEAM)],
            db=seeded_session,
        )
    await seeded_session.commit()

    res = await api_client.get("/api/v1/tags/popular?limit=10")
    assert res.status_code == 200
    tags = res.json()
    assert len(tags) > 0
    cl_tag = next((t for t in tags if t["name"] == "ליגת האלופות"), None)
    assert cl_tag is not None
    assert cl_tag["article_count"] >= 3


# ===========================================================================
# 10. Pipeline 10: Complete System Ingestion-to-Fan Journey
# ===========================================================================

@pytest.mark.asyncio
async def test_pipeline_full_fan_journey_end_to_end(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify full end-to-end user lifecycle from multi-source crawling to personalized fan reading."""
    # 1. Trigger story synthesis
    synth_res = await api_client.post("/api/v1/stories/synthesize")
    assert synth_res.status_code == 200

    # 2. Fan requests feed
    feed_res = await api_client.get("/api/v1/feed?page=1&page_size=10")
    assert feed_res.status_code == 200
    feed_items = feed_res.json()["items"]
    assert len(feed_items) >= 1

    # 3. Fan views story detail
    story_id = feed_items[0]["id"]
    story_detail = (await api_client.get(f"/api/v1/stories/{story_id}")).json()
    assert story_detail["id"] == story_id
    assert len(story_detail["citations"]) >= 1

    # 4. Verify outbound citation link format
    citation = story_detail["citations"][0]
    assert citation["url"].startswith("http")
    assert len(citation["publisher"]) > 0
