"""Integration tests for SQLAlchemy 2.0 Async ORM and ArticleRepository (Milestone 3).

Executes async CRUD operations, query filters, and session management using an
in-memory SQLite database via aiosqlite with StaticPool.
"""

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from db.repository import ArticleRepository
from db.session import (
    Base,
    create_async_db_engine,
    get_db,
    get_session_factory,
    init_db,
    normalize_database_url,
    reset_db,
)
from models.feed import ArticleModel
from schemas.feed import (
    AIEnrichedCard,
    PublisherEnum,
    RawArticlePayload,
    ToneEnum,
    UserPreferences,
)


# ---------------------------------------------------------------------------
# Test Fixtures (In-Memory Async DB Session)
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an isolated in-memory async SQLite engine with StaticPool."""
    engine = create_async_db_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def test_session_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Provide an async session factory bound to the isolated test engine."""
    return get_session_factory(test_engine)


@pytest.fixture
async def db_session(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an active AsyncSession rolled back after each test."""
    async with test_session_factory() as session:
        yield session


@pytest.fixture
def repo(db_session: AsyncSession) -> ArticleRepository:
    """Return an ArticleRepository instance wired to the test session."""
    return ArticleRepository(db_session)


# ---------------------------------------------------------------------------
# Helper Sample Payloads
# ---------------------------------------------------------------------------

def make_sample_raw(
    title: str = "מכבי תל אביב ניצחה ביורוליג",
    url: str = "https://www.sport5.co.il/articles.aspx?docID=101",
    publisher: str = "sport5",
    published_at: datetime = None,
    category: str = "כדורסל",
    author: str = "עמרי פולק",
    raw_body: str = "תצוגת ענק של הצהובים בהיכל מנורה מבטחים.",
    image_url: str = "https://images.sport5.co.il/pic101.jpg",
) -> RawArticlePayload:
    """Helper to build valid RawArticlePayload."""
    return RawArticlePayload(
        title=title,
        url=url,
        publisher=publisher,
        published_at=published_at or datetime(2026, 8, 29, 10, 0, 0, tzinfo=timezone.utc),
        raw_body=raw_body,
        category=category,
        author=author,
        image_url=image_url,
    )


def make_sample_enriched(
    micro_summary: str = "מכבי תל אביב השיגה ניצחון דרמטי ביורוליג מול ריאל מדריד.",
    tags: list = None,
    tone: ToneEnum = ToneEnum.HYPE,
    context_label: str = "יורוליג",
) -> AIEnrichedCard:
    """Helper to build valid AIEnrichedCard."""
    return AIEnrichedCard(
        micro_summary=micro_summary,
        tags=tags or ["מכבי תל אביב", "יורוליג", "כדורסל"],
        tone=tone,
        context_label=context_label,
    )


# ---------------------------------------------------------------------------
# Database Engine & URL Normalization Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDatabaseEngineConfig:
    """Tests for database engine creation and dialect URL normalization."""

    def test_normalize_database_url(self):
        """Verify URL prefixes are correctly rewritten for async drivers."""
        assert normalize_database_url("postgres://user:pass@localhost/db") == "postgresql+asyncpg://user:pass@localhost/db"
        assert normalize_database_url("postgresql://user:pass@localhost/db") == "postgresql+asyncpg://user:pass@localhost/db"
        assert normalize_database_url("sqlite:///fan_zone.db") == "sqlite+aiosqlite:///fan_zone.db"
        assert normalize_database_url("sqlite+aiosqlite:///:memory:") == "sqlite+aiosqlite:///:memory:"
        assert normalize_database_url("") == "sqlite+aiosqlite:///./fan_zone.db"

    async def test_init_db_and_reset_db(self, test_engine: AsyncEngine):
        """Verify init_db and reset_db execute without raising errors."""
        await reset_db(test_engine)
        await init_db(test_engine)


# ---------------------------------------------------------------------------
# CRUD Operation Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestArticleRepositoryCrud:
    """Tests for basic repository CRUD operations."""

    async def test_create_and_get_by_id(self, repo: ArticleRepository):
        """Verify creating an enriched article and reading it by primary key."""
        raw = make_sample_raw(
            title="מכבי חיפה ניצחה בדרבי",
            url="https://www.sport5.co.il/articles.aspx?docID=201",
            publisher="sport5",
        )
        enriched = make_sample_enriched(
            micro_summary="מכבי חיפה גברה על הפועל חיפה בדרבי הסוער בסמי עופר.",
            tags=["מכבי חיפה", "הפועל חיפה", "ליגת העל"],
            tone=ToneEnum.HYPE,
            context_label="דרבי חיפאי",
        )

        article = await repo.create_enriched_article(raw, enriched)

        assert article.id is not None
        assert article.id > 0
        assert article.title == "מכבי חיפה ניצחה בדרבי"
        assert article.publisher == "sport5"
        assert article.tone == "hype"
        assert article.context_label == "דרבי חיפאי"
        assert article.tags == ["מכבי חיפה", "הפועל חיפה", "ליגת העל"]

        # Fetch by ID
        fetched = await repo.get_by_id(article.id)
        assert fetched is not None
        assert fetched.id == article.id
        assert fetched.title == article.title
        assert fetched.url == article.url

    async def test_get_by_url_and_exists_by_url(self, repo: ArticleRepository):
        """Verify URL lookup and existence verification."""
        test_url = "https://www.ynet.co.il/sport/article/r99112233"
        raw = make_sample_raw(url=test_url, publisher="ynet")
        enriched = make_sample_enriched()

        # Before creation
        assert await repo.exists_by_url(test_url) is False
        assert await repo.get_by_url(test_url) is None

        # After creation
        await repo.create_enriched_article(raw, enriched)
        assert await repo.exists_by_url(test_url) is True
        fetched = await repo.get_by_url(test_url)
        assert fetched is not None
        assert fetched.url == test_url

    async def test_url_unique_constraint(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ):
        """Verify that inserting a duplicate URL raises IntegrityError."""
        dup_url = "https://www.one.co.il/Article/25-26/1,1,3,0/999999.html"
        raw1 = make_sample_raw(title="כתבה ראשונה", url=dup_url, publisher="one")
        raw2 = make_sample_raw(title="כתבה שנייה", url=dup_url, publisher="one")
        enriched = make_sample_enriched()

        async with test_session_factory() as session1:
            repo1 = ArticleRepository(session1)
            await repo1.create_enriched_article(raw1, enriched)

        # Attempt duplicate insertion in second session
        async with test_session_factory() as session2:
            repo2 = ArticleRepository(session2)
            with pytest.raises(IntegrityError):
                await repo2.create_enriched_article(raw2, enriched)

    async def test_update_article(self, repo: ArticleRepository):
        """Verify modifying article fields via update_article."""
        raw = make_sample_raw(title="כותרת ישנה", url="https://www.sport5.co.il/art/1")
        enriched = make_sample_enriched(tone=ToneEnum.OBJECTIVE)
        created = await repo.create_enriched_article(raw, enriched)

        updated = await repo.update_article(
            created.id,
            title="כותרת חדשה ומעודכנת",
            tone=ToneEnum.HYPE,
            category="כדורגל",
        )

        assert updated is not None
        assert updated.title == "כותרת חדשה ומעודכנת"
        assert updated.tone == "hype"
        assert updated.category == "כדורגל"

    async def test_delete_article(self, repo: ArticleRepository):
        """Verify deleting an article by primary key."""
        raw = make_sample_raw(url="https://www.sport5.co.il/art/to-delete")
        enriched = make_sample_enriched()
        created = await repo.create_enriched_article(raw, enriched)

        assert await repo.exists_by_url(created.url) is True

        deleted = await repo.delete_article(created.id)
        assert deleted is True
        assert await repo.get_by_id(created.id) is None
        assert await repo.exists_by_url(created.url) is False

        # Attempt deleting non-existent ID
        assert await repo.delete_article(9999) is False

    async def test_empty_database_lookups(self, repo: ArticleRepository):
        """Verify proper return values when querying non-existent records."""
        assert await repo.get_by_id(99999) is None
        assert await repo.get_by_url("https://unknown.com/article") is None
        assert await repo.exists_by_url("https://unknown.com/article") is False
        assert await repo.update_article(99999, title="new") is None
        items, total = await repo.list_articles()
        assert items == []
        assert total == 0


# ---------------------------------------------------------------------------
# Multi-Criteria Query Filtering & Pagination Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestArticleRepositoryFiltering:
    """Tests for multi-criteria search, cross-dialect tag filtering, and pagination."""

    @pytest.fixture(autouse=True)
    async def seed_articles(self, repo: ArticleRepository):
        """Seed 6 distinct articles for robust filtering and pagination assertions."""
        base_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)

        articles_data = [
            # 1. Sport5 Euroleague Basketball
            (
                make_sample_raw(
                    title="ניצחון ענק: מכבי תל אביב גברה על ריאל מדריד ביורוליג",
                    url="https://www.sport5.co.il/art/1",
                    publisher="sport5",
                    published_at=base_time - timedelta(hours=1),
                    category="כדורסל",
                ),
                make_sample_enriched(
                    micro_summary="מכבי תל אביב הבטיחה ניצחון הירואי על ריאל מדריד בהיכל מנורה.",
                    tags=["מכבי תל אביב", "ריאל מדריד", "יורוליג", "כדורסל"],
                    tone=ToneEnum.HYPE,
                    context_label="יורוליג",
                ),
            ),
            # 2. Ynet Beitar Jerusalem Football Crisis
            (
                make_sample_raw(
                    title="סערה בבית\"ר ירושלים: החלוץ הזר עזב במפתיע לטורקיה",
                    url="https://www.ynet.co.il/art/2",
                    publisher="ynet",
                    published_at=base_time - timedelta(hours=2),
                    category="כדורגל ישראלי",
                ),
                make_sample_enriched(
                    micro_summary="זעזוע בבית\"ר ירושלים לאחר נטישת החלוץ, ההנהלה תובעת.",
                    tags=["בית\"ר ירושלים", "ליגת העל", "כדורגל ישראלי"],
                    tone=ToneEnum.CRITICAL,
                    context_label="משבר במועדון",
                ),
            ),
            # 3. ONE Hapoel Beer Sheva Transfer
            (
                make_sample_raw(
                    title="הפועל באר שבע פתחה במו\"מ להחתמת קשר נבחרת רומניה",
                    url="https://www.one.co.il/art/3",
                    publisher="one",
                    published_at=base_time - timedelta(hours=3),
                    category="ליגת העל",
                ),
                make_sample_enriched(
                    micro_summary="הפועל באר שבע במגעים מתקדמים לצירוף קשר רומני לקראת אירופה.",
                    tags=["הפועל באר שבע", "חלון ההעברות", "קונפרנס ליג"],
                    tone=ToneEnum.OBJECTIVE,
                    context_label="העברות",
                ),
            ),
            # 4. Sport5 Maccabi Haifa Derby Prep
            (
                make_sample_raw(
                    title="לקראת הדרבי: ברק בכר מתלבט בהרכב מכבי חיפה בסמי עופר",
                    url="https://www.sport5.co.il/art/4",
                    publisher="sport5",
                    published_at=base_time - timedelta(hours=4),
                    category="ליגת העל",
                ),
                make_sample_enriched(
                    micro_summary="מכבי חיפה משלימה הכנות לדרבי מול הפועל חיפה.",
                    tags=["מכבי חיפה", "הפועל חיפה", "דרבי חיפאי"],
                    tone=ToneEnum.HYPE,
                    context_label="משחק עונה",
                ),
            ),
            # 5. Ynet Hapoel Tel Aviv Basketball Signing
            (
                make_sample_raw(
                    title="הפועל תל אביב החתימה גארד אמריקאי נוצץ ליורוקאפ",
                    url="https://www.ynet.co.il/art/5",
                    publisher="ynet",
                    published_at=base_time - timedelta(hours=5),
                    category="כדורסל",
                ),
                make_sample_enriched(
                    micro_summary="הפועל תל אביב צירפה כוכב יורוליג לשעבר למסע ביורוקאפ.",
                    tags=["הפועל תל אביב", "יורוקאפ", "כדורסל"],
                    tone=ToneEnum.HYPE,
                    context_label="העברות",
                ),
            ),
            # 6. Walla Olympic Judo Gold
            (
                make_sample_raw(
                    title="מדליית זהב היסטורית לנבחרת הג'ודו של ישראל באליפות אירופה",
                    url="https://sports.walla.co.il/art/6",
                    publisher="walla",
                    published_at=base_time - timedelta(hours=6),
                    category="ג'ודו",
                ),
                make_sample_enriched(
                    micro_summary="נבחרת ישראל בג'ודו זכתה בזהב קבוצתי בטביליסי.",
                    tags=["ג'ודו", "נבחרת ישראל", "ספורט אולימפי"],
                    tone=ToneEnum.HYPE,
                    context_label="ספורט אולימפי",
                ),
            ),
        ]

        for raw, enriched in articles_data:
            await repo.create_enriched_article(raw, enriched)

    async def test_list_all_articles_pagination(self, repo: ArticleRepository):
        """Verify default listing returns all articles sorted newest-first with pagination."""
        # Page 1 of size 2
        items_p1, total = await repo.list_articles(page=1, page_size=2)
        assert total == 6
        assert len(items_p1) == 2
        assert items_p1[0].url == "https://www.sport5.co.il/art/1"
        assert items_p1[1].url == "https://www.ynet.co.il/art/2"

        # Page 2 of size 2
        items_p2, total = await repo.list_articles(page=2, page_size=2)
        assert total == 6
        assert len(items_p2) == 2
        assert items_p2[0].url == "https://www.one.co.il/art/3"
        assert items_p2[1].url == "https://www.sport5.co.il/art/4"

        # Page 4 out of range
        items_p4, total = await repo.list_articles(page=4, page_size=2)
        assert total == 6
        assert len(items_p4) == 0

    async def test_filter_by_publisher(self, repo: ArticleRepository):
        """Verify filtering by single and multiple publishers."""
        # Filter Sport5
        sport5_items, total = await repo.list_articles(publishers=["sport5"])
        assert total == 2
        assert all(item.publisher == "sport5" for item in sport5_items)

        # Filter Ynet and ONE
        multi_items, total = await repo.list_articles(publishers=["ynet", "one"])
        assert total == 3
        assert {item.publisher for item in multi_items} == {"ynet", "one"}

        # Filter non-existent publisher
        empty_items, total = await repo.list_articles(publishers=["nonexistent"])
        assert total == 0
        assert empty_items == []

    async def test_filter_by_tags_json(self, repo: ArticleRepository):
        """Verify JSON tag filtering matching exact tags across items."""
        # Match single basketball tag
        basket_items, total = await repo.list_articles(tags=["כדורסל"])
        assert total == 2
        for item in basket_items:
            assert "כדורסל" in item.tags

        # Match multiple tags (OR logic: Maccabi Tel Aviv or Judo)
        or_items, total = await repo.list_articles(tags=["מכבי תל אביב", "ג'ודו"])
        assert total == 2
        tags_set = set(or_items[0].tags + or_items[1].tags)
        assert "מכבי תל אביב" in tags_set
        assert "ג'ודו" in tags_set

        # Non-matching tag
        none_items, total = await repo.list_articles(tags=["שחייה"])
        assert total == 0
        assert none_items == []

    async def test_filter_by_tone(self, repo: ArticleRepository):
        """Verify filtering by article tone."""
        # Critical tone (Beitar article)
        crit_items, total = await repo.list_articles(tone=ToneEnum.CRITICAL)
        assert total == 1
        assert crit_items[0].tone == "critical"
        assert crit_items[0].publisher == "ynet"

        # Objective tone (Hapoel Beer Sheva transfer)
        obj_items, total = await repo.list_articles(tone="objective")
        assert total == 1
        assert obj_items[0].tone == "objective"

        # Hype tone
        hype_items, total = await repo.list_articles(tone=ToneEnum.HYPE)
        assert total == 4
        assert all(item.tone == "hype" for item in hype_items)

    async def test_filter_by_date_range(self, repo: ArticleRepository):
        """Verify filtering articles within timestamp boundaries."""
        base_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
        date_from = base_time - timedelta(hours=3, minutes=30)
        date_to = base_time - timedelta(minutes=30)

        # Should match articles 1, 2, 3 (from -3h to -1h)
        items, total = await repo.list_articles(date_from=date_from, date_to=date_to)
        assert total == 3
        urls = [item.url for item in items]
        assert "https://www.sport5.co.il/art/1" in urls
        assert "https://www.ynet.co.il/art/2" in urls
        assert "https://www.one.co.il/art/3" in urls

    async def test_filter_by_text_search(self, repo: ArticleRepository):
        """Verify full-text substring search across title, micro_summary, and raw_body."""
        # Search by team name in headline
        search_maccabi, total = await repo.list_articles(search="מכבי")
        assert total == 2
        for item in search_maccabi:
            assert "מכבי" in item.title

        # Search by keyword in micro_summary
        search_gold, total = await repo.list_articles(search="טביליסי")
        assert total == 1
        assert "טביליסי" in search_gold[0].micro_summary

    async def test_multi_criteria_combined_filtering(self, repo: ArticleRepository):
        """Verify combining tags, publisher, tone, and search simultaneously."""
        items, total = await repo.list_articles(
            tags=["יורוליג"],
            publishers=["sport5"],
            tone=ToneEnum.HYPE,
            search="ריאל מדריד",
        )
        assert total == 1
        assert items[0].url == "https://www.sport5.co.il/art/1"
        assert items[0].publisher == "sport5"
        assert items[0].tone == "hype"

    async def test_get_articles_by_preferences(self, repo: ArticleRepository):
        """Verify personalized feed generation via UserPreferences payload."""
        # User follows Israeli Football & Basketball, excludes Walla, prefers HYPE
        prefs = UserPreferences(
            followed_tags=["כדורסל", "ליגת העל"],
            excluded_sources=["walla"],
            preferred_tones=[ToneEnum.HYPE],
        )

        items, total = await repo.get_articles_by_preferences(prefs, page=1, page_size=10)
        assert total >= 2
        assert all(item.publisher != "walla" for item in items)
        assert all(item.tone == "hype" for item in items)


# ---------------------------------------------------------------------------
# FastAPI get_db Dependency Lifecycle Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFastAPIDbDependency:
    """Tests validating the get_db FastAPI dependency lifecycle."""

    async def test_get_db_session_commit(self):
        """Verify get_db commits cleanly upon generator completion."""
        async for session in get_db():
            assert isinstance(session, AsyncSession)
            assert session.is_active

    async def test_get_db_session_rollback_on_error(self):
        """Verify get_db triggers rollback and raises when an exception occurs."""
        with pytest.raises(RuntimeError, match="Simulated endpoint failure"):
            async for session in get_db():
                assert session.is_active
                raise RuntimeError("Simulated endpoint failure")
