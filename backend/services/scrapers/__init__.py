"""Scraper module exports for Israeli sports portals."""

from services.scrapers.base import (
    BaseScraper,
    sanitize_article_text,
    truncate_article_text,
)
from services.scrapers.one import ONEScraper
from services.scrapers.registry import (
    SCRAPER_REGISTRY,
    get_all_scrapers,
    get_scraper,
    register_scraper,
)
from services.scrapers.sport5 import Sport5Scraper
from services.scrapers.walla import WallaScraper
from services.scrapers.ynet import YnetScraper

__all__ = [
    "BaseScraper",
    "Sport5Scraper",
    "YnetScraper",
    "ONEScraper",
    "WallaScraper",
    "SCRAPER_REGISTRY",
    "get_scraper",
    "get_all_scrapers",
    "register_scraper",
    "sanitize_article_text",
    "truncate_article_text",
]
