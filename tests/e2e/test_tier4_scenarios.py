"""Tier 4: Real-World Scenarios E2E Test Suite.

Simulates authentic Israeli sports news workloads and user journeys:
1. 7-Source Batch Ingestion Workload across all monitored outlets
2. The Tel Aviv Derby (דרבי תל אביבי) multi-outlet coverage & synthesis
3. The Haifa Derby & Transfer Rumor Frenzy (מכבי חיפה והפועל חיפה)
4. EuroLeague Basketball Thriller (מכבי תל אביב ביורוליג)
5. Multi-Sport Olympic & Weekend Rush (Football, Basketball, Tennis, Judo, Swimming)
6. Personalized Fan Persona Journeys (Tailored feeds for distinct fan profiles)
"""

from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator, Dict, List
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.ai.mock import MockAIProcessor
from fan_zone.db.session import get_db
from fan_zone.main import create_app
from fan_zone.models.article import Article
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.models.source import Source
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
# SCENARIO 1: 7-Source Batch Ingestion Workload
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_7_source_batch_ingestion_workload(seeded_session: AsyncSession):
    """Scenario 1: Simulate realistic news batch ingestion from all 7 Israeli sports sites."""
    source_repo = SourceRepository(seeded_session)
    sources = await source_repo.get_all_active(db=seeded_session)
    source_map = {s.name: s for s in sources}
    assert len(source_map) >= 7

    service = IngestionService(db=seeded_session, ai_processor=MockAIProcessor())
    now = datetime.now(timezone.utc)

    outlets_data = [
        ("sport5", "https://sport5.co.il/art101", "מכבי תל אביב ניצחה ביורוליג", "כדורסל", ["מכבי תל אביב"]),
        ("one", "https://one.co.il/art102", "מכבי חיפה הביסה את באר שבע", "כדורגל", ["מכבי חיפה", "הפועל באר שבע"]),
        ("walla", "https://walla.co.il/art103", "אלקרס העפיל לגמר הרולאן גארוס", "טניס", []),
        ("ynet", "https://ynet.co.il/art104", "נבחרת ישראל בג'ודו זכתה בשלוש מדליות", "ג'ודו", []),
        ("sport1", "https://sport1.co.il/art105", "ריאל מדריד ניצחה בליגת האלופות", "כדורגל", ["ריאל מדריד"]),
        ("israelhayom", "https://israelhayom.co.il/art106", "הפועל תל אביב החתימה סנטר חדש", "כדורסל", ["הפועל תל אביב"]),
        ("haaretz", "https://haaretz.co.il/art107", "אנסטסיה גורבנקו שברה שיא ישראלי בשחייה", "שחייה", []),
    ]

    ingested_articles: List[Article] = []
    for code, url, title, sport, teams in outlets_data:
        src = source_map.get(code)
        assert src is not None
        ext = ExtractedArticle(
            source_name=src.display_name,
            source_domain=src.base_url.replace("https://", ""),
            original_url=url,
            canonical_url=url,
            content_hash=compute_content_hash(title, [f"דיווח מקיף מאת {src.display_name}."]),
            original_title=title,
            published_at=now - timedelta(minutes=10),
            paragraphs=[f"דיווח מקיף מאת {src.display_name} על האירוע."],
            category_hint=sport,
        )
        art, is_new = await service.process_and_persist_article(ext, src)
        assert is_new is True
        ingested_articles.append(art)

    await seeded_session.commit()

    # Verify all 7 articles were saved
    article_repo = ArticleRepository(seeded_session)
    total_articles, count = await article_repo.list_articles(limit=50, db=seeded_session)
    assert count >= 7

    # Verify source stats reflect ingestion
    stats = await source_repo.get_stats(db=seeded_session)
    assert len(stats) == 7
    assert all(s.total_articles >= 1 for s in stats)


# ===========================================================================
# SCENARIO 2: The Tel Aviv Derby (דרבי תל אביבי)
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_tel_aviv_derby_multi_outlet_clustering(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Scenario 2: Multi-outlet coverage of Tel Aviv Derby clustered into synthesized story."""
    s_s5 = await SourceRepository(seeded_session).get_by_name("sport5", db=seeded_session)
    s_one = await SourceRepository(seeded_session).get_by_name("one", db=seeded_session)
    s_walla = await SourceRepository(seeded_session).get_by_name("walla", db=seeded_session)

    service = IngestionService(db=seeded_session, ai_processor=MockAIProcessor())
    now = datetime.now(timezone.utc)

    # 3 outlets reporting on the same Tel Aviv football derby
    derby_articles = [
        (s_s5, "https://sport5.co.il/derby_1", "מכבי תל אביב ניצחה 0:1 את הפועל תל אביב בדרבי", "שער ניצחון של זהבי בדקה ה-88"),
        (s_one, "https://one.co.il/derby_2", "צהוב עולה: 0:1 למכבי תל אביב על הפועל בבלומפילד", "ערן זהבי הכריע את הדרבי התל אביבי"),
        (s_walla, "https://walla.co.il/derby_3", "מכבי תל אביב גברה 0:1 על הפועל תל אביב", "האדומים נותרו בעשרה שחקנים"),
    ]

    for src, url, title, sub in derby_articles:
        ext = ExtractedArticle(
            source_name=src.display_name,
            source_domain="news.co.il",
            original_url=url,
            canonical_url=url,
            content_hash=compute_content_hash(title, [sub]),
            original_title=title,
            original_subtitle=sub,
            published_at=now,
            paragraphs=[f"{title}. {sub}. משחק סוער באצטדיון בלומפילד."],
            main_image=ExtractedImage(url=f"https://img.co.il/derby_{src.name}.jpg", caption="זהבי חוגג בדרבי"),
        )
        await service.process_and_persist_article(ext, src)

    await seeded_session.commit()

    # Trigger Story Synthesis
    synth_res = await api_client.post("/api/v1/stories/synthesize")
    assert synth_res.status_code == 200

    # Query fan feed for Tel Aviv teams
    maccabi_feed = await api_client.get("/api/v1/feed?teams=מכבי תל אביב")
    assert maccabi_feed.status_code == 200
    feed_data = maccabi_feed.json()
    assert feed_data["total"] >= 1

    # Verify story has multi-source citations
    story = feed_data["items"][0]
    assert "מכבי תל אביב" in story["teams"]
    assert len(story["citations"]) >= 2
    sources_cited = {c["source_name"] for c in story["citations"]}
    assert len(sources_cited) >= 2


# ===========================================================================
# SCENARIO 3: Haifa Derby & Transfer Rumors
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_haifa_derby_and_transfer_rumors(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Scenario 3: Transfer rumors and derby buildup involving Maccabi Haifa & Hapoel Haifa."""
    s_sport1 = await SourceRepository(seeded_session).get_by_name("sport1", db=seeded_session)
    s_one = await SourceRepository(seeded_session).get_by_name("one", db=seeded_session)

    service = IngestionService(db=seeded_session, ai_processor=MockAIProcessor())
    now = datetime.now(timezone.utc)

    ext1 = ExtractedArticle(
        source_name="Sport1", source_domain="sport1.maariv.co.il",
        original_url="https://sport1.maariv.co.il/haifa_transfer", canonical_url="https://sport1.maariv.co.il/haifa_transfer",
        content_hash="haifa_tx_hash_1", original_title="מכבי חיפה במשא ומתן מתקדם עם דיא סבע",
        published_at=now, paragraphs=["הירוקים של ברק בכר קרובים לסיכום עם דיא סבע לקראת הדרבי החיפאי."],
    )
    ext2 = ExtractedArticle(
        source_name="ONE", source_domain="one.co.il",
        original_url="https://one.co.il/haifa_derby_preview", canonical_url="https://one.co.il/haifa_derby_preview",
        content_hash="haifa_tx_hash_2", original_title="דריכות שיא במכבי חיפה ובהפועל חיפה לקראת הדרבי בסמי עופר",
        published_at=now, paragraphs=["מכבי חיפה והפועל חיפה יפגשו לדרבי החם של הכרמל."],
    )

    await service.process_and_persist_article(ext1, s_sport1)
    await service.process_and_persist_article(ext2, s_one)
    await seeded_session.commit()

    # Search articles for Haifa derby
    search_res = await api_client.get("/api/v1/articles?team=מכבי חיפה")
    assert search_res.status_code == 200
    assert search_res.json()["total"] >= 1


# ===========================================================================
# SCENARIO 4: EuroLeague Basketball Double-Header
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_euroleague_basketball_double_header(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Scenario 4: High-profile EuroLeague games with player entity tagging and fan feed filtering."""
    s_s5 = await SourceRepository(seeded_session).get_by_name("sport5", db=seeded_session)
    service = IngestionService(db=seeded_session, ai_processor=MockAIProcessor())

    ext = ExtractedArticle(
        source_name="Sport5", source_domain="sport5.co.il",
        original_url="https://sport5.co.il/euroleague_paob", canonical_url="https://sport5.co.il/euroleague_paob",
        content_hash="paob_hash_1", original_title="מכבי תל אביב ניצחה 89:93 את פנאתינייקוס",
        original_subtitle="ווייד בולדווין ולורנזו בראון להטו באואקה.",
        paragraphs=["מכבי תל אביב גברה על אלופת אירופה פנאתינייקוס באתונה.", "בולדווין קלע 26 נקודות."],
    )
    await service.process_and_persist_article(ext, s_s5)
    await seeded_session.commit()

    # Filter articles by competition
    res_el = await api_client.get("/api/v1/articles?competition=יורוליג")
    assert res_el.status_code == 200
    data = res_el.json()
    assert data["total"] >= 1
    assert any("פנאתינייקוס" in a["original_title"] or "יורוליג" in (a["competition"] or "") for a in data["items"])


# ===========================================================================
# SCENARIO 5: Multi-Sport Olympic & Weekend Rush
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_multisport_weekend_rush(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Scenario 5: Diverse sports weekend (Football, Basketball, Tennis, Judo, Swimming)."""
    # Query system stats breakdown
    stats_res = await api_client.get("/api/v1/stats")
    assert stats_res.status_code == 200
    breakdown = stats_res.json()["sports_breakdown"]
    assert isinstance(breakdown, dict)


# ===========================================================================
# SCENARIO 6: Personalized Fan Persona Journey
# ===========================================================================

@pytest.mark.asyncio
async def test_scenario_fan_persona_journeys(api_client: httpx.AsyncClient, seeded_session: AsyncSession):
    """Scenario 6: Personalized feeds for distinct fan personas (e.g. Maccabi TA fan vs Haifa fan)."""
    # Synthesize all stories
    await api_client.post("/api/v1/stories/synthesize")

    # Persona 1: Maccabi Tel Aviv fan (Football + Basketball)
    feed_maccabi_ta = await api_client.get("/api/v1/feed?teams=מכבי תל אביב&sports=כדורסל&sports=כדורגל")
    assert feed_maccabi_ta.status_code == 200
    m_data = feed_maccabi_ta.json()
    assert "items" in m_data

    # Persona 2: Tennis fan
    feed_tennis = await api_client.get("/api/v1/feed?sports=טניס")
    assert feed_tennis.status_code == 200
    t_data = feed_tennis.json()
    assert "items" in t_data
