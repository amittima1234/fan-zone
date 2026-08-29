"""Central registry maintaining active parser instances for all Israeli sports sources."""

from typing import Dict, List, Optional

from fan_zone.scrapers.base import BaseSourceParser
from fan_zone.scrapers.sport5 import Sport5Parser
from fan_zone.scrapers.one import ONEParser
from fan_zone.scrapers.walla import WallaParser
from fan_zone.scrapers.ynet import YnetParser
from fan_zone.scrapers.sport1 import Sport1Parser
from fan_zone.scrapers.israel_hayom import IsraelHayomParser
from fan_zone.scrapers.haaretz import HaaretzParser


class ScraperRegistry:
    """Central registry maintaining active parser instances for all Israeli sports sources."""

    def __init__(self) -> None:
        self._parsers: Dict[str, BaseSourceParser] = {}
        # Register standard 7 parsers
        self.register(Sport5Parser())
        self.register(ONEParser())
        self.register(WallaParser())
        self.register(YnetParser())
        self.register(Sport1Parser())
        self.register(IsraelHayomParser())
        self.register(HaaretzParser())

    def register(self, parser: BaseSourceParser) -> None:
        """Registers a source parser by code and name."""
        self._parsers[parser.source_code.lower()] = parser
        self._parsers[parser.source_name.lower()] = parser
        if parser.source_code.lower() == "israel_hayom":
            self._parsers["israelhayom"] = parser
        elif parser.source_code.lower() == "israelhayom":
            self._parsers["israel_hayom"] = parser

    def get_scraper(self, name_or_code: str) -> Optional[BaseSourceParser]:
        """Retrieves a parser by source code or display name."""
        if not name_or_code:
            return None
        cleaned = name_or_code.lower().strip()
        # Direct lookup
        if cleaned in self._parsers:
            return self._parsers[cleaned]
        # Partial match
        for key, parser in self._parsers.items():
            if key in cleaned or cleaned in key:
                return parser
        return None

    def get_scraper_for_url(self, url: str) -> Optional[BaseSourceParser]:
        """Automatically detects the appropriate parser for a given article URL."""
        if not url:
            return None
        url_lower = url.lower()
        if "sport5.co.il" in url_lower:
            return self._parsers.get("sport5")
        if "one.co.il" in url_lower:
            return self._parsers.get("one")
        if "walla.co.il" in url_lower:
            return self._parsers.get("walla")
        if "ynet.co.il" in url_lower:
            return self._parsers.get("ynet")
        if "sport1.maariv.co.il" in url_lower or "maariv.co.il" in url_lower:
            return self._parsers.get("sport1")
        if "israelhayom.co.il" in url_lower:
            return self._parsers.get("israel_hayom") or self._parsers.get("israelhayom")
        if "haaretz.co.il" in url_lower:
            return self._parsers.get("haaretz")
        return None

    def list_scrapers(self) -> List[BaseSourceParser]:
        """Returns a list of unique registered parser instances."""
        seen = set()
        unique = []
        for parser in self._parsers.values():
            if parser.source_code not in seen:
                seen.add(parser.source_code)
                unique.append(parser)
        return unique

    def get_all_scrapers(self) -> List[BaseSourceParser]:
        """Alias for list_scrapers."""
        return self.list_scrapers()


_GLOBAL_REGISTRY = ScraperRegistry()


def get_scraper(name_or_code: str) -> Optional[BaseSourceParser]:
    return _GLOBAL_REGISTRY.get_scraper(name_or_code)


def get_scraper_for_url(url: str) -> Optional[BaseSourceParser]:
    return _GLOBAL_REGISTRY.get_scraper_for_url(url)


def list_scrapers() -> List[BaseSourceParser]:
    return _GLOBAL_REGISTRY.list_scrapers()


def register_scraper(parser: BaseSourceParser) -> None:
    _GLOBAL_REGISTRY.register(parser)
