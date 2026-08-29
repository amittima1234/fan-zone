"""Database engine and session management for async SQLAlchemy 2.0."""

import logging
from typing import AsyncGenerator, Optional
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fan_zone.config import get_settings
from fan_zone.db.base import Base

logger = logging.getLogger(__name__)

# Global engine and sessionmaker singletons
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Creates or returns the cached AsyncEngine."""
    global _engine
    if _engine is not None and database_url is None:
        return _engine

    settings = get_settings()
    url = database_url or settings.DATABASE_URL

    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_async_engine(
        url,
        echo=settings.DB_ECHO,
        future=True,
        connect_args=connect_args,
    )

    # Enable SQLite foreign keys on connect
    if url.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    if database_url is None:
        _engine = engine
    return engine


def get_session_factory(engine: Optional[AsyncEngine] = None) -> async_sessionmaker[AsyncSession]:
    """Creates or returns the cached async_sessionmaker."""
    global _session_factory
    if _session_factory is not None and engine is None:
        return _session_factory

    target_engine = engine or get_async_engine()
    factory = async_sessionmaker(
        bind=target_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    if engine is None:
        _session_factory = factory
    return factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async dependency yielding an AsyncSession."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(engine: Optional[AsyncEngine] = None, seed_sources: bool = True) -> None:
    """Initializes the database schema and seeds initial data."""
    # Import all models to ensure they are registered on Base.metadata
    from fan_zone.models import source, article, tag, story  # noqa: F401
    
    target_engine = engine or get_async_engine()
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized successfully.")

    if seed_sources:
        factory = get_session_factory(target_engine)
        async with factory() as session:
            from fan_zone.repositories.source_repo import SourceRepository
            repo = SourceRepository(session)
            await repo.seed_default_sources()
            await session.commit()
        logger.info("Default sports news sources verified/seeded.")


async def close_db(engine: Optional[AsyncEngine] = None) -> None:
    """Disposes of the database engine connection pool."""
    global _engine, _session_factory
    target_engine = engine or _engine
    if target_engine is not None:
        await target_engine.dispose()
        if engine is None or engine == _engine:
            _engine = None
            _session_factory = None
        logger.info("Database engine disposed.")
