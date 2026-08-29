"""Integration tests for FastAPI Feed endpoints (Milestone 5).

Tests GET /api/v1/feed, GET /api/feed, GET /api/v1/feed/{article_id},
and POST /api/v1/feed/personal across filtering, pagination, and error scenarios.
"""

from datetime import datetime, timedelta, timezone
from typing import List
import httpx
import pytest

from schemas.feed import ToneEnum


@pytest.mark.integration
class TestFeedListingAndFiltering:
    """Tests for GET /api/v1/feed filtering and pagination."""

    async def test_get_feed_unfiltered(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify default feed listing returns all seeded articles in paginated envelope."""
        response = await async_client.get("/api/v1/feed")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == len(seeded_articles)
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total_pages"] == 1
        assert data["has_next"] is False
        assert data["has_prev"] is False
        assert len(data["items"]) == len(seeded_articles)

        # Validate item schema fields
        first_item = data["items"][0]
        assert "id" in first_item
        assert "title" in first_item
        assert "url" in first_item
        assert "publisher" in first_item
        assert "published_at" in first_item
        assert "micro_summary" in first_item
        assert "tags" in first_item
        assert "tone" in first_item
        assert "context_label" in first_item
        assert "created_at" in first_item

    async def test_get_feed_alias_route(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify the /api/feed top-level alias matches /api/v1/feed behavior."""
        response = await async_client.get("/api/feed")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(seeded_articles)
        assert len(data["items"]) == len(seeded_articles)

    async def test_filter_by_single_tag(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify filtering by single sport/team tag."""
        # Filter Judo
        res_judo = await async_client.get("/api/v1/feed", params={"tags": "ג'ודו"})
        assert res_judo.status_code == 200
        data_judo = res_judo.json()
        assert data_judo["total"] == 1
        assert data_judo["items"][0]["publisher"] == "walla"
        assert "ג'ודו" in data_judo["items"][0]["tags"]

        # Filter Basketball
        res_basket = await async_client.get("/api/v1/feed", params={"tags": "כדורסל"})
        assert res_basket.status_code == 200
        data_basket = res_basket.json()
        assert data_basket["total"] >= 1
        for item in data_basket["items"]:
            assert any("כדורסל" in t for t in item["tags"])

    async def test_filter_by_multiple_tags_repeated_and_comma(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify multi-tag query via both repeated params and comma-separated string."""
        # Repeated params: ?tags=מכבי תל אביב&tags=הפועל באר שבע
        res_rep = await async_client.get(
            "/api/v1/feed",
            params=[("tags", "מכבי תל אביב"), ("tags", "הפועל באר שבע")],
        )
        assert res_rep.status_code == 200
        data_rep = res_rep.json()
        assert data_rep["total"] == 2
        publishers_rep = {item["publisher"] for item in data_rep["items"]}
        assert "sport5" in publishers_rep
        assert "one" in publishers_rep

        # Comma-separated: ?tags=מכבי תל אביב,הפועל באר שבע
        res_comma = await async_client.get(
            "/api/v1/feed",
            params={"tags": "מכבי תל אביב,הפועל באר שבע"},
        )
        assert res_comma.status_code == 200
        data_comma = res_comma.json()
        assert data_comma["total"] == 2
        assert data_comma["total"] == data_rep["total"]

    async def test_filter_by_publisher(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify filtering by publisher identifier."""
        # Single publisher
        res_s5 = await async_client.get("/api/v1/feed", params={"publisher": "sport5"})
        assert res_s5.status_code == 200
        data_s5 = res_s5.json()
        assert data_s5["total"] == 2
        assert all(item["publisher"] == "sport5" for item in data_s5["items"])

        # Multiple publishers
        res_multi = await async_client.get(
            "/api/v1/feed",
            params=[("publisher", "ynet"), ("publisher", "one")],
        )
        assert res_multi.status_code == 200
        data_multi = res_multi.json()
        assert data_multi["total"] == 3
        assert all(item["publisher"] in ("ynet", "one") for item in data_multi["items"])

        # Unknown publisher
        res_none = await async_client.get("/api/v1/feed", params={"publisher": "unknown_pub"})
        assert res_none.status_code == 200
        data_none = res_none.json()
        assert data_none["total"] == 0
        assert data_none["items"] == []

    async def test_filter_by_tone(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify filtering by journalistic tone enum."""
        # Critical
        res_crit = await async_client.get("/api/v1/feed", params={"tone": "critical"})
        assert res_crit.status_code == 200
        data_crit = res_crit.json()
        assert data_crit["total"] == 1
        assert data_crit["items"][0]["tone"] == "critical"
        assert data_crit["items"][0]["publisher"] == "ynet"

        # Objective
        res_obj = await async_client.get("/api/v1/feed", params={"tone": "objective"})
        assert res_obj.status_code == 200
        data_obj = res_obj.json()
        assert data_obj["total"] == 1
        assert data_obj["items"][0]["tone"] == "objective"

        # Hype
        res_hype = await async_client.get("/api/v1/feed", params={"tone": "hype"})
        assert res_hype.status_code == 200
        data_hype = res_hype.json()
        assert data_hype["total"] == 4
        assert all(item["tone"] == "hype" for item in data_hype["items"])

    async def test_filter_by_date_range(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify valid date range filtering."""
        base_time = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
        date_from = (base_time - timedelta(hours=3, minutes=30)).isoformat()
        date_to = (base_time - timedelta(minutes=30)).isoformat()

        response = await async_client.get(
            "/api/v1/feed",
            params={"date_from": date_from, "date_to": date_to},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

    async def test_invalid_date_range_raises_400(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify date_from > date_to raises HTTP 400 Bad Request."""
        date_from = "2026-08-30T12:00:00Z"
        date_to = "2026-08-28T12:00:00Z"

        response = await async_client.get(
            "/api/v1/feed",
            params={"date_from": date_from, "date_to": date_to},
        )
        assert response.status_code == 400
        data = response.json()
        assert "date_from cannot be after date_to" in data["detail"]

    async def test_filter_by_search_text(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify substring search across headline, summary, and body."""
        # Search for player/coach name
        res_player = await async_client.get("/api/v1/feed", params={"search": "ברק בכר"})
        assert res_player.status_code == 200
        data_player = res_player.json()
        assert data_player["total"] == 1
        assert "ברק בכר" in data_player["items"][0]["title"]
        assert "מכבי חיפה" in data_player["items"][0]["tags"]

        # Search for topic in summary
        res_topic = await async_client.get("/api/v1/feed", params={"search": "קונפרנס ליג"})
        assert res_topic.status_code == 200
        data_topic = res_topic.json()
        assert data_topic["total"] == 1
        assert data_topic["items"][0]["publisher"] == "one"

    async def test_combined_multi_criteria_filter(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify simultaneous filtering by tag, publisher, tone, and search."""
        response = await async_client.get(
            "/api/v1/feed",
            params={
                "tags": "יורוליג",
                "publisher": "sport5",
                "tone": "hype",
                "search": "ריאל מדריד",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["publisher"] == "sport5"
        assert data["items"][0]["tone"] == "hype"

    async def test_pagination_boundary_calculations(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify pagination slicing, total_pages, has_next, and has_prev."""
        # Page 1 of 2
        r1 = await async_client.get("/api/v1/feed", params={"page": 1, "page_size": 2})
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["page"] == 1
        assert d1["page_size"] == 2
        assert d1["total"] == 6
        assert d1["total_pages"] == 3
        assert d1["has_next"] is True
        assert d1["has_prev"] is False
        assert len(d1["items"]) == 2

        # Page 2 of 2
        r2 = await async_client.get("/api/v1/feed", params={"page": 2, "page_size": 2})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["page"] == 2
        assert d2["has_next"] is True
        assert d2["has_prev"] is True
        assert len(d2["items"]) == 2

        # Page 3 of 2 (Last page)
        r3 = await async_client.get("/api/v1/feed", params={"page": 3, "page_size": 2})
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["page"] == 3
        assert d3["has_next"] is False
        assert d3["has_prev"] is True
        assert len(d3["items"]) == 2

        # Page 4 of 2 (Out of range)
        r4 = await async_client.get("/api/v1/feed", params={"page": 4, "page_size": 2})
        assert r4.status_code == 200
        d4 = r4.json()
        assert d4["page"] == 4
        assert d4["has_next"] is False
        assert d4["has_prev"] is True
        assert len(d4["items"]) == 0

    async def test_pagination_validation_errors(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify page < 1 or page_size > 100 raises HTTP 422."""
        # page = 0
        r_zero = await async_client.get("/api/v1/feed", params={"page": 0})
        assert r_zero.status_code == 422

        # page_size = 200 (limit is 100)
        r_large = await async_client.get("/api/v1/feed", params={"page_size": 200})
        assert r_large.status_code == 422


@pytest.mark.integration
class TestArticleByIdEndpoint:
    """Tests for GET /api/v1/feed/{article_id}."""

    async def test_get_article_by_id_success(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify looking up existing article by ID returns 200 and valid schema."""
        target_id = seeded_articles[0]
        response = await async_client.get(f"/api/v1/feed/{target_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == target_id
        assert "title" in data
        assert "url" in data
        assert "publisher" in data
        assert "micro_summary" in data

    async def test_get_article_by_id_not_found(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify looking up non-existent article returns 404 Not Found."""
        response = await async_client.get("/api/v1/feed/99999")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    async def test_get_article_by_invalid_id_type(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify passing non-integer ID returns 422 Unprocessable Entity."""
        response = await async_client.get("/api/v1/feed/non_numeric_id")
        assert response.status_code == 422

    async def test_get_article_by_zero_id(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify passing ID 0 returns 422 due to ge=1 constraint."""
        response = await async_client.get("/api/v1/feed/0")
        assert response.status_code == 422


@pytest.mark.integration
class TestPersonalizedFeedEndpoint:
    """Tests for POST /api/v1/feed/personal."""

    async def test_personalized_feed_success(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify feed personalization matches followed tags and excludes specified publishers."""
        payload = {
            "followed_tags": ["כדורגל ישראלי", "ליגת העל"],
            "excluded_sources": ["ynet"],
            "preferred_tones": ["objective", "hype"],
        }
        response = await async_client.post("/api/v1/feed/personal", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["total"] >= 1
        assert all(item["publisher"] != "ynet" for item in data["items"])
        assert all(item["tone"] in ("objective", "hype") for item in data["items"])

    async def test_personalized_feed_empty_preferences(
        self,
        async_client: httpx.AsyncClient,
        seeded_articles: List[int],
    ):
        """Verify empty UserPreferences payload returns all articles within pagination."""
        response = await async_client.post("/api/v1/feed/personal", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(seeded_articles)

    async def test_personalized_feed_invalid_body_raises_422(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Verify invalid preferred_tones value raises 422 Unprocessable Entity."""
        invalid_payload = {
            "preferred_tones": ["invalid_unknown_tone"],
        }
        response = await async_client.post("/api/v1/feed/personal", json=invalid_payload)
        assert response.status_code == 422
