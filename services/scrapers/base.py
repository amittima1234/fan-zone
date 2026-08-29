"""Abstract base scraper and content sanitization utilities for Fan Zone sports feeds."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import email.utils
import html
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import feedparser
import httpx

from schemas.feed import RawArticlePayload

logger = logging.getLogger(__name__)


def sanitize_article_text(text: str) -> str:
    """Strip HTML tags, scripts, styles, unescape entities, and normalize whitespace & RTL text.

    Args:
        text: Raw input text (which may contain HTML tags, entities, or excess whitespace).

    Returns:
        Cleaned, normalized plain text string.
    """
    if not text:
        return ""

    # Strip script and style blocks completely including contents
    cleaned = re.sub(r"<\s*(script|style|iframe|noscript)[^>]*>.*?<\s*/\s*\1\s*>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Strip any remaining unclosed/standalone HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Unescape HTML entities (e.g. &quot;, &amp;, &rlm;, &#39;)
    cleaned = html.unescape(cleaned)
    # Split by lines, normalize internal spaces per line, and preserve non-empty lines
    lines = []
    for line in cleaned.splitlines():
        normalized_line = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        if normalized_line:
            lines.append(normalized_line)
    cleaned = "\n\n".join(lines)
    # Remove leading spaces before punctuation
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)

    return cleaned.strip()


def truncate_article_text(text: str, max_chars: int = 3500) -> str:
    """Strictly truncate article text to maximum character limit.

    Args:
        text: Article body text to truncate.
        max_chars: Strict character limit (defaults to 3500 per R2 requirement).

    Returns:
        Truncated text satisfying len(text) <= max_chars.
    """
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    # Strict slice to max_chars characters
    return text[:max_chars].rstrip()


class BaseScraper(ABC):
    """Abstract base class defining the contract for Israeli sports portal scrapers."""

    publisher_id: str = "base"
    base_url: str = ""
    rss_urls: List[str] = []

    def __init__(
        self,
        timeout: float = 15.0,
        user_agent: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.headers: Dict[str, str] = {
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com/",
        }

    def _parse_published_date(self, entry: Dict[str, Any]) -> datetime:
        """Extract or parse publication datetime from a feedparser entry safely into UTC."""
        # 1. Try parsed time tuple from feedparser
        if entry.get("published_parsed"):
            try:
                time_struct = entry["published_parsed"]
                return datetime.fromtimestamp(time.mktime(time_struct), tz=timezone.utc)
            except Exception:
                pass

        # 2. Try raw string dates (e.g. RFC 822 or ISO 8601)
        raw_date = entry.get("published") or entry.get("pubDate") or entry.get("updated")
        if raw_date and isinstance(raw_date, str):
            try:
                parsed_tuple = email.utils.parsedate_tz(raw_date)
                if parsed_tuple:
                    ts = email.utils.mktime_tz(parsed_tuple)
                    return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                pass

            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass

        # 3. Fallback to current UTC datetime
        return datetime.now(timezone.utc)

    async def fetch_rss(self, client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
        """Fetch and parse RSS feeds for new article entries.

        Args:
            client: Optional httpx.AsyncClient instance for connection reuse.

        Returns:
            List of standardized dictionary entries extracted from the RSS feeds.
        """
        entries: List[Dict[str, Any]] = []
        seen_links = set()
        should_close = False

        if client is None:
            client = httpx.AsyncClient(headers=self.headers, timeout=self.timeout)
            should_close = True

        try:
            for rss_url in self.rss_urls:
                try:
                    resp = await client.get(rss_url, headers=self.headers, timeout=self.timeout, follow_redirects=True)
                    if resp.status_code != 200:
                        logger.warning("Failed to fetch RSS feed %s: HTTP %s", rss_url, resp.status_code)
                        continue

                    parsed_feed = feedparser.parse(resp.text)
                    for item in parsed_feed.entries:
                        link = item.get("link") or ""
                        if not link:
                            continue

                        # Resolve relative URLs
                        link = urljoin(self.base_url, link.strip())
                        if link in seen_links:
                            continue
                        seen_links.add(link)

                        # Author resolution
                        author = item.get("author") or item.get("dc_creator") or item.get("creator") or None
                        if author and isinstance(author, str):
                            author = sanitize_article_text(author)

                        # Category resolution
                        category = None
                        if item.get("tags") and len(item["tags"]) > 0:
                            category = item["tags"][0].get("term") or item["tags"][0].get("label")
                        elif item.get("category"):
                            category = item.get("category")
                        if category and isinstance(category, str):
                            category = sanitize_article_text(category)

                        entry_dict: Dict[str, Any] = {
                            "title": sanitize_article_text(item.get("title", "")),
                            "link": link,
                            "summary": sanitize_article_text(item.get("summary") or item.get("description", "")),
                            "published_at": self._parse_published_date(item),
                            "author": author,
                            "category": category,
                            "image_url": None,
                        }

                        # Check media enclosures or media_content
                        if item.get("media_content") and len(item["media_content"]) > 0:
                            entry_dict["image_url"] = item["media_content"][0].get("url")
                        elif item.get("enclosures") and len(item["enclosures"]) > 0:
                            entry_dict["image_url"] = item["enclosures"][0].get("href")

                        entries.append(entry_dict)
                except Exception as e:
                    logger.warning("Error fetching/parsing RSS URL %s: %s", rss_url, e)
        finally:
            if should_close:
                await client.aclose()

        return entries

    async def fetch_article_html(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        """Fetch raw HTML for an article URL asynchronously.

        Args:
            client: Active httpx.AsyncClient.
            url: Canonical URL of the article page.

        Returns:
            Raw HTML string or None if request failed.
        """
        try:
            resp = await client.get(url, headers=self.headers, timeout=self.timeout, follow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            logger.warning("Failed to fetch article HTML for %s: HTTP %s", url, resp.status_code)
            return None
        except Exception as e:
            logger.warning("Exception fetching article HTML for %s: %s", url, e)
            return None

    @abstractmethod
    def extract_article(
        self,
        html: str,
        rss_entry: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawArticlePayload]:
        """Extract title, raw_body, metadata, sanitize and return a RawArticlePayload.

        Args:
            html: Raw HTML content of the article page.
            rss_entry: Optional dictionary containing RSS metadata for fallback.

        Returns:
            Validated RawArticlePayload instance or None if extraction failed.
        """
        pass

    async def scrape(self, limit: Optional[int] = None) -> List[RawArticlePayload]:
        """Orchestrate scraping of RSS feeds and corresponding article pages.

        Args:
            limit: Maximum number of articles to scrape in this run.

        Returns:
            List of successfully extracted RawArticlePayload objects.
        """
        articles: List[RawArticlePayload] = []

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
            entries = await self.fetch_rss(client)
            if limit is not None and limit > 0:
                entries = entries[:limit]

            for entry in entries:
                url = entry["link"]
                html_content = await self.fetch_article_html(client, url)
                try:
                    payload = self.extract_article(html_content or "", rss_entry=entry)
                    if payload is not None:
                        articles.append(payload)
                except Exception as e:
                    logger.warning("Failed to extract article from %s: %s", url, e)

        return articles
