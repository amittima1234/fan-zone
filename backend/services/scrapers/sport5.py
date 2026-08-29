"""Sport5 Israeli sports portal scraper implementation.

Scrapes Sport5 newsroom, domestic football, international football, basketball,
NBA, and Olympic/other sports section pages without relying on RSS feeds.
"""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx
import trafilatura

from schemas.feed import RawArticlePayload
from services.scrapers.base import (
    BaseScraper,
    is_non_article_content,
    sanitize_article_text,
    truncate_article_text,
)

logger = logging.getLogger(__name__)


class Sport5Scraper(BaseScraper):
    """Direct HTML & Section based scraper for Sport5 (https://www.sport5.co.il)."""

    publisher_id: str = "sport5"
    base_url: str = "https://www.sport5.co.il"

    # Specific Sport5 section URLs for newsroom and sports categories
    SECTIONS: List[Dict[str, str]] = [
        {
            "url": "https://www.sport5.co.il/NewsRoom",
            "category": "מבזקים",
            "label": "חדר המבזקים",
        },
        {
            "url": "https://www.sport5.co.il/world.aspx?FolderID=4453",
            "category": "כדורגל עולמי",
            "label": "כדורגל עולמי",
        },
        {
            "url": "https://www.sport5.co.il/world.aspx?FolderID=4439",
            "category": "כדורגל ישראלי",
            "label": "כדורגל ישראלי",
        },
        {
            "url": "https://www.sport5.co.il/world.aspx?FolderID=4467",
            "category": "כדורסל",
            "label": "כדורסל",
        },
        {
            "url": "https://nba.sport5.co.il/NBA.aspx?FolderId=402",
            "category": "NBA",
            "label": "ליגת ה-NBA",
        },
        {
            "url": "https://www.sport5.co.il/world.aspx?FolderID=4498",
            "category": "ענפים נוספים",
            "label": "ענפים נוספים",
        },
    ]

    # Stored for BaseScraper interface compatibility
    rss_urls: List[str] = [s["url"] for s in SECTIONS]

    def _is_article_url(self, url: str) -> bool:
        """Check if a URL points to a Sport5 article or news item."""
        if not url:
            return False
        clean = url.lower().strip()
        # Must not be an anchor, javascript, or external non-sport5 domain
        if clean.startswith("#") or clean.startswith("javascript:") or clean.startswith("mailto:"):
            return False
        
        parsed = urlparse(clean)
        if parsed.netloc and "sport5.co.il" not in parsed.netloc:
            return False

        # Discard known non-article URL patterns (terms, accessibility, privacy, contact)
        if is_non_article_content(url=clean):
            return False

        # Match article indicators on Sport5
        article_patterns = (
            "articles.aspx",
            "docid=",
            "docid%3d",
            "/item/",
            "/article/",
            "/newsroom/",
            "articleid=",
        )
        return any(p in clean for p in article_patterns)

    def _extract_links_from_section_html(
        self,
        html_content: str,
        section_meta: Dict[str, str],
        seen_links: Set[str],
    ) -> List[Dict[str, Any]]:
        """Extract article metadata dictionaries from a section listing HTML."""
        entries: List[Dict[str, Any]] = []
        if not html_content or not html_content.strip():
            return entries

        try:
            soup = BeautifulSoup(html_content, "html.parser")
        except Exception as e:
            logger.warning("BeautifulSoup failed parsing Sport5 section HTML: %s", e)
            return entries

        # Decompose footer, navigation, legal, and copyright elements so footer links are never scraped
        for junk in soup.select("footer, div.footer, div.site-footer, div.bottom-nav, div.legal, div.terms, nav.footer-nav, div.bottom_links, div.copyright, div.site_map, div.about-section"):
            junk.decompose()

        category_name = section_meta.get("category", "ספורט")
        section_base_url = section_meta.get("url", self.base_url)

        # 1. Look for structured newsroom or article card containers first
        article_containers = soup.select(
            "div.newsroom-item, div.news-item, div.article-box, div.main-article, "
            "div.art-item, li.news-item, div.item, div.gallery-item, div.content-item, "
            "article, div.news_item, div.row-item"
        )

        for container in article_containers:
            link_tag = container.select_one("a[href]")
            if not link_tag:
                continue

            raw_href = link_tag.get("href", "").strip()
            if not self._is_article_url(raw_href):
                continue

            abs_url = urljoin(section_base_url, raw_href)
            if abs_url in seen_links:
                continue

            # Title
            title_text = ""
            title_elem = container.select_one("h1, h2, h3, h4, span.title, div.title, .art-title, strong")
            if title_elem and title_elem.get_text(strip=True):
                title_text = title_elem.get_text(strip=True)
            elif link_tag.get_text(strip=True):
                title_text = link_tag.get_text(strip=True)
            elif link_tag.get("title"):
                title_text = link_tag["title"].strip()

            # Teaser / Summary
            summary_text = ""
            summary_elem = container.select_one("p, div.desc, span.desc, div.sub-title, div.text")
            if summary_elem and summary_elem.get_text(strip=True):
                summary_text = summary_elem.get_text(strip=True)

            # Check if this item is static/legal/contact content
            if is_non_article_content(title=title_text, url=abs_url, raw_body=summary_text):
                continue

            seen_links.add(abs_url)

            # Image
            image_url = None
            img_elem = container.select_one("img[src], img[data-src]")
            if img_elem:
                raw_img = img_elem.get("data-src") or img_elem.get("src")
                if raw_img and not raw_img.startswith("data:"):
                    image_url = urljoin(section_base_url, raw_img.strip())

            # Timestamp / Author if present in listing
            author = None
            author_elem = container.select_one("span.author, span.writer")
            if author_elem and author_elem.get_text(strip=True):
                author = author_elem.get_text(strip=True).replace("מאת:", "").strip()

            if title_text or abs_url:
                entries.append({
                    "title": sanitize_article_text(title_text),
                    "link": abs_url,
                    "summary": sanitize_article_text(summary_text),
                    "published_at": datetime.now(timezone.utc),
                    "author": author,
                    "category": category_name,
                    "image_url": image_url,
                })

        # 2. General <a> tag scan for any missed article links
        for a_tag in soup.select("a[href]"):
            raw_href = a_tag.get("href", "").strip()
            if not self._is_article_url(raw_href):
                continue

            abs_url = urljoin(section_base_url, raw_href)
            if abs_url in seen_links:
                continue

            title_text = a_tag.get_text(strip=True) or a_tag.get("title", "").strip()
            # If link text is trivial (like "לכתבה המלאה"), look for heading in parent
            if len(title_text) < 5 and a_tag.parent:
                parent_h = a_tag.parent.find(["h1", "h2", "h3", "h4", "h5"])
                if parent_h and parent_h.get_text(strip=True):
                    title_text = parent_h.get_text(strip=True)

            if is_non_article_content(title=title_text, url=abs_url):
                continue

            seen_links.add(abs_url)

            entries.append({
                "title": sanitize_article_text(title_text),
                "link": abs_url,
                "summary": "",
                "published_at": datetime.now(timezone.utc),
                "author": None,
                "category": category_name,
                "image_url": None,
            })

        return entries

    async def fetch_section_entries(
        self,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch Sport5 section index pages and discover article URLs."""
        entries: List[Dict[str, Any]] = []
        seen_links: Set[str] = set()
        should_close = False

        if client is None:
            client = httpx.AsyncClient(headers=self.headers, timeout=self.timeout)
            should_close = True

        try:
            for section in self.SECTIONS:
                sec_url = section["url"]
                sec_label = section["label"]
                try:
                    resp = await client.get(
                        sec_url,
                        headers=self.headers,
                        timeout=self.timeout,
                        follow_redirects=True,
                    )
                    if resp.status_code != 200:
                        logger.warning(
                            "Failed to fetch Sport5 section '%s' (%s): HTTP %s",
                            sec_label,
                            sec_url,
                            resp.status_code,
                        )
                        continue

                    section_entries = self._extract_links_from_section_html(
                        resp.text,
                        section,
                        seen_links,
                    )
                    logger.debug(
                        "Sport5 section '%s' yielded %d articles",
                        sec_label,
                        len(section_entries),
                    )
                    entries.extend(section_entries)

                except Exception as e:
                    logger.warning("Error scraping Sport5 section '%s' (%s): %s", sec_label, sec_url, e)

        finally:
            if should_close:
                await client.aclose()

        return entries

    async def fetch_rss(
        self,
        client: Optional[httpx.AsyncClient] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch article entries via direct section page scraping (replaces RSS)."""
        return await self.fetch_section_entries(client=client)

    def extract_article(
        self,
        html: str,
        rss_entry: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawArticlePayload]:
        """Extract Sport5 article headline, body, and metadata with dual-tier parsing.

        Args:
            html: Raw HTML content of the Sport5 article page.
            rss_entry: Optional entry dictionary from section crawling for fallback metadata.

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
                logger.warning("BeautifulSoup parsing failed on Sport5 HTML: %s", e)

        if soup is not None:
            # 1. Extract Title
            title_tag = soup.select_one(
                "h1.art-title, h1.article-title, h1.title, h1.main-title, "
                "h1[data-component='headline'], header h1, h1"
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
            author_tag = soup.select_one(
                "span.author, div.author-box, div.art-meta span.author, "
                "div.article-author, span.writer, div.writers"
            )
            if author_tag and author_tag.get_text(strip=True):
                author_text = author_tag.get_text(strip=True)
                if author_text.startswith("מאת:"):
                    author_text = author_text[4:].strip()
                author = author_text
            else:
                meta_author = soup.find("meta", attrs={"name": "author"})
                if meta_author and meta_author.get("content"):
                    author = meta_author["content"]

            # 4. Extract Category / Section Breadcrumb
            if not category:
                meta_section = soup.find("meta", property="article:section")
                if meta_section and meta_section.get("content"):
                    category = meta_section["content"]
                else:
                    breadcrumb = soup.select_one("div.breadcrumb, span.category, a.sec-name, .sec-title")
                    if breadcrumb and breadcrumb.get_text(strip=True):
                        category = breadcrumb.get_text(strip=True)

            # 5. Extract Cover Image
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                image_url = og_img["content"]
            elif not image_url:
                img_tag = soup.select_one("div.art-img img, div.article-image img, div.main-img img")
                if img_tag and img_tag.get("src"):
                    image_url = urljoin(self.base_url, img_tag["src"])

            # 6. Extract Published Date
            meta_pub_date = soup.find("meta", property="article:published_time")
            if meta_pub_date and meta_pub_date.get("content"):
                try:
                    published_at = datetime.fromisoformat(meta_pub_date["content"].replace("Z", "+00:00"))
                except Exception:
                    pass

            # 7. Extract Article Body Text
            # Tier 1: Trafilatura
            try:
                traf_text = trafilatura.extract(
                    html,
                    output_format="txt",
                    include_comments=False,
                    include_tables=False,
                )
                if traf_text and len(traf_text.strip()) > 50:
                    raw_body = traf_text.strip()
            except Exception as e:
                logger.debug("Trafilatura failed on Sport5 article: %s", e)

            # Tier 2: BeautifulSoup DOM extraction fallback
            if not raw_body:
                body_container = soup.select_one(
                    "div.art-body, div.article-body, div.article-content, "
                    "article.article-content, div#articleBody, div.content-wrapper, "
                    "div.newsroom-content, div.article_content"
                )
                if body_container:
                    # Remove unwanted tags inside the article container
                    for unwanted in body_container.select(
                        "script, style, iframe, .ad, .in-article-ad, #banner-ad, .banner, .outbrain, .taboola"
                    ):
                        unwanted.decompose()
                    paragraphs = [p.get_text(strip=True) for p in body_container.find_all("p") if p.get_text(strip=True)]
                    if paragraphs:
                        raw_body = "\n\n".join(paragraphs)
                    else:
                        raw_body = body_container.get_text(separator="\n\n", strip=True)

        # Fallback to section entry metadata if page parsing did not yield title/body
        if not title:
            title = rss_entry.get("title")
        if not raw_body:
            raw_body = rss_entry.get("summary") or title

        if not title or not raw_body:
            logger.warning("Sport5 article extraction discarded due to missing title or body")
            return None

        # Sanitize and truncate
        clean_title = sanitize_article_text(title)
        clean_body = sanitize_article_text(raw_body)
        truncated_body = truncate_article_text(clean_body, max_chars=3500)

        if not clean_title or not truncated_body:
            return None

        # Filter out static/legal/accessibility/contact pages
        if is_non_article_content(title=clean_title, url=url, raw_body=clean_body):
            logger.info("Discarding non-article content for Sport5: '%s' (%s)", clean_title, url)
            return None

        if not url:
            url = f"{self.base_url}/articles.aspx"

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
