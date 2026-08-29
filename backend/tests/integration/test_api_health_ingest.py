"""Integration tests for Health and Ingestion endpoints (Milestone 5).

Tests GET /health, GET /api/v1/health, POST /api/v1/ingestion/trigger,
root service discovery, error handling (503, 400), and deduplication behavior.
"""

from typing import AsyncGenerator
import httpx
from httpx import ASGITransport
import pytest
from unittest.mock import AsyncMock, patch

from api.deps import get_db
from main import app
from schemas.feed import RawArticlePayload
from tests.fixtures.raw_articles import (
    ONE_RAW_ARTICLE,
    SPORT5_RAW_ARTICLE,
    YNET_RAW_ARTICLE,
)


@pytest.mark.integration
class TestHealthCheckEndpoints:
    """Tests for GET /health and GET /api/v1/health endpoints."""

    async def test_health_check_healthy(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify health check returns HTTP 200 and healthy status when DB is connected."""
        # Test /health root alias
        res_root = await async_client.get("/health")
        assert res_root.status_code == 200
        data_root = res_root.json()
        assert data_root["status"] == "healthy"
        assert data_root["database"] == "connected"
        assert data_root["ai_mode"] in ("mock", "live_gemini")
        assert "timestamp" in data_root
        assert "app_name" in data_root

        # Test /api/v1/health versioned route
        res_v1 = await async_client.get("/api/v1/health")
        assert res_v1.status_code == 200
        data_v1 = res_v1.json()
        assert data_v1["status"] == "healthy"
        assert data_v1["database"] == "connected"

    async def test_health_check_database_disconnected_returns_503(self):
        """Verify health check returns HTTP 503 and unhealthy status when DB ping fails."""

        async def broken_get_db() -> AsyncGenerator:
            # Create a mock session whose execute() method raises an exception
            mock_session = AsyncMock()
            mock_session.execute.side_effect = ConnectionRefusedError("Database connection lost")
            yield mock_session

        app.dependency_overrides[get_db] = broken_get_db
        try:
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/health")
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "unhealthy"
                assert data["database"] == "disconnected"
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_root_discovery_endpoint(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify GET / returns application metadata and service URLs."""
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "app_name" in data
        assert "docs_url" in data
        assert "health_url" in data
        assert "feed_url" in data


@pytest.mark.integration
class TestIngestionTriggerEndpoint:
    """Tests for POST /api/v1/ingestion/trigger."""

    async def test_trigger_ingestion_single_publisher_success(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify triggering ingestion for a specific registered publisher."""
        sample_articles = [
            RawArticlePayload(**SPORT5_RAW_ARTICLE),
        ]

        with patch("services.scrapers.sport5.Sport5Scraper.scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = sample_articles

            response = await async_client.post(
                "/api/v1/ingestion/trigger",
                params={"publisher": "sport5", "limit": 5},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert data["publisher"] == "sport5"
            assert data["articles_fetched"] == 1
            assert data["articles_queued"] == 1
            assert "sport5" in data["message"]

    async def test_trigger_ingestion_deduplication(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify that triggering ingestion with duplicate URLs does not double-insert."""
        sample_article = RawArticlePayload(
            title="בדיקת כפילות כתבה",
            raw_body="תוכן כתבה לבדיקת כפילויות במערכת.",
            url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=999888",
            publisher="sport5",
        )

        with patch("services.scrapers.sport5.Sport5Scraper.scrape", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = [sample_article]

            # First run: inserts article
            res1 = await async_client.post(
                "/api/v1/ingestion/trigger",
                params={"publisher": "sport5"},
            )
            assert res1.status_code == 200
            d1 = res1.json()
            assert d1["articles_fetched"] == 1
            assert d1["articles_queued"] == 1

            # Second run: same URL detected, should be skipped
            res2 = await async_client.post(
                "/api/v1/ingestion/trigger",
                params={"publisher": "sport5"},
            )
            assert res2.status_code == 200
            d2 = res2.json()
            assert d2["articles_fetched"] == 1
            assert d2["articles_queued"] == 0  # 0 newly saved

    async def test_trigger_ingestion_all_publishers(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify triggering ingestion without publisher param scrapes all registered portals."""
        sport5_articles = [RawArticlePayload(**SPORT5_RAW_ARTICLE)]
        ynet_articles = [RawArticlePayload(**YNET_RAW_ARTICLE)]
        one_articles = [RawArticlePayload(**ONE_RAW_ARTICLE)]

        with patch("services.scrapers.sport5.Sport5Scraper.scrape", new_callable=AsyncMock) as m_s5, \
             patch("services.scrapers.ynet.YnetScraper.scrape", new_callable=AsyncMock) as m_ynet, \
             patch("services.scrapers.one.ONEScraper.scrape", new_callable=AsyncMock) as m_one, \
             patch("services.scrapers.walla.WallaScraper.scrape", new_callable=AsyncMock) as m_walla:

            m_s5.return_value = sport5_articles
            m_ynet.return_value = ynet_articles
            m_one.return_value = one_articles
            m_walla.return_value = []

            response = await async_client.post("/api/v1/ingestion/trigger")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert data["publisher"] == "all"
            assert data["articles_fetched"] == 3
            assert data["articles_queued"] == 3

    async def test_trigger_ingestion_invalid_publisher_raises_400(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify triggering with an unregistered publisher identifier raises HTTP 400."""
        response = await async_client.post(
            "/api/v1/ingestion/trigger",
            params={"publisher": "invalid_news_outlet"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Invalid publisher" in data["detail"]
        assert "sport5" in data["detail"]
