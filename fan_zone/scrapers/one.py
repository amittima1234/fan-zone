"""Scraper for ONE (one.co.il)."""

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


class ONEParser(BaseSourceParser):
    """Scraper for ONE (one.co.il)."""
    source_name = "ONE"
    source_code = "one"
    source_domain = "one.co.il"
    base_url = "https://www.one.co.il"
    feed_urls = [
        "https://www.one.co.il/cat/rss/rss.aspx",
        "https://www.one.co.il/cat/coop/xml/rss/newsfeed.aspx",
        "https://www.one.co.il/cat/rss/rss.aspx?t=1",  # Soccer
        "https://www.one.co.il/cat/rss/rss.aspx?t=2",  # Basketball
    ]
    discovery_urls = ["https://www.one.co.il"]

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        return bool(re.search(r"/article/(?:[0-9-]+/)?[0-9]+\.html", url, re.I))

    def _extract_css_title(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h1.article-title", "h1.main-title", "h1#article_title", "h1"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_subtitle(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h2.article-subtitle", "div.article-sub-title", "h2.sub-title", "h2"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_author(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["span.article-writer", "div.article-author", "span.writer-name", "span.author"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        for sel in ["span.article-date", "span.date", "div.article-time", "time"]:
            tag = soup.select_one(sel)
            if tag:
                return parse_datetime(tag.text)
        return None

    def _extract_css_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        paragraphs: List[str] = []
        for container_sel in ["div.article-body-content", "div#article-content", "div#article_body", "div.text_area"]:
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

        main_img = soup.select_one("div.article-main-img img, div.main-img-wrap img")
        if main_img:
            src = main_img.get("src") or main_img.get("data-src")
            if src:
                credit_tag = soup.select_one("div.img-credit, span.photo-credit, div.article-img-caption")
                credit = clean_html_text(credit_tag.text) if credit_tag else None
                lead_img = ExtractedImage(
                    url=src if src.startswith("http") else urljoin(base_url, src),
                    credit=credit,
                    is_main=True,
                )

        for img in soup.select("div.article-gallery-item img, div.content-images img"):
            src = img.get("src") or img.get("data-src")
            if src and (not lead_img or src != lead_img.url):
                gallery.append(ExtractedImage(url=src if src.startswith("http") else urljoin(base_url, src)))

        return lead_img, gallery
