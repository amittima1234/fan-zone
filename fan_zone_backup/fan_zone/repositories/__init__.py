"""Repositories package exposing data access objects."""

from fan_zone.repositories.base import BaseRepository
from fan_zone.repositories.source_repo import SourceRepository, DEFAULT_SOURCES
from fan_zone.repositories.tag_repo import TagRepository, slugify
from fan_zone.repositories.article_repo import ArticleRepository

__all__ = [
    "BaseRepository",
    "SourceRepository",
    "DEFAULT_SOURCES",
    "TagRepository",
    "slugify",
    "ArticleRepository",
]
