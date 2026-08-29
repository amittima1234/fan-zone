"""Unit tests for Settings configuration (Milestone 1)."""

import pytest
from core.config import Settings, get_settings, settings


class TestSettings:
    """Tests for application settings and environment resolution."""

    def test_default_settings(self):
        s = Settings()
        assert s.APP_NAME == "FanZone Israeli Sports Ingestion Backend"
        assert s.APP_ENV in ["development", "production", "test"]
        assert s.PORT == 8000
        assert s.GEMINI_MODEL.startswith("gemini-") and "flash" in s.GEMINI_MODEL
        assert s.POLL_INTERVAL_SECONDS >= 1
        assert s.SCRAPER_TIMEOUT_SECONDS >= 1

    def test_is_sqlite_property(self):
        s1 = Settings(DATABASE_URL="sqlite+aiosqlite:///./fan_zone.db")
        assert s1.is_sqlite is True
        assert s1.is_postgres is False

        s2 = Settings(DATABASE_URL="sqlite:///./fan_zone.db")
        assert s2.is_sqlite is True
        assert s2.is_postgres is False

    def test_is_postgres_property(self):
        s1 = Settings(DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/fanzone")
        assert s1.is_postgres is True
        assert s1.is_sqlite is False

        s2 = Settings(DATABASE_URL="postgres://user:pass@localhost:5432/fanzone")
        assert s2.is_postgres is True
        assert s2.is_sqlite is False

    def test_is_mock_ai_property(self):
        # Case 1: USE_MOCK_AI explicitly True
        s_mock = Settings(USE_MOCK_AI=True, GEMINI_API_KEY="some-key")
        assert s_mock.is_mock_ai is True

        # Case 2: No API key configured
        s_no_key = Settings(USE_MOCK_AI=False, GEMINI_API_KEY=None)
        assert s_no_key.is_mock_ai is True

        # Case 3: Empty string API key
        s_empty_key = Settings(USE_MOCK_AI=False, GEMINI_API_KEY="   ")
        assert s_empty_key.is_mock_ai is True

        # Case 4: Live mode with key
        s_live = Settings(USE_MOCK_AI=False, GEMINI_API_KEY="valid-api-key-12345")
        assert s_live.is_mock_ai is False

    def test_environment_override(self, monkeypatch):
        monkeypatch.setenv("APP_NAME", "Custom Fan Zone App")
        monkeypatch.setenv("PORT", "9090")
        monkeypatch.setenv("USE_MOCK_AI", "true")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://db:5432/test")

        custom_settings = Settings()
        assert custom_settings.APP_NAME == "Custom Fan Zone App"
        assert custom_settings.PORT == 9090
        assert custom_settings.USE_MOCK_AI is True
        assert custom_settings.is_postgres is True

    def test_get_settings_cached_singleton(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        assert settings is not None
        assert isinstance(settings, Settings)
