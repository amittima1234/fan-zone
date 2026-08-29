"""Scraper for Haaretz Sport (haaretz.co.il/sport)."""

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


class HaaretzParser(BaseSourceParser):
    """Scraper for Haaretz Sport (haaretz.co.il/sport)."""
    source_name = "Haaretz"
    source_code = "haaretz"
    source_domain = "haaretz.co.il"
    base_url = "https://www.haaretz.co.il/sport"
    feed_urls = ["https://www.haaretz.co.il/cmlink/1.144754"]
    discovery_urls = ["https://www.haaretz.co.il/sport"]

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        return "/sport" in url.lower()

    def _extract_css_title(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h1[data-test='articleHeadline']", "h1.t-article-headline", "h1.entry-title", "h1"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_subtitle(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h2[data-test='articleSubtitle']", "p.t-article-subtitle", "h2.subtitle", "h2"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_author(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["span[data-test='authorName']", "a[rel='author']", "div.t-author-name", "span.author"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        for sel in ["time[data-test='publishDate']", "time", "span.publish-date"]:
            tag = soup.select_one(sel)
            if tag:
                dt_str = tag.get("datetime") or tag.text
                if dt_str:
                    return parse_datetime(dt_str)
        return None

    def _extract_css_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        paragraphs: List[str] = []
        for container_sel in ["article[data-test='articleBody']", "article.b-article", "div.article-text", "article"]:
            container = soup.select_one(container_sel)
            if container:
                # Use CSS selector to match both p and div[data-test='articleParagraph']
                for p in container.select("p, div[data-test='articleParagraph']"):
                    txt = clean_html_text(p.text)
                    if len(txt) >= 15:
                        paragraphs.append(txt)
                if paragraphs:
                    return paragraphs
        return paragraphs

    def _extract_css_images(self, soup: BeautifulSoup, base_url: str) -> Tuple[Optional[ExtractedImage], List[ExtractedImage]]:
        lead_img = None
        gallery: List[ExtractedImage] = []

        main_img = soup.select_one("figure[data-test='mainFigure'] img, div.hero-image img, figure img")
        if main_img:
            src = main_img.get("src") or main_img.get("data-src")
            if src:
                caption_tag = soup.select_one("figcaption[data-test='caption'], span.credit, figcaption")
                caption = clean_html_text(caption_tag.text) if caption_tag else None
                lead_img = ExtractedImage(
                    url=src if src.startswith("http") else urljoin(base_url, src),
                    caption=caption,
                    is_main=True,
                )

        for img in soup.select("figure[data-test='articleFigure'] img"):
            src = img.get("src") or img.get("data-src")
            if src and (not lead_img or src != lead_img.url):
                gallery.append(ExtractedImage(url=src if src.startswith("http") else urljoin(base_url, src)))

        return lead_img, gallery
