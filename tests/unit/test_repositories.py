"""Unit tests for SourceRepository, TagRepository, and ArticleRepository."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.models.source import Source
from fan_zone.models.article import Article
from fan_zone.repositories.source_repo import SourceRepository, DEFAULT_SOURCES
from fan_zone.repositories.tag_repo import TagRepository, slugify
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.schemas.source import SourceCreate
from fan_zone.schemas.article import ArticleCreate
from fan_zone.schemas.media import MediaCreate


# ==========================================
# 1. SourceRepository Tests
# ==========================================

@pytest.mark.asyncio
async def test_seed_default_sources(db_session: AsyncSession):
    """Verify seeding creates all 7 default Israeli sports news outlets idempotently."""
    repo = SourceRepository(db_session)
    sources = await repo.seed_default_sources()
    assert len(sources) == 7

    # Names check
    names = {s.name for s in sources}
    assert names == {"sport5", "one", "walla", "ynet", "sport1", "israelhayom", "haaretz"}

    # Re-running seed must be idempotent (0 new items, returns same 7)
    sources_reseed = await repo.seed_default_sources()
    assert len(sources_reseed) == 7
    all_sources = await repo.list_all()
    assert len(all_sources) == 7


@pytest.mark.asyncio
async def test_source_repo_getters_and_status(db_session: AsyncSession):
    """Test lookup by ID, name, code and poll status updates."""
    repo = SourceRepository(db_session)
    source, created = await repo.create_or_get(
        SourceCreate(
            name="custom_source",
            display_name="Custom Source",
            base_url="https://custom.co.il",
            feed_url="https://custom.co.il/rss",
        )
    )
    assert created is True
    assert source.id is not None

    by_id = await repo.get_by_id(source.id)
    assert by_id is not None
    assert by_id.name == "custom_source"

    by_name = await repo.get_by_name("custom_source")
    assert by_name is not None
    assert by_name.id == source.id

    by_code = await repo.get_by_code("CUSTOM_SOURCE")
    assert by_code is not None

    # Test failure status update
    updated_fail = await repo.update_poll_status(source.id, success=False, error_msg="Timeout")
    assert updated_fail.error_count == 1
    assert updated_fail.last_polled_at is not None

    # Test success status update
    updated_success = await repo.update_poll_status(source.id, success=True)
    assert updated_success.error_count == 0
    assert updated_success.last_success_at is not None


@pytest.mark.asyncio
async def test_source_repo_get_stats(db_session: AsyncSession, sample_article_dict: dict):
    """Test get_stats returns per-source article metrics."""
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)

    await source_repo.seed_default_sources()
    source = await source_repo.get_by_name("sport5")
    assert source is not None

    # Insert an article for sport5
    sample_article_dict["source_id"] = source.id
    await article_repo.upsert_article(sample_article_dict)

    stats = await source_repo.get_stats()
    assert len(stats) == 7

    sport5_stat = next(s for s in stats if s.code == "sport5")
    assert sport5_stat.total_articles == 1


# ==========================================
# 2. TagRepository Tests
# ==========================================

@pytest.mark.asyncio
async def test_slugify():
    """Test slug creation for Hebrew and English text."""
    assert slugify("מכבי תל אביב") == "מכבי-תל-אביב"
    assert slugify("ליגת האלופות 2026!") == "ליגת-האלופות-2026"
    assert slugify("Real Madrid CF") == "real-madrid-cf"
    assert slugify("   ג'ודו   ") == "גודו"


@pytest.mark.asyncio
async def test_tag_repo_get_or_create_batch(db_session: AsyncSession):
    """Test single and batch tag creation and deduplication."""
    repo = TagRepository(db_session)

    tag1 = await repo.get_or_create_tag("כדורגל", tag_type=TagType.SPORT)
    assert tag1.id is not None
    assert tag1.name == "כדורגל"
    assert tag1.tag_type == TagType.SPORT

    # Duplicate call should return existing tag
    tag1_dup = await repo.get_or_create_tag("  כדורגל  ", tag_type=TagType.SPORT)
    assert tag1_dup.id == tag1.id

    # Batch creation with duplicates within batch
    batch_tags = [
        ("מכבי תל אביב", TagType.TEAM),
        ("הפועל ירושלים", TagType.TEAM),
        ("כדורסל", TagType.SPORT),
        ("מכבי תל אביב", TagType.TEAM),  # Duplicate
        ("  ", TagType.GENERAL),           # Empty
    ]
    created_tags = await repo.get_or_create_tags(batch_tags)
    assert len(created_tags) == 3

    # Test get_or_create_batch alias with direct tags argument
    alias_batch = await repo.get_or_create_batch([("בית\"ר ירושלים", TagType.TEAM)])
    assert len(alias_batch) == 1
    assert alias_batch[0].name == "בית\"ר ירושלים"

    all_tags = await repo.list_tags()
    # 1 previous + 3 from batch + 1 from alias = 5
    assert len(all_tags) == 5


@pytest.mark.asyncio
async def test_tag_repo_filtering_and_popular(db_session: AsyncSession):
    """Test filtering tags by type and search substring."""
    repo = TagRepository(db_session)
    await repo.get_or_create_tag("מכבי תל אביב", tag_type=TagType.TEAM)
    await repo.get_or_create_tag("מכבי חיפה", tag_type=TagType.TEAM)
    await repo.get_or_create_tag("ליגת העל", tag_type=TagType.COMPETITION)

    team_tags = await repo.list_tags(tag_type=TagType.TEAM)
    assert len(team_tags) == 2

    maccabi_tags = await repo.list_tags(search_query="מכבי")
    assert len(maccabi_tags) == 2

    popular = await repo.get_popular_tags(limit=10)
    assert len(popular) == 3


# ==========================================
# 3. ArticleRepository Tests
# ==========================================

@pytest.mark.asyncio
async def test_article_hash_computation():
    """Verify SHA-256 content hashing."""
    h1 = ArticleRepository.compute_content_hash(
        "כותרת ראשית",
        ["פסקה 1", "פסקה 2"],
    )
    h2 = ArticleRepository.compute_content_hash(
        " כותרת ראשית ",
        ["פסקה 1", "  ", "פסקה 2"],
    )
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.asyncio
async def test_article_upsert_and_deduplication(db_session: AsyncSession, sample_article_dict: dict):
    """Test upserting new article, updating, and detecting duplicates via URL and content hash."""
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)

    source, _ = await source_repo.create_or_get(
        SourceCreate(name="sport5", display_name="Sport5", base_url="https://sport5.co.il")
    )
    sample_article_dict["source_id"] = source.id

    # 1. First insert -> is_created = True
    article, is_created = await article_repo.upsert_article(sample_article_dict)
    assert is_created is True
    assert article.id is not None
    assert article.ai_headline == "מכבי תל אביב גברה 82:85 על ריאל מדריד ביורוליג"
    assert len(article.media) == 1
    assert len(article.tags) == 7
    assert len(article.tags_json) == 5

    # 2. Duplicate canonical URL with same AI processed state -> returns existing, is_created = False
    dup_url_payload = dict(sample_article_dict)
    article_dup, is_created_dup = await article_repo.upsert_article(dup_url_payload)
    assert is_created_dup is False
    assert article_dup.id == article.id

    # 3. Duplicate content hash (different URL, identical body/title) -> returns existing
    dup_hash_payload = dict(sample_article_dict)
    dup_hash_payload["canonical_url"] = "https://sport5.co.il/different_url_same_content"
    article_hash_dup, is_created_hash = await article_repo.upsert_article(dup_hash_payload)
    assert is_created_hash is False
    assert article_hash_dup.id == article.id

    # 4. Check exists helper
    exists = await article_repo.exists_by_url_or_hash(
        canonical_url=sample_article_dict["canonical_url"],
        content_hash=article.content_hash,
    )
    assert exists is True


@pytest.mark.asyncio
async def test_article_list_and_filters(db_session: AsyncSession):
    """Test rich filtering and Hebrew substring search in ArticleRepository."""
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)

    s1, _ = await source_repo.create_or_get(SourceCreate(name="sport5", display_name="Sport5", base_url="https://sport5.co.il"))
    s2, _ = await source_repo.create_or_get(SourceCreate(name="one", display_name="ONE", base_url="https://one.co.il"))

    base_time = datetime(2026, 8, 28, 10, 0, 0, tzinfo=timezone.utc)

    # Article 1: Basketball - Maccabi Tel Aviv vs Real Madrid (Sport5)
    await article_repo.upsert_article({
        "source_id": s1.id,
        "canonical_url": "https://sport5.co.il/art1",
        "original_title": "סנסציה ביורוליג: מכבי תל אביב הדהימה את ריאל מדריד",
        "original_subtitle": "תצוגת ענק של ווייד בולדווין",
        "published_at": base_time + timedelta(hours=1),
        "raw_paragraphs": ["משחק אדיר בהיכל."],
        "sport": "כדורסל",
        "competition": "יורוליג",
        "teams_json": ["מכבי תל אביב", "ריאל מדריד"],
        "players_json": ["ווייד בולדווין"],
        "tags_json": ["כדורסל", "יורוליג"],
        "ai_headline": "מכבי תל אביב ניצחה את ריאל מדריד 82:85 ביורוליג",
        "ingestion_status": IngestionStatus.AI_PROCESSED,
    })

    # Article 2: Football - Maccabi Haifa in Israeli Premier League (ONE)
    await article_repo.upsert_article({
        "source_id": s2.id,
        "canonical_url": "https://one.co.il/art2",
        "original_title": "מכבי חיפה ניצחה 0:2 את ביתר ירושלים",
        "original_subtitle": "דיא סבע וצ'ארון שרי כבשו בסמי עופר",
        "published_at": base_time + timedelta(hours=2),
        "raw_paragraphs": ["ניצחון חלק לירוקים."],
        "sport": "כדורגל",
        "competition": "ליגת העל",
        "teams_json": ["מכבי חיפה", "בית\"ר ירושלים"],
        "players_json": ["דיא סבע", "צ'ארון שרי"],
        "tags_json": ["כדורגל", "ליגת העל"],
        "ai_headline": "מכבי חיפה גברה 0:2 על בית\"ר ירושלים",
        "ingestion_status": IngestionStatus.AI_PROCESSED,
    })

    # Article 3: Football - Hapoel Tel Aviv (ONE, Pending)
    await article_repo.upsert_article({
        "source_id": s2.id,
        "canonical_url": "https://one.co.il/art3",
        "original_title": "הפועל תל אביב השלימה את החתמת הבלם",
        "original_subtitle": "חוזה לשנתיים",
        "published_at": base_time + timedelta(hours=3),
        "raw_paragraphs": ["חיזוק להגנה."],
        "sport": "כדורגל",
        "competition": "ליגת העל",
        "teams_json": ["הפועל תל אביב"],
        "tags_json": ["הפועל תל אביב", "העברות"],
        "ingestion_status": IngestionStatus.PENDING,
    })

    # Test 1: Total list
    all_articles, total = await article_repo.list_articles()
    assert total == 3
    assert len(all_articles) == 3
    # Verify descending ordering by published_at
    assert all_articles[0].canonical_url == "https://one.co.il/art3"

    # Test 2: Filter by sport
    football_articles, fb_total = await article_repo.list_articles(sport="כדורגל")
    assert fb_total == 2
    assert len(football_articles) == 2

    basketball_articles, bb_total = await article_repo.list_articles(sport="כדורסל")
    assert bb_total == 1
    assert basketball_articles[0].original_title.startswith("סנסציה")

    # Test 3: Filter by team
    haifa_articles, haifa_total = await article_repo.list_articles(team="מכבי חיפה")
    assert haifa_total == 1
    assert haifa_articles[0].teams_json == ["מכבי חיפה", "בית\"ר ירושלים"]

    # Test 4: Filter by source
    sport5_articles, s5_total = await article_repo.list_articles(source_name="sport5")
    assert s5_total == 1
    assert sport5_articles[0].source.name == "sport5"

    # Test 5: Filter by status
    pending_articles, p_total = await article_repo.list_articles(status=IngestionStatus.PENDING)
    assert p_total == 1
    assert pending_articles[0].canonical_url == "https://one.co.il/art3"

    # Test 6: Hebrew search query
    search_res, s_total = await article_repo.list_articles(search_query="בולדווין")
    assert s_total == 1
    assert search_res[0].sport == "כדורסל"

    search_res2, s2_total = await article_repo.list_articles(search_query="סמי עופר")
    assert s2_total == 1
    assert search_res2[0].sport == "כדורגל"

    # Test 7: Pagination
    paged, p_count = await article_repo.list_articles(skip=1, limit=1)
    assert p_count == 3
    assert len(paged) == 1
    assert paged[0].canonical_url == "https://one.co.il/art2"


@pytest.mark.asyncio
async def test_article_delete(db_session: AsyncSession, sample_article_dict: dict):
    """Test deleting an article via ArticleRepository."""
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)

    source, _ = await source_repo.create_or_get(
        SourceCreate(name="sport5", display_name="Sport5", base_url="https://sport5.co.il")
    )
    sample_article_dict["source_id"] = source.id
    article, _ = await article_repo.upsert_article(sample_article_dict)

    deleted = await article_repo.delete_article(article.id)
    assert deleted is True

    fetched = await article_repo.get_by_id(article.id)
    assert fetched is None

    # Deleting nonexistent article returns False
    deleted_missing = await article_repo.delete_article(999999)
    assert deleted_missing is False


@pytest.mark.asyncio
async def test_repository_missing_lookups(db_session: AsyncSession):
    """Test queries for nonexistent records return None or False."""
    source_repo = SourceRepository(db_session)
    tag_repo = TagRepository(db_session)
    article_repo = ArticleRepository(db_session)

    assert await source_repo.get_by_id(999) is None
    assert await source_repo.get_by_name("nonexistent") is None
    assert await source_repo.update_poll_status(999, success=False) is None

    assert await tag_repo.get_by_id(999) is None
    assert await tag_repo.get_by_name("nonexistent") is None

    assert await article_repo.get_by_id(999) is None
    assert await article_repo.get_by_canonical_url("https://example.com/none") is None
    assert await article_repo.get_by_content_hash("0000000000000000000000000000000000000000000000000000000000000000") is None
    assert await article_repo.exists_by_url_or_hash("https://example.com/none", "0000") is False


@pytest.mark.asyncio
async def test_init_and_close_db():
    """Test init_db creates schema and close_db disposes engine."""
    from fan_zone.db.session import init_db, close_db, get_async_engine, get_session_factory
    from sqlalchemy.ext.asyncio import create_async_engine
    
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    await init_db(engine=test_engine, seed_sources=True)

    session_factory = get_session_factory(test_engine)
    async with session_factory() as session:
        s_repo = SourceRepository(session)
        sources = await s_repo.list_all()
        assert len(sources) == 7

    await close_db(engine=test_engine)

