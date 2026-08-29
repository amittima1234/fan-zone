"""Async SQLAlchemy database session, engine configuration, and connection management.

Supports both SQLite (local development and in-memory test suites via aiosqlite with StaticPool)
and PostgreSQL (production environments via asyncpg).
"""

import json
from typing import Any, AsyncGenerator, Dict, Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, StaticPool

from core.config import settings

# Base class for all SQLAlchemy declarative ORM models
Base = declarative_base()


def normalize_database_url(url: str) -> str:
    """Normalize database connection URL to ensure appropriate async dialect prefixes.

    Converts:
    - 'sqlite:///' -> 'sqlite+aiosqlite:///'
    - 'postgres://' or 'postgresql://' -> 'postgresql+asyncpg://'
    """
    if not url:
        return "sqlite+aiosqlite:///./fan_zone.db"

    url_clean = url.strip()

    if url_clean.startswith("postgres://"):
        return url_clean.replace("postgres://", "postgresql+asyncpg://", 1)
    if url_clean.startswith("postgresql://"):
        return url_clean.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url_clean.startswith("sqlite://") and not url_clean.startswith("sqlite+aiosqlite://"):
        return url_clean.replace("sqlite://", "sqlite+aiosqlite://", 1)

    return url_clean


def create_async_db_engine(
    database_url: Optional[str] = None,
    echo: Optional[bool] = None,
    **kwargs: Any,
) -> AsyncEngine:
    """Create and configure an asynchronous SQLAlchemy engine.

    Configures connection pooling and dialect-specific parameters based on the URL.
    - SQLite in-memory uses StaticPool and check_same_thread=False.
    - PostgreSQL uses pool_size, max_overflow, and pool_pre_ping.
    """
    db_url = normalize_database_url(database_url or settings.DATABASE_URL)
    is_echo = echo if echo is not None else settings.DB_ECHO

    engine_kwargs: Dict[str, Any] = {
        "echo": is_echo,
        "json_serializer": lambda obj: json.dumps(obj, ensure_ascii=False),
    }

    if "sqlite" in db_url.lower():
        connect_args = kwargs.pop("connect_args", {})
        connect_args.setdefault("check_same_thread", False)
        engine_kwargs["connect_args"] = connect_args

        if ":memory:" in db_url.lower():
            # StaticPool maintains a single connection so in-memory SQLite tables persist
            engine_kwargs.setdefault("poolclass", StaticPool)
    elif "postgresql" in db_url.lower() or "postgres" in db_url.lower():
        engine_kwargs.setdefault("pool_size", 10)
        engine_kwargs.setdefault("max_overflow", 20)
        engine_kwargs.setdefault("pool_pre_ping", True)

    engine_kwargs.update(kwargs)
    return create_async_engine(db_url, **engine_kwargs)


# Global async engine instance using application settings
engine: AsyncEngine = create_async_db_engine()

# Global async session factory
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


def get_session_factory(
    engine_override: Optional[AsyncEngine] = None,
) -> async_sessionmaker[AsyncSession]:
    """Return an async_sessionmaker bound to the given engine or default engine."""
    if engine_override is not None:
        return async_sessionmaker(
            bind=engine_override,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI async dependency yielding an AsyncSession.

    Commits on successful completion and rolls back on unhandled exceptions.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(engine_override: Optional[AsyncEngine] = None) -> None:
    """Create all database tables defined in Base.metadata asynchronously."""
    target_engine = engine_override or engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def reset_db(engine_override: Optional[AsyncEngine] = None) -> None:
    """Drop and recreate all database tables defined in Base.metadata."""
    target_engine = engine_override or engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
