"""Application configuration settings using pydantic-settings."""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application Settings
    APP_NAME: str = Field(
        default="FanZone Israeli Sports Ingestion Backend",
        description="Application Title"
    )
    APP_ENV: str = Field(
        default="development",
        description="Environment: development, production, test"
    )
    DEBUG: bool = Field(
        default=False,
        description="Debug mode flag"
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR"
    )
    HOST: str = Field(
        default="0.0.0.0",
        description="FastAPI host binding"
    )
    PORT: int = Field(
        default=8000,
        description="FastAPI port binding"
    )

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./fan_zone.db",
        description="Async SQLAlchemy database URL (supports sqlite+aiosqlite and postgresql+asyncpg)"
    )
    DB_ECHO: bool = Field(
        default=False,
        description="SQLAlchemy query echoing"
    )

    # Google Gemini AI Integration
    GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        description="Google Gemini API Key"
    )
    GEMINI_MODEL: str = Field(
        default="gemini-3.7-flash",
        description="Gemini model identifier"
    )
    GEMINI_MAX_RETRIES: int = Field(
        default=3,
        description="Maximum retry attempts on transient Gemini errors (503/429/overload)"
    )
    GEMINI_RETRY_DELAY_SECONDS: float = Field(
        default=2.0,
        description="Initial delay in seconds between Gemini retries"
    )
    USE_MOCK_AI: bool = Field(
        default=False,
        description="Mock AI mode flag for deterministic offline testing"
    )

    # Scheduler & Scraper Settings
    ENABLE_SCHEDULER: bool = Field(
        default=True,
        description="Enable periodic background scraping scheduler"
    )
    POLL_INTERVAL_SECONDS: int = Field(
        default=300,
        description="Polling interval in seconds between scraper runs"
    )
    SCRAPER_TIMEOUT_SECONDS: int = Field(
        default=15,
        description="Timeout per HTTP scraping request"
    )
    MAX_CONCURRENT_SCRAPES: int = Field(
        default=4,
        description="Max concurrent scrapers running simultaneously"
    )

    # Redis / Task Queue
    REDIS_URL: Optional[str] = Field(
        default=None,
        description="Redis connection URL for queue backend"
    )

    @property
    def is_sqlite(self) -> bool:
        """Return True if the configured DATABASE_URL is SQLite."""
        return bool(self.DATABASE_URL and self.DATABASE_URL.lower().startswith("sqlite"))

    @property
    def is_postgres(self) -> bool:
        """Return True if the configured DATABASE_URL is PostgreSQL."""
        return bool(
            self.DATABASE_URL
            and (
                self.DATABASE_URL.lower().startswith("postgres://")
                or self.DATABASE_URL.lower().startswith("postgresql://")
                or self.DATABASE_URL.lower().startswith("postgresql+")
            )
        )

    @property
    def is_mock_ai(self) -> bool:
        """Return True if mock AI mode is enabled or no Gemini API key is configured."""
        return bool(self.USE_MOCK_AI or not self.GEMINI_API_KEY or not self.GEMINI_API_KEY.strip())


@lru_cache()
def get_settings() -> Settings:
    """Return cached application Settings instance."""
    return Settings()


# Global settings singleton
settings: Settings = get_settings()
