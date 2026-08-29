"""Scraper for Sport5 (sport5.co.il)."""

from datetime import datetime
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from fan_zone.scrapers.base import (
    BaseSourceParser,
    ExtractedImage,
    clean_html_text,
    parse_datetime,
)


class Sport5Parser(BaseSourceParser):
    """Scraper for Sport5 (sport5.co.il)."""
    source_name = "Sport5"
    source_code = "sport5"
    source_domain = "sport5.co.il"
    base_url = "https://www.sport5.co.il"
    discovery_urls = [
        "https://www.sport5.co.il",
        "https://www.sport5.co.il/articles.aspx?FolderID=64",   # Israeli Football
        "https://www.sport5.co.il/articles.aspx?FolderID=274",  # Israeli Basketball
        "https://www.sport5.co.il/articles.aspx?FolderID=394",  # World Football
        "https://www.sport5.co.il/articles.aspx?FolderID=405",  # NBA
    ]

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        # Matches: sport5.co.il/articles.aspx?FolderID=...&docID=...
        return bool(re.search(r"articles\.aspx\?.*(docid|folderid)", url, re.I))

    def _extract_css_title(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h1.article-title", "h1.title", "h1.art_title", "h1.main-title", "h1"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_subtitle(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h2.article-subtitle", "div.article-sub-title", "h2.subtitle", "h2.sub_title", "h2"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_author(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in [
            "div.article-credit",
            "span.article-credit",
            ".article-credit",
            "span.writer",
            "div.author-name a",
            "div.art_author",
            "span.author",
            "div.author",
            "span.art_author",
            "div.writer",
            "a.author-name",
        ]:
            tag = soup.select_one(sel)
            if tag:
                txt = clean_html_text(tag.text)
                if txt:
                    # Clean any leading credit prefixes and whitespace
                    txt = re.sub(r"^(?:מאת|כתב|עריכה|מערכת|צילום|קרדיט)\s*:\s*", "", txt).strip()
                    txt = re.sub(r"^(?:מאת|כתב)\s+", "", txt).strip()
                    if txt:
                        return txt
        return None

    def _extract_css_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        for sel in ["span.article-date", "time", "div.art_date", "span.date"]:
            tag = soup.select_one(sel)
            if tag:
                dt_str = tag.get("datetime") or tag.text
                if dt_str:
                    return parse_datetime(dt_str)
        return None

    def _extract_css_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        paragraphs: List[str] = []
        for container_sel in ["div.article-body", "div.art_body", "div.article-text", "div.article-content"]:
            container = soup.select_one(container_sel)
            if container:
                for p in container.find_all("p"):
                    txt = clean_html_text(p.text)
                    if len(txt) >= 15 and not txt.startswith(("צילום:", "קרדיט:")):
                        paragraphs.append(txt)
                if paragraphs:
                    return paragraphs
        return paragraphs

    def _extract_css_images(self, soup: BeautifulSoup, base_url: str) -> Tuple[Optional[ExtractedImage], List[ExtractedImage]]:
        lead_img = None
        gallery: List[ExtractedImage] = []

        # Lead image
        main_img_elem = soup.select_one("div.article-main-image img, figure.main-image img, div.main-image img")
        if main_img_elem:
            src = main_img_elem.get("src") or main_img_elem.get("data-src")
            if src:
                caption_elem = soup.select_one("div.main-image-caption, span.image-credit, figcaption")
                caption = clean_html_text(caption_elem.text) if caption_elem else None
                lead_img = ExtractedImage(
                    url=src if src.startswith("http") else urljoin(base_url, src),
                    caption=caption,
                    is_main=True,
                )

        # Gallery
        for img in soup.select("div.article-gallery img, div.art_media img"):
            src = img.get("src") or img.get("data-src")
            if src and (not lead_img or src != lead_img.url):
                gallery.append(ExtractedImage(url=src if src.startswith("http") else urljoin(base_url, src)))

        return lead_img, gallery

    def _extract_css_tags(self, soup: BeautifulSoup) -> List[str]:
        tags = []
        for a in soup.select("div.article-tags a, ul.tags li a"):
            t = clean_html_text(a.text)
            if t:
                tags.append(t)
        return tags
