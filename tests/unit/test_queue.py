"""Unit tests for task queue abstractions, deduplication, and FIFO ordering (Milestone 2)."""

import asyncio
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.config import Settings
from core.queue import (
    BaseQueue,
    InMemoryTaskQueue,
    RedisTaskQueue,
    get_task_queue,
)
from schemas.feed import RawArticlePayload
from tests.fixtures.raw_articles import (
    MACCABI_HAIFA_FOOTBALL_RAW_ARTICLE,
    ONE_RAW_ARTICLE,
    SPORT5_RAW_ARTICLE,
    YNET_RAW_ARTICLE,
)


@pytest.fixture
def sample_payloads():
    return [
        RawArticlePayload(**SPORT5_RAW_ARTICLE),
        RawArticlePayload(**YNET_RAW_ARTICLE),
        RawArticlePayload(**ONE_RAW_ARTICLE),
    ]


class TestInMemoryTaskQueue:
    """Unit tests for InMemoryTaskQueue."""

    @pytest.mark.asyncio
    async def test_fifo_ordering(self, sample_payloads):
        queue = InMemoryTaskQueue()
        for p in sample_payloads:
            pushed = await queue.push(p)
            assert pushed is True

        assert await queue.size() == 3

        # Pop in FIFO order
        p1 = await queue.pop()
        assert p1 is not None
        assert p1.url == sample_payloads[0].url

        p2 = await queue.pop()
        assert p2 is not None
        assert p2.url == sample_payloads[1].url

        p3 = await queue.pop()
        assert p3 is not None
        assert p3.url == sample_payloads[2].url

        # Queue is now empty
        assert await queue.size() == 0
        assert await queue.pop() is None

    @pytest.mark.asyncio
    async def test_url_deduplication(self, sample_payloads):
        queue = InMemoryTaskQueue()
        item = sample_payloads[0]

        # First push succeeds
        res1 = await queue.push(item)
        assert res1 is True
        assert await queue.size() == 1
        assert queue.seen_urls_count == 1

        # Second push with same URL is deduplicated
        res2 = await queue.push(item)
        assert res2 is False
        assert await queue.size() == 1
        assert queue.seen_urls_count == 1

        # Different item succeeds
        item2 = sample_payloads[1]
        res3 = await queue.push(item2)
        assert res3 is True
        assert await queue.size() == 2

    @pytest.mark.asyncio
    async def test_pop_timeout_empty(self):
        queue = InMemoryTaskQueue()
        # Fast timeout on empty queue returns None
        item = await queue.pop(timeout=0.05)
        assert item is None

    @pytest.mark.asyncio
    async def test_clear_queue(self, sample_payloads):
        queue = InMemoryTaskQueue()
        for p in sample_payloads:
            await queue.push(p)

        assert await queue.size() == 3
        await queue.clear()
        assert await queue.size() == 0
        assert queue.seen_urls_count == 0

        # After clear, re-pushing previous URL should now succeed
        res = await queue.push(sample_payloads[0])
        assert res is True
        assert await queue.size() == 1

    @pytest.mark.asyncio
    async def test_concurrent_pushes(self):
        queue = InMemoryTaskQueue()

        async def push_item(index: int, duplicate: bool = False):
            url = f"https://www.sport5.co.il/article_{index if not duplicate else 0}"
            payload = RawArticlePayload(
                title=f"כותרת {index}",
                raw_body=f"תוכן כתבה מספר {index}",
                url=url,
                publisher="sport5",
            )
            return await queue.push(payload)

        # Concurrently push 20 distinct items and 20 duplicates of item 0
        tasks = [push_item(i, duplicate=False) for i in range(20)] + [push_item(i, duplicate=True) for i in range(20)]
        results = await asyncio.gather(*tasks)

        # Exactly 20 distinct pushes must return True, the 20 duplicates of 0 should mostly return False
        success_count = sum(1 for r in results if r is True)
        assert success_count == 20
        assert await queue.size() == 20


class TestRedisTaskQueue:
    """Unit tests for RedisTaskQueue using mock async Redis client."""

    @pytest.mark.asyncio
    async def test_redis_queue_push_and_pop(self, sample_payloads):
        mock_redis = AsyncMock()
        mock_redis.sadd.return_value = 1  # URL is new
        mock_redis.rpush.return_value = 1
        mock_redis.llen.return_value = 1

        item = sample_payloads[0]
        queue = RedisTaskQueue(redis_client=mock_redis)

        # Test push
        pushed = await queue.push(item)
        assert pushed is True
        mock_redis.sadd.assert_called_once_with(queue.seen_set_key, str(item.url))
        mock_redis.rpush.assert_called_once()

        # Test pop
        mock_redis.lpop.return_value = item.model_dump_json()
        popped = await queue.pop()
        assert popped is not None
        assert popped.title == item.title
        assert popped.url == item.url

    @pytest.mark.asyncio
    async def test_redis_queue_deduplication(self, sample_payloads):
        mock_redis = AsyncMock()
        mock_redis.sadd.return_value = 0  # URL already in set

        item = sample_payloads[0]
        queue = RedisTaskQueue(redis_client=mock_redis)

        pushed = await queue.push(item)
        assert pushed is False
        mock_redis.rpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_queue_size_and_clear(self):
        mock_redis = AsyncMock()
        mock_redis.llen.return_value = 5

        queue = RedisTaskQueue(redis_client=mock_redis)
        assert await queue.size() == 5

        await queue.clear()
        mock_redis.delete.assert_called_once_with(queue.queue_key, queue.seen_set_key)


class TestGetTaskQueueFactory:
    """Unit tests for queue factory dispatcher."""

    def test_default_returns_in_memory_queue(self):
        s = Settings(REDIS_URL=None)
        q = get_task_queue(s)
        assert isinstance(q, InMemoryTaskQueue)

    def test_redis_url_configured_returns_redis_queue(self):
        s = Settings(REDIS_URL="redis://localhost:6379/0")
        q = get_task_queue(s)
        assert isinstance(q, RedisTaskQueue)
