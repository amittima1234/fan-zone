"""Scraper registry and dispatcher for Fan Zone sports news portals."""

from typing import Dict, List, Type

from services.scrapers.base import BaseScraper
from services.scrapers.one import ONEScraper
from services.scrapers.sport5 import Sport5Scraper
from services.scrapers.walla import WallaScraper
from services.scrapers.ynet import YnetScraper

# Central registry mapping lowercase publisher identifiers to scraper classes
SCRAPER_REGISTRY: Dict[str, Type[BaseScraper]] = {
    "sport5": Sport5Scraper,
    "ynet": YnetScraper,
    "one": ONEScraper,
    "walla": WallaScraper,
}


def register_scraper(publisher_id: str, scraper_cls: Type[BaseScraper]) -> None:
    """Register or override a scraper class for a publisher identifier."""
    if not publisher_id or not isinstance(publisher_id, str):
        raise ValueError("publisher_id must be a non-empty string")
    SCRAPER_REGISTRY[publisher_id.lower().strip()] = scraper_cls


def get_scraper(publisher_id: str, **kwargs) -> BaseScraper:
    """Retrieve and instantiate a scraper by its publisher identifier.

    Args:
        publisher_id: Normalized publisher key (e.g. 'sport5', 'ynet', 'one').
        **kwargs: Optional initialization arguments passed to scraper constructor.

    Returns:
        Instantiated BaseScraper subclass.

    Raises:
        ValueError: If publisher_id is unknown or unregistered.
    """
    key = publisher_id.lower().strip()
    scraper_cls = SCRAPER_REGISTRY.get(key)
    if not scraper_cls:
        available = list(SCRAPER_REGISTRY.keys())
        raise ValueError(f"Unknown publisher '{publisher_id}'. Available scrapers: {available}")
    return scraper_cls(**kwargs)


def get_all_scrapers(**kwargs) -> List[BaseScraper]:
    """Instantiate and return all registered scrapers.

    Args:
        **kwargs: Optional initialization arguments passed to all scraper constructors.

    Returns:
        List of initialized BaseScraper instances.
    """
    return [cls(**kwargs) for cls in SCRAPER_REGISTRY.values()]
