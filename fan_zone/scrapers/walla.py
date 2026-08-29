"""Scraper for Walla! Sports (sports.walla.co.il / walla.co.il)."""

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


class WallaParser(BaseSourceParser):
    """Scraper for Walla! Sports (sports.walla.co.il / walla.co.il)."""
    source_name = "Walla! Sports"
    source_code = "walla"
    source_domain = "walla.co.il"
    base_url = "https://sports.walla.co.il"
    feed_urls = [
        "https://rss.walla.co.il/feed/3",    # Sports Main
        "https://rss.walla.co.il/feed/175",  # Israeli Soccer
        "https://rss.walla.co.il/feed/151",  # Israeli Basketball
        "https://rss.walla.co.il/feed/156",  # World Soccer
    ]
    discovery_urls = ["https://sports.walla.co.il"]

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        return bool(re.search(r"/item/\d+", url, re.I))

    def _extract_css_title(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h1.title", "h1[data-testid='article-title']", "h1.css-title", "h1"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_subtitle(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h2.subtitle", "p.css-subtitle", "div.subtitle", "h2"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_author(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["div.author", "span.author-name", ".author", "div.css-author", "div.article-author span", "div.article-author", "span.author"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        for sel in ["time", "span.date", "div.css-date"]:
            tag = soup.select_one(sel)
            if tag:
                dt_str = tag.get("datetime") or tag.text
                if dt_str:
                    return parse_datetime(dt_str)
        return None

    def _extract_css_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        paragraphs: List[str] = []
        for container_sel in ["div.css-article-body", "section.article-content", "div.article-text", "article"]:
            container = soup.select_one(container_sel)
            if container:
                for p in container.find_all("p"):
                    txt = clean_html_text(p.text)
                    if len(txt) >= 15:
                        paragraphs.append(txt)
                if paragraphs:
                    return paragraphs
        return paragraphs

    def _extract_css_images(self, soup: BeautifulSoup, base_url: str) -> Tuple[Optional[ExtractedImage], List[ExtractedImage]]:
        lead_img = None
        gallery: List[ExtractedImage] = []

        main_img = soup.select_one("figure.main-media img, div.article-media img, figure img")
        if main_img:
            src = main_img.get("src") or main_img.get("data-src")
            if src:
                caption_tag = soup.select_one("figcaption, span.credit, p.media-caption")
                caption = clean_html_text(caption_tag.text) if caption_tag else None
                lead_img = ExtractedImage(
                    url=src if src.startswith("http") else urljoin(base_url, src),
                    caption=caption,
                    is_main=True,
                )

        for img in soup.select("figure.gallery-item img, div.media-gallery img"):
            src = img.get("src") or img.get("data-src")
            if src and (not lead_img or src != lead_img.url):
                gallery.append(ExtractedImage(url=src if src.startswith("http") else urljoin(base_url, src)))

        return lead_img, gallery
