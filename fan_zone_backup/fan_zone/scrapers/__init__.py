"""Multi-source scrapers and parser registry for Israeli sports news outlets."""

from fan_zone.scrapers.base import (
    BaseSourceParser,
    ExtractedArticle,
    ExtractedImage,
    clean_html_text,
    compute_content_hash,
    extract_heuristic_dom,
    extract_json_ld,
    extract_opengraph,
    extract_trafilatura,
    normalize_canonical_url,
    parse_datetime,
)
from fan_zone.scrapers.sport5 import Sport5Parser
from fan_zone.scrapers.one import ONEParser
from fan_zone.scrapers.walla import WallaParser
from fan_zone.scrapers.ynet import YnetParser
from fan_zone.scrapers.sport1 import Sport1Parser
from fan_zone.scrapers.israel_hayom import IsraelHayomParser
from fan_zone.scrapers.haaretz import HaaretzParser
from fan_zone.scrapers.registry import (
    ScraperRegistry,
    get_scraper,
    get_scraper_for_url,
    list_scrapers,
    register_scraper,
)

__all__ = [
    "BaseSourceParser",
    "ExtractedArticle",
    "ExtractedImage",
    "clean_html_text",
    "compute_content_hash",
    "extract_heuristic_dom",
    "extract_json_ld",
    "extract_opengraph",
    "extract_trafilatura",
    "normalize_canonical_url",
    "parse_datetime",
    "Sport5Parser",
    "ONEParser",
    "WallaParser",
    "YnetParser",
    "Sport1Parser",
    "IsraelHayomParser",
    "HaaretzParser",
    "ScraperRegistry",
    "get_scraper",
    "get_scraper_for_url",
    "list_scrapers",
    "register_scraper",
]
