"""Scraper for Israel Hayom Sport (israelhayom.co.il/sport)."""

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


class IsraelHayomParser(BaseSourceParser):
    """Scraper for Israel Hayom Sport (israelhayom.co.il/sport)."""
    source_name = "Israel Hayom"
    source_code = "israel_hayom"
    source_domain = "israelhayom.co.il"
    base_url = "https://www.israelhayom.co.il/sport"
    discovery_urls = [
        "https://www.israelhayom.co.il/sport",
        "https://www.israelhayom.co.il/sport/israeli-soccer",
        "https://www.israelhayom.co.il/sport/world-soccer",
        "https://www.israelhayom.co.il/sport/israeli-basketball",
        "https://www.israelhayom.co.il/sport/nba",
    ]

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        return bool(re.search(r"/sport/(?:[^/]+/)?article/\d+", url, re.I))

    def _extract_css_title(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h1.article-title", "h1.post-title", "h1.main-title", "h1"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_subtitle(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h2.article-subtitle", "div.article-sub-headline", "h2.subtitle", "h2"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_author(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["div.writer-name", "span.author", "div.byline-author"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        for sel in ["time.article-date", "div.publish-time", "span.date", "time"]:
            tag = soup.select_one(sel)
            if tag:
                dt_str = tag.get("datetime") or tag.text
                if dt_str:
                    return parse_datetime(dt_str)
        return None

    def _extract_css_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        paragraphs: List[str] = []
        for container_sel in ["div.article-content", "div.text-content", "div.article-body", "article"]:
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

        main_img = soup.select_one("div.article-main-media img, figure.main-image img, figure img")
        if main_img:
            src = main_img.get("src") or main_img.get("data-src")
            if src:
                caption_tag = soup.select_one("figcaption .credit, div.media-caption, span.credit")
                caption = clean_html_text(caption_tag.text) if caption_tag else None
                lead_img = ExtractedImage(
                    url=src if src.startswith("http") else urljoin(base_url, src),
                    caption=caption,
                    is_main=True,
                )

        for img in soup.select("div.article-gallery img, figure.gallery-photo img"):
            src = img.get("src") or img.get("data-src")
            if src and (not lead_img or src != lead_img.url):
                gallery.append(ExtractedImage(url=src if src.startswith("http") else urljoin(base_url, src)))

        return lead_img, gallery
