"""Global pytest fixtures and test infrastructure for Fan Zone backend."""

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, List
import httpx
from httpx import ASGITransport
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from api.deps import get_db, get_settings
from core.config import Settings
from db.repository import ArticleRepository
from db.session import (
    Base,
    create_async_db_engine,
    get_session_factory,
)
from main import app
from schemas.feed import (
    AIEnrichedCard,
    PublisherEnum,
    RawArticlePayload,
    ToneEnum,
)


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated application settings for testing."""
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USE_MOCK_AI=True,
        ENABLE_SCHEDULER=False,
        DEBUG=True,
        DB_ECHO=False,
        APP_ENV="test",
    )


@pytest.fixture
async def test_engine(test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
    """Provide an in-memory async SQLite database engine with StaticPool."""
    engine = create_async_db_engine(test_settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def test_session_factory(
    test_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Provide an async session factory bound to the in-memory test engine."""
    return get_session_factory(test_engine)


@pytest.fixture
async def db_session(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an active AsyncSession rolled back after each test."""
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture
def article_repo(db_session: AsyncSession) -> ArticleRepository:
    """Provide an ArticleRepository bound to the test db_session."""
    return ArticleRepository(db_session)


@pytest.fixture
async def seeded_articles(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> List[int]:
    """Seed 6 diverse sports articles into the test database and return their IDs."""
    base_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)

    articles_data = [
        # 1. Sport5 Maccabi Tel Aviv Euroleague (Hype)
        (
            RawArticlePayload(
                title="ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג",
                url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450101",
                publisher="sport5",
                published_at=base_time - timedelta(hours=1),
                raw_body="תצוגת ענק של הצהובים בהיכל מנורה מבטחים הבטיחה מקום בפלייאוף.",
                category="כדורסל",
                author="עמרי פולק",
            ),
            AIEnrichedCard(
                micro_summary="מכבי תל אביב הבטיחה ניצחון יוקרתי 82:86 על ריאל מדריד ביורוליג.",
                tags=["מכבי תל אביב", "ריאל מדריד", "יורוליג", "כדורסל"],
                tone=ToneEnum.HYPE,
                context_label="יורוליג",
            ),
        ),
        # 2. Ynet Beitar Jerusalem Crisis (Critical)
        (
            RawArticlePayload(
                title="סערה בבית\"ר ירושלים: החלוץ הזר הודיע על עזיבה מיידית",
                url="https://www.ynet.co.il/sport/israelifootball/article/r1j8xk9211",
                publisher="ynet",
                published_at=base_time - timedelta(hours=2),
                raw_body="זעזוע בבירה יומיים לפני משחק העונה, החלוץ דורש התרת חוזה.",
                category="ליגת העל",
                author="גידי ליפקין",
            ),
            AIEnrichedCard(
                micro_summary="זעזוע בבית\"ר ירושלים בעקבות עזיבת החלוץ הזר לפני משחק העונה.",
                tags=["בית\"ר ירושלים", "ליגת העל", "כדורגל ישראלי"],
                tone=ToneEnum.CRITICAL,
                context_label="משבר במועדון",
            ),
        ),
        # 3. ONE Hapoel Beer Sheva Transfer (Objective)
        (
            RawArticlePayload(
                title="פרסום ראשון: הפועל באר שבע פתחה במו\"מ לצירוף קשר נבחרת רומניה",
                url="https://www.one.co.il/Article/25-26/1,1,3,0/478901.html",
                publisher="one",
                published_at=base_time - timedelta(hours=3),
                raw_body="אלונה ברקת נותנת אור ירוק למהלך המרכזי של חלון ההעברות בטרנר.",
                category="הפועל באר שבע",
                author="איציק כלפי",
            ),
            AIEnrichedCard(
                micro_summary="הפועל באר שבע במשא ומתן מתקדם לצירוף קשר רומני לקונפרנס ליג.",
                tags=["הפועל באר שבע", "חלון ההעברות", "קונפרנס ליג", "כדורגל ישראלי"],
                tone=ToneEnum.OBJECTIVE,
                context_label="העברות",
            ),
        ),
        # 4. Sport5 Maccabi Haifa Derby (Hype)
        (
            RawArticlePayload(
                title="לקראת הדרבי החיפאי: ברק בכר מתלבט במערך ההתקפי בסמי עופר",
                url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450102",
                publisher="sport5",
                published_at=base_time - timedelta(hours=4),
                raw_body="מכבי חיפה השלימה הכנות לדרבי הגדול מול הפועל חיפה.",
                category="ליגת העל",
                author="תומר לוי",
            ),
            AIEnrichedCard(
                micro_summary="מכבי חיפה משלימה הכנות אחרונות לדרבי מול הפועל חיפה בסמי עופר.",
                tags=["מכבי חיפה", "הפועל חיפה", "ליגת העל", "דרבי חיפאי"],
                tone=ToneEnum.HYPE,
                context_label="משחק עונה",
            ),
        ),
        # 5. Ynet Hapoel Tel Aviv Basketball Signing (Hype)
        (
            RawArticlePayload(
                title="הפועל תל אביב בכדורסל השלימה את הסגל עם גארד אמריקאי נוצץ",
                url="https://www.ynet.co.il/sport/israelibasketball/article/s99k2l1100",
                publisher="ynet",
                published_at=base_time - timedelta(hours=5),
                raw_body="האדומים מתל אביב הודיעו על החתמת גארד בעל עבר עשיר ביורוליג.",
                category="כדורסל ישראלי",
                author="אפרת עמורבן",
            ),
            AIEnrichedCard(
                micro_summary="הפועל תל אביב צירפה כוכב יורוליג לשעבר למסע ביורוקאפ.",
                tags=["הפועל תל אביב", "יורוקאפ", "כדורסל ישראלי"],
                tone=ToneEnum.HYPE,
                context_label="העברות",
            ),
        ),
        # 6. Walla Olympic Judo Gold (Hype)
        (
            RawArticlePayload(
                title="מדליית זהב היסטורית לנבחרת הג'ודו של ישראל באליפות אירופה",
                url="https://sports.walla.co.il/item/369901",
                publisher="walla",
                published_at=base_time - timedelta(hours=6),
                raw_body="הישג ספורטיבי כביר בטביליסי: פיטר פלצ'יק ורז הרשקו כיכבו בקרבות הגמר.",
                category="ג'ודו",
                author="יניב טוכמן",
            ),
            AIEnrichedCard(
                micro_summary="נבחרת ישראל בג'ודו זכתה במדליית זהב היסטורית באליפות אירופה בטביליסי.",
                tags=["ג'ודו", "נבחרת ישראל", "ספורט אולימפי"],
                tone=ToneEnum.HYPE,
                context_label="ספורט אולימפי",
            ),
        ),
    ]

    created_ids = []
    async with test_session_factory() as session:
        repo = ArticleRepository(session)
        for raw, enriched in articles_data:
            created = await repo.create_enriched_article(raw, enriched)
            created_ids.append(created.id)

    return created_ids


@pytest.fixture
async def async_client(
    test_session_factory: async_sessionmaker[AsyncSession],
    test_settings: Settings,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an async ASGI test client wired to the in-memory test database."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    def override_get_settings() -> Settings:
        return test_settings

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
