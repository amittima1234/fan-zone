"""Application configuration module using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Application
    APP_NAME: str = "FanZone Israeli Sports Ingestion Backend"
    ENVIRONMENT: str = Field(default="development", alias="APP_ENV")
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./fan_zone.db",
        description="Async database connection URL (e.g. sqlite+aiosqlite:///./fan_zone.db or postgresql+asyncpg://...)",
    )
    DB_ECHO: bool = False

    # Gemini AI
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    USE_MOCK_AI: bool = False

    # Scheduler & Scrapers
    ENABLE_SCHEDULER: bool = True
    POLL_INTERVAL_SECONDS: int = 300
    SCRAPER_TIMEOUT_SECONDS: int = 15
    MAX_CONCURRENT_SCRAPES: int = 4
    USER_AGENT: str = "FanZoneBot/1.0 (+https://fanzone.co.il)"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT.lower() in ("testing", "test")

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: Optional[str]) -> str:
        if not v:
            return "sqlite+aiosqlite:///./fan_zone.db"
        
        # Convert synchronous sqlite URL to async aiosqlite
        if v.startswith("sqlite:///") and not v.startswith("sqlite+aiosqlite:///"):
            return v.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        if v.startswith("sqlite://") and not v.startswith("sqlite+aiosqlite://"):
            return v.replace("sqlite://", "sqlite+aiosqlite://", 1)
        
        # Convert synchronous postgresql URL to async asyncpg
        if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://") and not v.startswith("postgresql+asyncpg://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
            
        return v


@lru_cache()
def get_settings() -> Settings:
    """Returns cached application settings instance."""
    return Settings()
