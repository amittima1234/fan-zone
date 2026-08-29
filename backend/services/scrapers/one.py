"""ONE Israeli sports portal scraper implementation."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import trafilatura

from schemas.feed import RawArticlePayload
from services.scrapers.base import (
    BaseScraper,
    is_non_article_content,
    sanitize_article_text,
    truncate_article_text,
)

logger = logging.getLogger(__name__)


class ONEScraper(BaseScraper):
    """Scraper for the ONE sports portal (https://www.one.co.il)."""

    publisher_id: str = "one"
    base_url: str = "https://www.one.co.il"
    rss_urls: List[str] = [
        "https://www.one.co.il/rss",
    ]

    def extract_article(
        self,
        html: str,
        rss_entry: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawArticlePayload]:
        """Extract ONE article headline, body, and metadata with dual-tier parsing.

        Args:
            html: Raw HTML content of the ONE article page.
            rss_entry: Optional RSS entry dictionary with fallback metadata.

        Returns:
            Validated RawArticlePayload or None.
        """
        rss_entry = rss_entry or {}
        title: Optional[str] = None
        raw_body: Optional[str] = None
        url: Optional[str] = rss_entry.get("link")
        author: Optional[str] = rss_entry.get("author")
        category: Optional[str] = rss_entry.get("category")
        image_url: Optional[str] = rss_entry.get("image_url")
        published_at: datetime = rss_entry.get("published_at") or datetime.now(timezone.utc)

        soup: Optional[BeautifulSoup] = None
        if html and html.strip():
            try:
                soup = BeautifulSoup(html, "html.parser")
            except Exception as e:
                logger.warning("BeautifulSoup parsing failed on ONE HTML: %s", e)

        if soup is not None:
            # 1. Extract Title
            title_tag = soup.select_one(
                "h1.art-title, h1.article-title, h1#article-title, meta[property='og:title'], h1"
            )
            if title_tag and title_tag.get_text(strip=True):
                title = title_tag.get_text(strip=True)
            else:
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    title = og_title["content"]

            # 2. Extract Canonical / OG URL
            if not url:
                og_url = soup.find("meta", property="og:url")
                if og_url and og_url.get("content"):
                    url = og_url["content"]

            # 3. Extract Author
            author_tag = soup.select_one("div.author, span.author-name, div.article-author")
            if author_tag and author_tag.get_text(strip=True):
                author_text = author_tag.get_text(strip=True)
                if author_text.startswith("מאת:"):
                    author_text = author_text[4:].strip()
                author = author_text
            else:
                meta_author = soup.find("meta", attrs={"name": "author"})
                if meta_author and meta_author.get("content"):
                    author = meta_author["content"]

            # 4. Extract Cover Image
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                image_url = og_img["content"]

            # 5. Extract Article Body Text
            # Tier 1: Trafilatura
            try:
                traf_text = trafilatura.extract(html, output_format="txt", include_comments=False, include_tables=False)
                if traf_text and len(traf_text.strip()) > 50:
                    raw_body = traf_text.strip()
            except Exception as e:
                logger.debug("Trafilatura failed on ONE article: %s", e)

            # Tier 2: BeautifulSoup DOM extraction fallback
            if not raw_body:
                body_container = soup.select_one(
                    "div.one-content, div.article-text, div.article-content, div.plain-content, div#article_content, div.article div.content"
                )
                if body_container:
                    # Remove ads, tracking, and videos inside the container
                    for unwanted in body_container.select(
                        "script, style, iframe, .one-ad-slot, .ad, [class*='ad-'], .video-player"
                    ):
                        unwanted.decompose()
                    paragraphs = [p.get_text(strip=True) for p in body_container.find_all("p") if p.get_text(strip=True)]
                    if paragraphs:
                        raw_body = "\n\n".join(paragraphs)
                    else:
                        raw_body = body_container.get_text(separator="\n\n", strip=True)

        # Fallback to RSS metadata
        if not title:
            title = rss_entry.get("title")
        if not raw_body:
            raw_body = rss_entry.get("summary") or title

        if not title or not raw_body:
            logger.warning("ONE article extraction discarded due to missing title or body")
            return None

        # Sanitize and truncate
        clean_title = sanitize_article_text(title)
        clean_body = sanitize_article_text(raw_body)
        truncated_body = truncate_article_text(clean_body, max_chars=3500)

        if not clean_title or not truncated_body:
            return None

        # Filter out static/legal/accessibility/contact pages
        if is_non_article_content(title=clean_title, url=url, raw_body=clean_body):
            logger.info("Discarding non-article content for ONE: '%s' (%s)", clean_title, url)
            return None

        if not url:
            url = f"{self.base_url}"

        return RawArticlePayload(
            title=clean_title,
            raw_body=truncated_body,
            url=url,
            publisher=self.publisher_id,
            published_at=published_at,
            category=category,
            author=author,
            image_url=image_url,
        )
