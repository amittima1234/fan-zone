"""Base models, normalizers, hashers, and abstract scraper base class."""

import asyncio
from datetime import datetime, timezone
import hashlib
import html as html_lib
import json
import logging
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, model_validator

try:
    import trafilatura
except ImportError:
    trafilatura = None

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. URL Normalization & Content Hashing Utilities
# ==============================================================================

TRACKING_PARAMS: Set[str] = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_name", "utm_cid", "utm_reader", "fbclid", "gclid", "gbraid", "wbraid",
    "ref", "rnd", "v", "_ga", "timestamp", "campaign", "cmp", "tab", "xtor",
    "at_custom1", "at_custom2", "at_custom3", "at_custom4", "mvt", "mc_cid",
    "mc_eid", "yclid", "igshid", "ocid", "dclid", "_hsenc", "_hsmi"
}


def normalize_canonical_url(raw_url: str) -> str:
    """Normalizes an article URL into a canonical format by stripping tracking parameters,
    normalizing scheme and hostnames, resolving path trailing slashes, and sorting query keys.
    """
    if not raw_url or not isinstance(raw_url, str):
        return ""

    url_str = raw_url.strip()
    if not url_str:
        return ""

    # Fix relative protocol
    if url_str.startswith("//"):
        url_str = "https:" + url_str
    elif not url_str.lower().startswith(("http://", "https://")):
        url_str = "https://" + url_str

    try:
        parsed = urlparse(url_str)
    except Exception:
        return url_str

    scheme = "https"
    netloc = parsed.netloc.lower().strip()
    # Strip standard default ports if present
    if netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Normalize path: remove consecutive slashes, strip trailing slash unless root '/'
    path = re.sub(r"/+", "/", parsed.path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    elif not path:
        path = "/"

    # Filter and sort query parameters
    query_items = parse_qsl(parsed.query, keep_blank_values=False)
    filtered_items: List[Tuple[str, str]] = []
    for k, v in query_items:
        k_clean = k.strip()
        v_clean = v.strip()
        k_lower = k_clean.lower()
        if k_lower in TRACKING_PARAMS or k_lower.startswith(("utm_", "fb_")):
            continue
        filtered_items.append((k_clean, v_clean))

    # Sort query parameters alphabetically by lower key for deterministic hashing/comparison
    filtered_items.sort(key=lambda item: (item[0].lower(), item[1]))
    clean_query = urlencode(filtered_items) if filtered_items else ""

    # Reconstruct URL without fragment
    return urlunparse((scheme, netloc, path, "", clean_query, ""))


def clean_html_text(text: Optional[str], preserve_newlines: bool = False) -> str:
    """Strips HTML tags before unescaping HTML entities so bracketed text is preserved,
    strips zero-width/RTL control characters, and collapses whitespace.
    When preserve_newlines=True, preserves \n while cleaning whitespace per line.
    """
    if not text:
        return ""
    # 1. Remove HTML tags BEFORE unescaping HTML entities so &lt;foo&gt; is not deleted
    cleaned = re.sub(r"<[^>]+>", "", text)
    # 2. Unescape HTML entities
    unescaped = html_lib.unescape(cleaned)
    # 3. Remove zero-width characters and control markers
    cleaned = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad]", "", unescaped)
    if preserve_newlines:
        lines = [re.sub(r"[^\S\r\n]+", " ", line).strip() for line in re.split(r"[\r\n]+", cleaned)]
        return "\n".join([line for line in lines if line]).strip()
    # 4. Collapse multiple whitespace characters into single space
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def compute_content_hash(title: str, paragraphs: Sequence[str]) -> str:
    """Computes a deterministic SHA-256 hash over normalized Hebrew title and body paragraphs.
    Applies Unicode NFC normalization, strips branding suffixes, and normalizes whitespace invariant to multi-space.
    """
    cleaned_title = unicodedata.normalize("NFC", (title or "").strip())
    # Strip common site branding suffixes from title
    cleaned_title = re.sub(
        r"\s*[-|–—]\s*(ספורט 5|ספורט 1|וואלה!\s*ספורט|וואלה|ONE|ynet|ידיעות אחרונות|ישראל היום|הארץ|Sport 5|Sport 1|Haaretz)\s*$",
        "",
        cleaned_title,
        flags=re.IGNORECASE,
    ).strip()
    # Normalize whitespace in title
    cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip()

    valid_paragraphs: List[str] = []
    for p in paragraphs or []:
        if p and isinstance(p, str):
            p_clean = unicodedata.normalize("NFC", p.strip())
            p_clean = re.sub(r"\s+", " ", p_clean).strip()
            if p_clean:
                valid_paragraphs.append(p_clean)

    body_text = "\n".join(valid_paragraphs)
    payload = f"{cleaned_title}\n{body_text}".strip().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


HEBREW_MONTH_MAP: Dict[str, int] = {
    "ינואר": 1, "בינואר": 1,
    "פברואר": 2, "בפברואר": 2,
    "מרץ": 3, "במרץ": 3, "מרס": 3, "במרס": 3,
    "אפריל": 4, "באפריל": 4,
    "מאי": 5, "במאי": 5,
    "יוני": 6, "ביוני": 6,
    "יולי": 7, "ביולי": 7,
    "אוגוסט": 8, "באוגוסט": 8,
    "ספטמבר": 9, "בספטמבר": 9,
    "אוקטובר": 10, "באוקטובר": 10,
    "נובמבר": 11, "בנובמבר": 11,
    "דצמבר": 12, "בדצמבר": 12,
}


def parse_datetime(date_input: Union[str, datetime, None]) -> datetime:
    """Robustly parses datetime from ISO-8601 strings, Hebrew text, or custom publisher formats.
    Always returns a timezone-aware UTC datetime.
    """
    if isinstance(date_input, datetime):
        if date_input.tzinfo is None:
            return date_input.replace(tzinfo=timezone.utc)
        return date_input.astimezone(timezone.utc)

    if not date_input or not isinstance(date_input, str):
        return datetime.now(timezone.utc)

    raw = clean_html_text(date_input)
    # 1. Try standard ISO-8601 parsing
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # 2. Hebrew date formats (e.g. "28.08.26 - 22:30", "28/08/2026 21:15", "28.08.2026, 21:30")
    patterns = [
        (r"(\d{1,2})[./](\d{1,2})[./](\d{4})[ ,\-]+(\d{1,2}):(\d{2})", True),  # DD.MM.YYYY HH:mm
        (r"(\d{1,2})[./](\d{1,2})[./](\d{2})[ ,\-]+(\d{1,2}):(\d{2})", False),  # DD.MM.YY HH:mm
        (r"(\d{1,2})[./](\d{1,2})[./](\d{4})", True),  # DD.MM.YYYY
        (r"(\d{1,2})[./](\d{1,2})[./](\d{2})", False),  # DD.MM.YY
    ]

    for pat, is_4digit_year in patterns:
        m = re.search(pat, raw)
        if m:
            day = int(m.group(1))
            month = int(m.group(2))
            year = int(m.group(3))
            if not is_4digit_year:
                year += 2000 if year < 70 else 1900
            hour = int(m.group(4)) if len(m.groups()) >= 4 and m.group(4) is not None else 12
            minute = int(m.group(5)) if len(m.groups()) >= 5 and m.group(5) is not None else 0
            try:
                dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

    # 3. Hebrew textual month names (e.g. "28 באוגוסט 2026, 21:30", "יום שישי, 28 באוגוסט 2026, 21:30")
    hebrew_match = re.search(
        r"(\d{1,2})\s+([א-ת]+)\s+(\d{4})(?:[ ,\-]+(\d{1,2}):(\d{2}))?",
        raw,
    )
    if hebrew_match:
        day = int(hebrew_match.group(1))
        month_name = hebrew_match.group(2)
        year = int(hebrew_match.group(3))
        hour = int(hebrew_match.group(4)) if hebrew_match.group(4) else 12
        minute = int(hebrew_match.group(5)) if hebrew_match.group(5) else 0
        month = HEBREW_MONTH_MAP.get(month_name, 1)
        try:
            return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            pass

    return datetime.now(timezone.utc)


# ==============================================================================
# 2. Extracted Data Models
# ==============================================================================

class ExtractedImage(BaseModel):
    url: str
    caption: Optional[str] = None
    credit: Optional[str] = None
    is_main: bool = False
    width: Optional[int] = None
    height: Optional[int] = None


class ExtractedArticle(BaseModel):
    source_name: str
    source_domain: str
    original_url: str
    canonical_url: str
    content_hash: str
    original_title: str
    original_subtitle: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    paragraphs: List[str] = Field(default_factory=list)
    raw_body_text: str = ""
    main_image: Optional[ExtractedImage] = None
    gallery_images: List[ExtractedImage] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    raw_html: Optional[str] = None
    category_hint: Optional[str] = None

    @model_validator(mode="after")
    def populate_defaults(self) -> "ExtractedArticle":
        if not self.raw_body_text and self.paragraphs:
            self.raw_body_text = "\n\n".join(self.paragraphs)
        return self


# ==============================================================================
# 3. 5-Tier Fallback Cascade Extractors
# ==============================================================================

def extract_json_ld(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    """Tier 2: Extracts schema.org structured JSON-LD (NewsArticle/Article/BlogPosting)."""
    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string or script.text
        if not text or not text.strip():
            continue
        try:
            data = json.loads(text.strip(), strict=False)
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                if "@graph" in data and isinstance(data["@graph"], list):
                    items = data["@graph"]
                else:
                    items = [data]

            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    types_set = set(item_type)
                else:
                    types_set = {item_type}

                if types_set & {"NewsArticle", "Article", "BlogPosting", "Report", "LiveBlogPosting"}:
                    return item
        except Exception:
            continue
    return None


def extract_opengraph(soup: BeautifulSoup) -> Dict[str, str]:
    """Tier 3: Extracts OpenGraph and Twitter Card metadata."""
    og: Dict[str, str] = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name") or ""
        content = meta.get("content") or ""
        if prop and content:
            prop_clean = prop.lower().strip()
            if prop_clean in {
                "og:title", "og:description", "og:image", "og:url", "og:site_name",
                "article:published_time", "article:author", "article:tag", "article:section",
                "twitter:title", "twitter:description", "twitter:image"
            }:
                og[prop_clean] = clean_html_text(content)
    return og


def extract_trafilatura(html_content: str, url: str) -> Optional[Dict[str, Any]]:
    """Tier 4: Automated boilerplate removal via Trafilatura."""
    if not trafilatura or not html_content:
        return None
    try:
        extracted = trafilatura.extract(
            html_content,
            url=url,
            include_images=True,
            include_links=False,
            output_format="python",
            favor_recall=True,
        )
        if isinstance(extracted, dict) and extracted.get("text"):
            return extracted
    except Exception:
        pass
    return None


def extract_heuristic_dom(soup: BeautifulSoup) -> Dict[str, Any]:
    """Tier 5: Resilient heuristic DOM cleaner extracting title, body paragraphs, and lead image."""
    soup_copy = BeautifulSoup(str(soup), "html.parser")
    # Remove unneeded elements
    for tag in soup_copy.find_all(["script", "style", "nav", "footer", "aside", "header", "iframe", "noscript", "svg", "form"]):
        tag.decompose()

    # Title heuristics
    title = ""
    h1 = soup_copy.find("h1")
    if h1 and clean_html_text(h1.text):
        title = clean_html_text(h1.text)
    elif soup_copy.title and clean_html_text(soup_copy.title.text):
        title = clean_html_text(soup_copy.title.text)

    # Paragraphs extraction
    paragraphs: List[str] = []
    p_tags = soup_copy.find_all("p")
    for p in p_tags:
        txt = clean_html_text(p.text)
        if len(txt) >= 20 and not re.search(r"^(כל הזכויות שמורות|תנאי שימוש|צילום:|פורסם:)", txt):
            paragraphs.append(txt)

    # Main image heuristic
    main_image_url = None
    for img in soup_copy.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if src and src.startswith(("http://", "https://", "//")):
            if not re.search(r"(logo|icon|avatar|banner|pixel|spacer|button|ad-|advert)", src, re.I):
                main_image_url = src if src.startswith("http") else "https:" + src
                break

    return {
        "title": title,
        "paragraphs": paragraphs,
        "main_image_url": main_image_url,
    }


# ==============================================================================
# 4. BaseSourceParser Abstract Class
# ==============================================================================

class BaseSourceParser:
    """Abstract base class for Israeli sports news scrapers with polite HTTP client support,
    5-tier extraction cascade, and Hebrew content sanitization.
    """
    source_name: str = "Base"
    source_code: str = "base"
    source_domain: str = "example.com"
    base_url: str = "https://example.com"
    feed_urls: List[str] = []
    discovery_urls: List[str] = []

    DEFAULT_HEADERS: Dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 (FanZoneSportsBot/1.0; +https://github.com/amittima1234/fan-zone)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
    }

    async def discover_articles(self, client: httpx.AsyncClient) -> List[str]:
        """Discovers new article candidate URLs from RSS feeds and discovery sections."""
        discovered_urls: Set[str] = set()

        # 1. Fetch RSS feeds if defined
        for feed_url in self.feed_urls:
            try:
                resp = await client.get(feed_url, headers=self.DEFAULT_HEADERS, timeout=10.0)
                if resp.status_code == 200 and resp.text:
                    feed_links = self.parse_rss_feed(resp.text)
                    for link in feed_links:
                        canon = normalize_canonical_url(link)
                        if self.is_valid_article_url(canon):
                            discovered_urls.add(canon)
            except Exception as e:
                logger.warning(f"Error fetching RSS feed {feed_url} for {self.source_name}: {e}")

        # 2. Fetch Discovery section URLs
        for disc_url in self.discovery_urls:
            try:
                resp = await client.get(disc_url, headers=self.DEFAULT_HEADERS, timeout=10.0)
                if resp.status_code == 200 and resp.text:
                    section_links = self.extract_article_links_from_section(resp.text, disc_url)
                    for link in section_links:
                        canon = normalize_canonical_url(link)
                        if self.is_valid_article_url(canon):
                            discovered_urls.add(canon)
            except Exception as e:
                logger.warning(f"Error discovering section {disc_url} for {self.source_name}: {e}")

        return sorted(list(discovered_urls))

    def extract_article_links_from_section(self, html_content: str, section_url: str) -> List[str]:
        """Extracts article candidate links from section HTML."""
        soup = BeautifulSoup(html_content, "html.parser")
        links: Set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            full_url = urljoin(section_url, href)
            canon = normalize_canonical_url(full_url)
            if self.is_valid_article_url(canon):
                links.add(canon)
        return list(links)

    def is_valid_article_url(self, url: str) -> bool:
        """Determines whether a given URL belongs to this source's article pattern."""
        if not url or self.source_domain not in url.lower():
            return False
        return True

    def parse_rss_feed(self, xml_content: str) -> List[str]:
        """Parses RSS/Atom XML feed content and returns article URLs.
        Falls back to html.parser if xml parser fails or drops broken headers.
        """
        if not xml_content or not xml_content.strip():
            return []
        
        links: List[str] = []
        # Attempt 1: XML parser
        try:
            soup = BeautifulSoup(xml_content, "xml")
            for item in soup.find_all(["item", "entry"]):
                link_tag = item.find("link")
                if link_tag:
                    url_val = link_tag.get("href") or link_tag.text or ""
                    if url_val.strip():
                        links.append(url_val.strip())
        except Exception:
            pass

        # Attempt 2: Fallback to html.parser if 0 links extracted
        if not links:
            try:
                soup = BeautifulSoup(xml_content, "html.parser")
                for item in soup.find_all(["item", "entry"]):
                    link_tag = item.find("link")
                    if link_tag:
                        url_val = link_tag.get("href") or link_tag.text or ""
                        if url_val.strip():
                            links.append(url_val.strip())
            except Exception:
                pass

        # Attempt 3: Regex fallback if still empty
        if not links:
            url_matches = re.findall(r"<link(?:[^>]*href=[\"']([^\"']+)[\"']|[^>]*>([^<]+)</link>)", xml_content, re.IGNORECASE)
            for m1, m2 in url_matches:
                val = (m1 or m2 or "").strip()
                if val.startswith("http"):
                    links.append(val)

        return links

    async def parse_article(self, client: httpx.AsyncClient, url: str) -> Optional[ExtractedArticle]:
        """Asynchronously downloads and parses article HTML into structured ExtractedArticle."""
        canon_url = normalize_canonical_url(url)
        try:
            resp = await client.get(canon_url, headers=self.DEFAULT_HEADERS, timeout=12.0, follow_redirects=True)
            if resp.status_code != 200 or not resp.text:
                logger.warning(f"Failed to fetch article {canon_url}, status: {resp.status_code}")
                return None
            return self.parse_article_html(resp.text, canon_url)
        except Exception as e:
            logger.error(f"Exception downloading article {canon_url}: {e}")
            return None

    def parse_article_html(self, html_content: str, url: str) -> Optional[ExtractedArticle]:
        """Executes the 5-tier extraction cascade to parse article HTML."""
        if not html_content or not html_content.strip():
            return None

        soup = BeautifulSoup(html_content, "html.parser")
        canonical_url = normalize_canonical_url(url)

        # -------------------------------------------------------------
        # Tier 1: Source-Specific CSS Selectors
        # -------------------------------------------------------------
        t1_title = self._extract_css_title(soup)
        t1_subtitle = self._extract_css_subtitle(soup)
        t1_author = self._extract_css_author(soup)
        t1_published_at = self._extract_css_date(soup)
        t1_paragraphs = self._extract_css_paragraphs(soup)
        t1_main_image, t1_gallery = self._extract_css_images(soup, canonical_url)
        t1_tags = self._extract_css_tags(soup)

        # -------------------------------------------------------------
        # Tier 2: Schema.org JSON-LD structured data
        # -------------------------------------------------------------
        json_ld = extract_json_ld(soup) or {}
        ld_title = clean_html_text(json_ld.get("headline"))
        ld_desc = clean_html_text(json_ld.get("description"))
        ld_body_raw = json_ld.get("articleBody")
        if isinstance(ld_body_raw, list):
            ld_body = "\n".join([clean_html_text(p) for p in ld_body_raw if clean_html_text(p)])
        elif isinstance(ld_body_raw, str):
            ld_body = clean_html_text(ld_body_raw, preserve_newlines=True)
        else:
            ld_body = ""
        ld_date_str = json_ld.get("datePublished") or json_ld.get("dateCreated")
        ld_date = parse_datetime(ld_date_str) if ld_date_str else None
        ld_author = None
        if isinstance(json_ld.get("author"), dict):
            ld_author = clean_html_text(json_ld["author"].get("name"))
        elif isinstance(json_ld.get("author"), list) and json_ld["author"]:
            first_auth = json_ld["author"][0]
            ld_author = clean_html_text(first_auth.get("name") if isinstance(first_auth, dict) else str(first_auth))
        elif isinstance(json_ld.get("author"), str):
            ld_author = clean_html_text(json_ld.get("author"))

        ld_img_url = None
        if isinstance(json_ld.get("image"), dict):
            ld_img_url = json_ld["image"].get("url")
        elif isinstance(json_ld.get("image"), list) and json_ld["image"]:
            first_img = json_ld["image"][0]
            ld_img_url = first_img.get("url") if isinstance(first_img, dict) else str(first_img)
        elif isinstance(json_ld.get("image"), str):
            ld_img_url = json_ld.get("image")

        # -------------------------------------------------------------
        # Tier 3: OpenGraph & Twitter Meta Tags
        # -------------------------------------------------------------
        og = extract_opengraph(soup)
        og_title = og.get("og:title") or og.get("twitter:title") or ""
        og_desc = og.get("og:description") or og.get("twitter:description") or ""
        og_img_url = og.get("og:image") or og.get("twitter:image") or ""
        og_date_str = og.get("article:published_time")
        og_date = parse_datetime(og_date_str) if og_date_str else None
        og_author = og.get("article:author")

        # -------------------------------------------------------------
        # Tier 4: Trafilatura Boilerplate Removal
        # -------------------------------------------------------------
        traf = extract_trafilatura(html_content, canonical_url) or {}
        traf_title = clean_html_text(traf.get("title"))
        traf_text = traf.get("text") or ""
        traf_paragraphs = [p.strip() for p in traf_text.split("\n") if p.strip() and len(p.strip()) >= 15]

        # -------------------------------------------------------------
        # Tier 5: Semantic DOM Heuristic
        # -------------------------------------------------------------
        dom_fallback = extract_heuristic_dom(soup)

        # -------------------------------------------------------------
        # Cascade Consolidation
        # -------------------------------------------------------------
        final_title = (
            t1_title
            or ld_title
            or og_title
            or traf_title
            or dom_fallback.get("title")
            or "ידיעת ספורט"
        )
        final_subtitle = t1_subtitle or ld_desc or og_desc or None
        final_author = t1_author or ld_author or og_author or traf.get("author") or None
        if final_author:
            final_author = re.sub(r"^מאת[:\s\-]+", "", final_author).strip() or final_author
        final_published_at = t1_published_at or ld_date or og_date or datetime.now(timezone.utc)

        # Paragraphs consolidation
        final_paragraphs = t1_paragraphs
        if not final_paragraphs or len(final_paragraphs) == 0:
            if ld_body:
                final_paragraphs = [p.strip() for p in re.split(r"\n+", ld_body) if p.strip()]
            elif traf_paragraphs:
                final_paragraphs = traf_paragraphs
            else:
                final_paragraphs = dom_fallback.get("paragraphs") or []

        if not final_paragraphs and final_subtitle:
            final_paragraphs = [final_subtitle]

        raw_body_text = "\n\n".join(final_paragraphs)

        # Main image consolidation
        final_main_image = t1_main_image
        if not final_main_image:
            img_url = ld_img_url or og_img_url or dom_fallback.get("main_image_url")
            if img_url:
                final_main_image = ExtractedImage(
                    url=img_url if img_url.startswith("http") else urljoin(canonical_url, img_url),
                    is_main=True,
                )

        # Tags consolidation
        final_tags = list(set(t1_tags + ([og.get("article:tag")] if og.get("article:tag") else [])))

        # Content hash
        content_hash = compute_content_hash(final_title, final_paragraphs)

        return ExtractedArticle(
            source_name=self.source_name,
            source_domain=self.source_domain,
            original_url=url,
            canonical_url=canonical_url,
            content_hash=content_hash,
            original_title=final_title,
            original_subtitle=final_subtitle,
            author=final_author,
            published_at=final_published_at,
            paragraphs=final_paragraphs,
            raw_body_text=raw_body_text,
            main_image=final_main_image,
            gallery_images=t1_gallery,
            tags=final_tags,
            raw_html=html_content,
        )

    # Protected CSS selector hooks to be implemented/overridden by concrete subclasses
    def _extract_css_title(self, soup: BeautifulSoup) -> Optional[str]:
        return None

    def _extract_css_subtitle(self, soup: BeautifulSoup) -> Optional[str]:
        return None

    def _extract_css_author(self, soup: BeautifulSoup) -> Optional[str]:
        return None

    def _extract_css_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        return None

    def _extract_css_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        return []

    def _extract_css_images(self, soup: BeautifulSoup, base_url: str) -> Tuple[Optional[ExtractedImage], List[ExtractedImage]]:
        return None, []

    def _extract_css_tags(self, soup: BeautifulSoup) -> List[str]:
        return []
