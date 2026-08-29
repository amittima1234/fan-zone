"""Base repository class providing session management and common CRUD patterns."""

from typing import Generic, Optional, Type, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """Generic base class for repositories."""

    def __init__(self, session: Optional[AsyncSession] = None):
        self._session = session

    def _get_session(self, session: Optional[AsyncSession] = None) -> AsyncSession:
        """Returns the active session from argument or instance."""
        target = session or self._session
        if target is None:
            raise ValueError("AsyncSession must be provided either in repository constructor or as method argument.")
        return target
