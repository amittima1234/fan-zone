"""Scraper for Ynet Sport (ynet.co.il/sport)."""

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


class YnetParser(BaseSourceParser):
    """Scraper for Ynet Sport (ynet.co.il/sport)."""
    source_name = "Ynet Sport"
    source_code = "ynet"
    source_domain = "ynet.co.il"
    base_url = "https://www.ynet.co.il/sport"
    feed_urls = ["https://www.ynet.co.il/Integration/StoryRss3.xml"]
    discovery_urls = [
        "https://www.ynet.co.il/sport",
        "https://www.ynet.co.il/sport/israelisoccer",
        "https://www.ynet.co.il/sport/worldsoccer",
        "https://www.ynet.co.il/sport/israelibasketball",
    ]

    def is_valid_article_url(self, url: str) -> bool:
        if not super().is_valid_article_url(url):
            return False
        return bool(re.search(r"(?:/sport)?/(?:[^/]+/)?article/[a-zA-Z0-9]+|/articles/\d+", url, re.I))

    def _extract_css_title(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h1.mainTitle", "h1[data-component='headline']", "h1.title", "h1"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_subtitle(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["h2.subTitle", "div.subTitle", "h2[data-component='subheadline']", "h2"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_author(self, soup: BeautifulSoup) -> Optional[str]:
        for sel in ["span.authorName", "div.authorName", ".authorName", "span.authors", "div[data-component='author-details']", "span.author", "div.author"]:
            tag = soup.select_one(sel)
            if tag and clean_html_text(tag.text):
                return clean_html_text(tag.text)
        return None

    def _extract_css_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        for sel in ["time.date", "div.dateDisplay", "span[data-component='publish-date']", "time"]:
            tag = soup.select_one(sel)
            if tag:
                dt_str = tag.get("datetime") or tag.text
                if dt_str:
                    return parse_datetime(dt_str)
        return None

    def _extract_css_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        paragraphs: List[str] = []
        for container_sel in ["div.text_editor_paragraph", "div[data-component='article-body']", "div.text14", "div.article-paragraphs", "article"]:
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

        main_img = soup.select_one("figure[data-component='media'] img, div.media-wrapper img, figure.main-image img")
        if main_img:
            src = main_img.get("src") or main_img.get("data-src")
            if src:
                caption_tag = soup.select_one("figcaption .caption, figcaption .credit, span.photoCredit")
                caption = clean_html_text(caption_tag.text) if caption_tag else None
                lead_img = ExtractedImage(
                    url=src if src.startswith("http") else urljoin(base_url, src),
                    caption=caption,
                    is_main=True,
                )

        for img in soup.select("div[data-component='gallery'] img, figure.gallery-image img"):
            src = img.get("src") or img.get("data-src")
            if src and (not lead_img or src != lead_img.url):
                gallery.append(ExtractedImage(url=src if src.startswith("http") else urljoin(base_url, src)))

        return lead_img, gallery
