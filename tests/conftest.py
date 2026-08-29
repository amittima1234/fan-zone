"""Pytest configuration and shared async test fixtures."""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fan_zone.db.base import Base
from fan_zone.models.source import Source
from fan_zone.models.article import Article, ArticleMedia
from fan_zone.models.tag import Tag, ArticleTag
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.repositories.source_repo import SourceRepository


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Creates a fresh in-memory SQLite async engine for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Creates a new AsyncSession per test function."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def seeded_session(db_session: AsyncSession) -> AsyncSession:
    """AsyncSession pre-populated with default Israeli sports sources."""
    repo = SourceRepository(db_session)
    await repo.seed_default_sources()
    await db_session.commit()
    return db_session


@pytest.fixture
def sample_article_dict():
    """Returns sample Hebrew sports news article data."""
    return {
        "canonical_url": "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450000",
        "original_title": "מכבי תל אביב ניצחה 85:82 את ריאל מדריד ביורוליג",
        "original_subtitle": "משחק ענק של הצהובים בהיכל. ווייד בולדווין להט עם 28 נקודות.",
        "author": "רועי כהן",
        "published_at": datetime(2026, 8, 28, 20, 0, 0, tzinfo=timezone.utc),
        "raw_paragraphs": [
            "מכבי תל אביב השיגה הערב ניצחון יוקרתי במיוחד בהיכל מנורה מבטחים.",
            "הצהובים של עודד קטש גברו 82:85 על ריאל מדריד במסגרת המחזור ה-15 של היורוליג.",
            "ווייד בולדווין הצטיין עם 28 נקודות ו-6 אסיסטים.",
        ],
        "cleaned_body": (
            "מכבי תל אביב השיגה הערב ניצחון יוקרתי במיוחד בהיכל מנורה מבטחים.\n\n"
            "הצהובים של עודד קטש גברו 82:85 על ריאל מדריד במסגרת המחזור ה-15 של היורוליג.\n\n"
            "ווייד בולדווין הצטיין עם 28 נקודות ו-6 אסיסטים."
        ),
        "ai_headline": "מכבי תל אביב גברה 82:85 על ריאל מדריד ביורוליג",
        "ai_subheadline": "בולדווין הוביל עם 28 נקודות בניצחון הביתי של הצהובים על אלופת אירופה.",
        "sport": "כדורסל",
        "competition": "יורוליג",
        "teams_json": ["מכבי תל אביב", "ריאל מדריד"],
        "players_json": ["ווייד בולדווין", "עודד קטש"],
        "tags_json": ["מכבי תל אביב", "יורוליג", "כדורסל", "ריאל מדריד", "בולדווין"],
        "ingestion_status": IngestionStatus.AI_PROCESSED,
        "media": [
            {
                "url": "https://sport5.co.il/images/baldwin_action.jpg",
                "media_type": MediaType.IMAGE,
                "caption": "ווייד בולדווין חוגג שלשה גדולה",
                "credit": "אלן שיבר",
                "is_primary": True,
                "position_index": 0,
            }
        ],
    }
