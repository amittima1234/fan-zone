"""Asynchronous task queue abstractions and implementations for Fan Zone ingestion pipeline."""

from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Any, Optional, Set

from schemas.feed import RawArticlePayload

logger = logging.getLogger(__name__)


class BaseQueue(ABC):
    """Abstract interface for raw article ingestion queues."""

    @abstractmethod
    async def push(self, item: RawArticlePayload) -> bool:
        """Push a raw article payload to the queue with deduplication.

        Args:
            item: RawArticlePayload to enqueue.

        Returns:
            True if successfully enqueued, False if duplicate URL or push failed.
        """
        pass

    @abstractmethod
    async def pop(self, timeout: Optional[float] = None) -> Optional[RawArticlePayload]:
        """Pop a raw article payload from the queue.

        Args:
            timeout: Maximum wait time in seconds (None or 0 for non-blocking).

        Returns:
            RawArticlePayload instance or None if queue is empty or timed out.
        """
        pass

    @abstractmethod
    async def size(self) -> int:
        """Return the current number of pending items in the queue."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all pending items and reset deduplication state."""
        pass


class InMemoryTaskQueue(BaseQueue):
    """Standalone in-memory asyncio Queue for offline and single-process execution."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._maxsize = maxsize
        self._queue: asyncio.Queue[RawArticlePayload] = asyncio.Queue(maxsize=maxsize)
        self._seen_urls: Set[str] = set()
        self._lock = asyncio.Lock()

    async def push(self, item: RawArticlePayload) -> bool:
        """Enqueue item with URL deduplication.

        Returns False if the URL has already been queued, True otherwise.
        """
        url_str = str(item.url).strip()
        async with self._lock:
            if url_str in self._seen_urls:
                return False
            try:
                self._queue.put_nowait(item)
                self._seen_urls.add(url_str)
                return True
            except asyncio.QueueFull:
                pass

        # If queue is full, wait with put then register seen URL
        await self._queue.put(item)
        async with self._lock:
            self._seen_urls.add(url_str)
        return True

    async def pop(self, timeout: Optional[float] = None) -> Optional[RawArticlePayload]:
        """Dequeue an item with optional timeout."""
        if timeout is None or timeout <= 0:
            try:
                return self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return None

        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            return None

    async def size(self) -> int:
        """Return number of pending items in the in-memory queue."""
        return self._queue.qsize()

    async def clear(self) -> None:
        """Drain the queue and reset seen URLs set."""
        async with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._seen_urls.clear()

    @property
    def seen_urls_count(self) -> int:
        """Return the count of tracked unique URLs."""
        return len(self._seen_urls)


class RedisTaskQueue(BaseQueue):
    """Distributed Redis-backed FIFO task queue with Set-based URL deduplication."""

    def __init__(
        self,
        redis_client: Optional[Any] = None,
        redis_url: Optional[str] = None,
        queue_key: str = "fanzone:raw_articles",
        seen_set_key: str = "fanzone:seen_urls",
    ) -> None:
        self.queue_key = queue_key
        self.seen_set_key = seen_set_key
        self._redis_url = redis_url
        self._redis = redis_client

    async def _get_redis(self) -> Any:
        """Lazily initialize Redis client if not already connected."""
        if self._redis is None:
            if not self._redis_url:
                raise ValueError("RedisTaskQueue requires either a redis_client or redis_url")
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            except ImportError as e:
                raise RuntimeError("redis package is required for RedisTaskQueue (pip install redis)") from e
        return self._redis

    async def push(self, item: RawArticlePayload) -> bool:
        """Deduplicate via Redis SADD and push JSON payload to list."""
        url_str = str(item.url).strip()
        client = await self._get_redis()

        try:
            # SADD returns 1 if element is new, 0 if already existed
            is_new = await client.sadd(self.seen_set_key, url_str)
            if not is_new:
                return False

            payload_json = item.model_dump_json()
            await client.rpush(self.queue_key, payload_json)
            return True
        except Exception as e:
            logger.error("RedisTaskQueue push failed for URL %s: %s", url_str, e)
            return False

    async def pop(self, timeout: Optional[float] = None) -> Optional[RawArticlePayload]:
        """Pop item from Redis list (LPOP or BLPOP) and parse to RawArticlePayload."""
        client = await self._get_redis()
        try:
            if timeout is None or timeout <= 0:
                raw_json = await client.lpop(self.queue_key)
            else:
                res = await client.blpop(self.queue_key, timeout=max(1, int(timeout)))
                raw_json = res[1] if res else None

            if not raw_json:
                return None

            if isinstance(raw_json, bytes):
                raw_json = raw_json.decode("utf-8")

            return RawArticlePayload.model_validate_json(raw_json)
        except Exception as e:
            logger.error("RedisTaskQueue pop failed: %s", e)
            return None

    async def size(self) -> int:
        """Return the length of the Redis queue list."""
        try:
            client = await self._get_redis()
            return await client.llen(self.queue_key)
        except Exception as e:
            logger.error("RedisTaskQueue size query failed: %s", e)
            return 0

    async def clear(self) -> None:
        """Delete queue list and seen set keys."""
        try:
            client = await self._get_redis()
            await client.delete(self.queue_key, self.seen_set_key)
        except Exception as e:
            logger.error("RedisTaskQueue clear failed: %s", e)


def get_task_queue(settings_obj: Optional[Any] = None) -> BaseQueue:
    """Factory helper to return appropriate TaskQueue backend based on configuration.

    Args:
        settings_obj: Optional Settings instance (falls back to core.config.get_settings()).

    Returns:
        Configured BaseQueue implementation (InMemoryTaskQueue or RedisTaskQueue).
    """
    if settings_obj is None:
        from core.config import get_settings
        settings_obj = get_settings()

    if getattr(settings_obj, "REDIS_URL", None):
        try:
            return RedisTaskQueue(redis_url=settings_obj.REDIS_URL)
        except Exception as e:
            logger.warning("Failed to initialize RedisTaskQueue with %s, falling back to InMemoryTaskQueue: %s", settings_obj.REDIS_URL, e)

    return InMemoryTaskQueue()
