"""Integration tests for all FastAPI REST API v1 endpoints."""

from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.ai.mock import MockAIProcessor
from fan_zone.db.session import get_db
from fan_zone.main import create_app
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.repositories.story_repo import StoryRepository
from fan_zone.schemas.article import ArticleCreate
from fan_zone.schemas.media import MediaCreate


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


@pytest_asyncio.fixture
async def populated_db(seeded_session: AsyncSession) -> AsyncSession:
    """Populates test database with rich Israeli sports articles, media, and entity tags."""
    source_repo = SourceRepository(seeded_session)
    sport5 = await source_repo.get_by_name("sport5", db=seeded_session)
    one = await source_repo.get_by_name("one", db=seeded_session)
    walla = await source_repo.get_by_name("walla", db=seeded_session)

    article_repo = ArticleRepository(seeded_session)
    now = datetime.now(timezone.utc)

    # Article 1: Basketball / Maccabi TA / Euroleague / Sport5
    await article_repo.upsert_article(
        article_data=ArticleCreate(
            source_id=sport5.id,
            canonical_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=101",
            original_title="מכבי תל אביב ניצחה 85:82 את ריאל מדריד ביורוליג",
            original_subtitle="משחק מותח בהיכל מנורה מבטחים.",
            author="רועי כהן",
            published_at=now - timedelta(hours=2),
            raw_paragraphs=[
                "מכבי תל אביב השיגה ניצחון דרמטי על ריאל מדריד בהיכל.",
                "ווייד בולדווין להט עם 28 נקודות ומסר 6 אסיסטים.",
            ],
            cleaned_body="מכבי תל אביב השיגה ניצחון דרמטי על ריאל מדריד בהיכל. ווייד בולדווין להט עם 28 נקודות ומסר 6 אסיסטים.",
            ai_headline="מכבי תל אביב גברה 82:85 על ריאל מדריד ביורוליג",
            ai_subheadline="בולדווין קלע 28 נקודות והוביל את הצהובים לניצחון ביתי יוקרתי.",
            sport="כדורסל",
            competition="יורוליג",
            teams_json=["מכבי תל אביב", "ריאל מדריד"],
            players_json=["ווייד בולדווין", "עודד קטש"],
            tags_json=["יורוליג", "כדורסל", "מכבי תל אביב"],
            ingestion_status=IngestionStatus.AI_PROCESSED,
        ),
        media_data=[
            MediaCreate(
                url="https://sport5.co.il/img/baldwin.jpg",
                caption="בולדווין חוגג",
                credit="אלן שיבר",
                is_primary=True,
                position_index=0,
            ),
            MediaCreate(
                url="https://sport5.co.il/img/katash.jpg",
                caption="קטש מתדרך",
                credit="ברני ארדוב",
                is_primary=False,
                position_index=1,
            ),
        ],
        tag_names=[
            ("כדורסל", TagType.SPORT),
            ("יורוליג", TagType.COMPETITION),
            ("מכבי תל אביב", TagType.TEAM),
            ("ריאל מדריד", TagType.TEAM),
            ("ווייד בולדווין", TagType.PLAYER),
        ],
        db=seeded_session,
    )

    # Article 2: Football / Maccabi Haifa / Premier League / ONE
    await article_repo.upsert_article(
        article_data=ArticleCreate(
            source_id=one.id,
            canonical_url="https://www.one.co.il/Article/202",
            original_title="מכבי חיפה הביסה 0:3 את הפועל באר שבע בסמי עופר",
            original_subtitle="דיא סבע כיכב עם צמד ובישול.",
            author="גידי ליפקין",
            published_at=now - timedelta(hours=5),
            raw_paragraphs=[
                "מכבי חיפה הרשימה הערב באצטדיון סמי עופר עם הצגה גדולה מול הפועל באר שבע.",
                "דיא סבע כבש צמד שערים בדרך ל-0:3 משכנע.",
            ],
            cleaned_body="מכבי חיפה הרשימה הערב באצטדיון סמי עופר עם הצגה גדולה מול הפועל באר שבע.",
            ai_headline="מכבי חיפה ניצחה 0:3 את הפועל באר שבע בליגת העל",
            ai_subheadline="צמד של דיא סבע העניק לירוקים ניצחון מוחץ בסמי עופר.",
            sport="כדורגל",
            competition="ליגת העל",
            teams_json=["מכבי חיפה", "הפועל באר שבע"],
            players_json=["דיא סבע", "ברק בכר"],
            tags_json=["ליגת העל", "כדורגל", "מכבי חיפה"],
            ingestion_status=IngestionStatus.AI_PROCESSED,
        ),
        media_data=[
            MediaCreate(
                url="https://one.co.il/img/saba.jpg",
                caption="דיא סבע חוגג צמד",
                credit="רדאד ג'בארה",
                is_primary=True,
                position_index=0,
            ),
        ],
        tag_names=[
            ("כדורגל", TagType.SPORT),
            ("ליגת העל", TagType.COMPETITION),
            ("מכבי חיפה", TagType.TEAM),
            ("הפועל באר שבע", TagType.TEAM),
            ("דיא סבע", TagType.PLAYER),
        ],
        db=seeded_session,
    )

    # Article 3: Tennis / Roland Garros / Walla
    await article_repo.upsert_article(
        article_data=ArticleCreate(
            source_id=walla.id,
            canonical_url="https://sports.walla.co.il/item/303",
            original_title="קרלוס אלקרס העפיל לגמר הרולאן גארוס",
            original_subtitle="ניצחון בחמש מערכות על סינר.",
            author="מערכת וואלה!",
            published_at=now - timedelta(days=1),
            raw_paragraphs=[
                "קרלוס אלקרס הספרדי גבר על יאניק סינר בחצי גמר הרולאן גארוס בפריז.",
            ],
            cleaned_body="קרלוס אלקרס הספרדי גבר על יאניק סינר בחצי גמר הרולאן גארוס בפריז.",
            ai_headline="קרלוס אלקרס עלה לגמר הרולאן גארוס לאחר ניצחון על סינר",
            ai_subheadline="הספרדי ניצח בחמש מערכות וישחק בגמר הגראנד סלאם בפריז.",
            sport="טניס",
            competition="רולאן גארוס",
            teams_json=[],
            players_json=["קרלוס אלקרס", "יאניק סינר"],
            tags_json=["טניס", "רולאן גארוס", "גראנד סלאם"],
            ingestion_status=IngestionStatus.AI_PROCESSED,
        ),
        tag_names=[
            ("טניס", TagType.SPORT),
            ("רולאן גארוס", TagType.COMPETITION),
            ("קרלוס אלקרס", TagType.PLAYER),
        ],
        db=seeded_session,
    )

    await seeded_session.commit()
    return seeded_session


# ---------------------------------------------------------------------------
# 1. System, Health and Stats Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_check_endpoint(api_client: httpx.AsyncClient):
    """Verify GET /api/v1/health returns healthy service status."""
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "scheduler_running" in data
    assert "timestamp" in data
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_root_endpoint_and_health_alias(api_client: httpx.AsyncClient):
    """Verify root / and /health convenience endpoints."""
    res_root = await api_client.get("/")
    assert res_root.status_code == 200
    assert "docs" in res_root.json()

    res_alias = await api_client.get("/health")
    assert res_alias.status_code == 200
    assert res_alias.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_system_stats_endpoint(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify GET /api/v1/stats returns accurate aggregated metrics."""
    response = await api_client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_articles"] == 3
    assert data["ai_processed_count"] == 3
    assert data["ai_pending_count"] == 0
    assert data["failed_count"] == 0
    assert "כדורסל" in data["sports_breakdown"]
    assert "כדורגל" in data["sports_breakdown"]
    assert "טניס" in data["sports_breakdown"]
    assert len(data["sources_stats"]) >= 7


# ---------------------------------------------------------------------------
# 2. Sources Endpoints Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_sources_endpoint(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify GET /api/v1/sources lists all 7 Israeli sports sources."""
    response = await api_client.get("/api/v1/sources")
    assert response.status_code == 200
    sources = response.json()
    assert len(sources) == 7

    codes = {s["code"] for s in sources}
    assert {"sport5", "one", "walla", "ynet", "sport1", "israelhayom", "haaretz"}.issubset(codes)

    # Check article counts
    sport5_stat = next(s for s in sources if s["code"] == "sport5")
    assert sport5_stat["total_articles"] == 1


@pytest.mark.asyncio
async def test_get_source_by_code_and_id(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify GET /api/v1/sources/{id_or_code} resolves by code and numeric ID."""
    # Lookup by code
    res_code = await api_client.get("/api/v1/sources/sport5")
    assert res_code.status_code == 200
    data = res_code.json()
    assert data["name"] == "sport5"
    assert data["display_name"] == "Sport5"
    source_id = data["id"]

    # Lookup by ID
    res_id = await api_client.get(f"/api/v1/sources/{source_id}")
    assert res_id.status_code == 200
    assert res_id.json()["id"] == source_id

    # Nonexistent source
    res_404 = await api_client.get("/api/v1/sources/unknown_outlet_xyz")
    assert res_404.status_code == 404


# ---------------------------------------------------------------------------
# 3. Tags Endpoints Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tags_endpoint(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify GET /api/v1/tags with search and type filters."""
    response = await api_client.get("/api/v1/tags")
    assert response.status_code == 200
    tags = response.json()
    assert len(tags) >= 5

    # Filter by tag_type
    res_teams = await api_client.get("/api/v1/tags?type=team")
    assert res_teams.status_code == 200
    teams = res_teams.json()
    assert all(t["tag_type"] == "team" for t in teams)
    team_names = {t["name"] for t in teams}
    assert "מכבי תל אביב" in team_names
    assert "מכבי חיפה" in team_names

    # Substring search
    res_search = await api_client.get("/api/v1/tags?q=חיפה")
    assert res_search.status_code == 200
    search_tags = res_search.json()
    assert any("חיפה" in t["name"] for t in search_tags)


@pytest.mark.asyncio
async def test_popular_tags_endpoint(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify GET /api/v1/tags/popular returns top ranked tags."""
    response = await api_client.get("/api/v1/tags/popular?limit=5")
    assert response.status_code == 200
    tags = response.json()
    assert len(tags) <= 5
    assert len(tags) > 0


# ---------------------------------------------------------------------------
# 4. Articles Search, Filter and Detail Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_articles_pagination(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify GET /api/v1/articles pagination metadata and response container."""
    response = await api_client.get("/api/v1/articles?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 2
    assert data["has_next"] is True
    assert data["has_prev"] is False
    assert len(data["items"]) == 2

    # Second page
    res_page2 = await api_client.get("/api/v1/articles?page=2&page_size=2")
    assert res_page2.status_code == 200
    data2 = res_page2.json()
    assert data2["page"] == 2
    assert data2["has_next"] is False
    assert data2["has_prev"] is True
    assert len(data2["items"]) == 1


@pytest.mark.asyncio
async def test_filter_articles_by_sport(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify filtering articles by sport category."""
    response = await api_client.get("/api/v1/articles?sport=כדורסל")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["sport"] == "כדורסל"
    assert "מכבי תל אביב" in data["items"][0]["original_title"]


@pytest.mark.asyncio
async def test_filter_articles_by_team(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify filtering articles by team name."""
    response = await api_client.get("/api/v1/articles?team=מכבי חיפה")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "מכבי חיפה" in data["items"][0]["teams"]


@pytest.mark.asyncio
async def test_filter_articles_by_competition(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify filtering articles by competition/league."""
    response = await api_client.get("/api/v1/articles?competition=יורוליג")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["competition"] == "יורוליג"


@pytest.mark.asyncio
async def test_filter_articles_by_source(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify filtering articles by source name."""
    response = await api_client.get("/api/v1/articles?source=one")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["source"]["name"] == "one"


@pytest.mark.asyncio
async def test_filter_articles_hebrew_search(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify Hebrew keyword search query matching headline, title, or body."""
    response = await api_client.get("/api/v1/articles?q=בולדווין")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "בולדווין" in data["items"][0]["ai_subheadline"] or "בולדווין" in data["items"][0]["original_title"]


@pytest.mark.asyncio
async def test_get_article_detail_and_media(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify GET /api/v1/articles/{id} returns complete body, media items, and tag taxonomy."""
    # Find article 1 ID
    list_res = await api_client.get("/api/v1/articles?sport=כדורסל")
    article_id = list_res.json()["items"][0]["id"]

    response = await api_client.get(f"/api/v1/articles/{article_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == article_id
    assert detail["sport"] == "כדורסל"
    assert len(detail["paragraphs"]) >= 2
    assert len(detail["media"]) == 2
    assert detail["media"][0]["caption"] == "בולדווין חוגג"
    assert detail["media"][0]["credit"] == "אלן שיבר"
    assert len(detail["tags_detail"]) >= 3

    # Nonexistent article ID
    res_404 = await api_client.get("/api/v1/articles/999999")
    assert res_404.status_code == 404


# ---------------------------------------------------------------------------
# 5. Ingestion Trigger and Status Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_trigger_single_url(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify POST /api/v1/ingest/trigger for a single article URL."""
    sample_url = "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=99999"
    with patch(
        "fan_zone.services.ingestion_service.IngestionService.ingest_url",
        new_callable=AsyncMock,
    ) as mock_ingest_url:
        mock_article = AsyncMock()
        mock_article.id = 77
        mock_ingest_url.return_value = (mock_article, True)

        payload = {"url": sample_url, "source_name": "sport5"}
        response = await api_client.post("/api/v1/ingest/trigger", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["articles_ingested"] == 1
        assert data["article_id"] == 77


@pytest.mark.asyncio
async def test_ingest_trigger_source_polling(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Verify POST /api/v1/ingest/trigger for a specific source."""
    with patch(
        "fan_zone.services.ingestion_service.IngestionService.ingest_source",
        new_callable=AsyncMock,
    ) as mock_ingest_source:
        mock_ingest_source.return_value = AsyncMock(
            total_processed=5,
            total_ingested=3,
            total_skipped=2,
            total_failed=0,
            total_errors=0,
        )

        payload = {"source_name": "one"}
        response = await api_client.post("/api/v1/ingest/trigger", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["articles_ingested"] == 3


@pytest.mark.asyncio
async def test_ingest_status_endpoint(api_client: httpx.AsyncClient):
    """Verify GET /api/v1/ingest/status returns runtime status."""
    response = await api_client.get("/api/v1/ingest/status")
    assert response.status_code == 200
    data = response.json()
    assert "scheduler_running" in data
    assert "poll_interval_seconds" in data
    assert "run_count" in data


# ---------------------------------------------------------------------------
# 6. Stories & Personalized Fan Feed Tests (Synthesis-First Architecture)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_story_synthesis_and_listing_endpoints(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify POST /api/v1/stories/synthesize and GET /api/v1/stories endpoints."""
    # 1. Trigger synthesis
    synth_res = await api_client.post("/api/v1/stories/synthesize")
    assert synth_res.status_code == 200
    synth_data = synth_res.json()
    assert synth_data["status"] == "success"
    assert synth_data["stories_created"] >= 3

    # 2. List synthesized stories
    stories_res = await api_client.get("/api/v1/stories")
    assert stories_res.status_code == 200
    stories_data = stories_res.json()
    assert stories_data["total"] >= 3
    assert len(stories_data["items"]) >= 3

    # Verify first story has citations and entity tags
    first_story = stories_data["items"][0]
    assert "title" in first_story
    assert "summary" in first_story
    assert "citations" in first_story
    assert len(first_story["citations"]) >= 1
    assert "url" in first_story["citations"][0]
    assert "source_name" in first_story["citations"][0]

    # 3. Get single story detail
    story_id = first_story["id"]
    detail_res = await api_client.get(f"/api/v1/stories/{story_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["id"] == story_id
    assert detail_data["title"] == first_story["title"]

    # 4. Filter stories by sport
    bball_res = await api_client.get("/api/v1/stories?sport=כדורסל")
    assert bball_res.status_code == 200
    assert bball_res.json()["total"] >= 1
    assert bball_res.json()["items"][0]["sport"] == "כדורסל"


@pytest.mark.asyncio
async def test_personalized_fan_feed_endpoint(api_client: httpx.AsyncClient, populated_db: AsyncSession):
    """Verify GET /api/v1/feed with multi-select fan preference filters."""
    # Synthesize stories first
    await api_client.post("/api/v1/stories/synthesize")

    # Feed without filters
    feed_all = await api_client.get("/api/v1/feed")
    assert feed_all.status_code == 200
    assert feed_all.json()["total"] >= 3

    # Feed filtered by favorite team
    feed_team = await api_client.get("/api/v1/feed?teams=מכבי תל אביב")
    assert feed_team.status_code == 200
    team_data = feed_team.json()
    assert team_data["total"] >= 1
    assert any("מכבי תל אביב" in s["teams"] for s in team_data["items"])

    # Feed filtered by multi-sports
    feed_sports = await api_client.get("/api/v1/feed?sports=כדורסל&sports=טניס")
    assert feed_sports.status_code == 200
    sports_data = feed_sports.json()
    assert sports_data["total"] >= 2
    assert all(s["sport"] in ["כדורסל", "טניס"] for s in sports_data["items"])
