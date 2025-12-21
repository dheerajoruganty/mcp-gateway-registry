"""File-based search repository using FAISS."""

import logging
from typing import Any, Dict, List

from ...core.config import settings
from ..interfaces import SearchRepositoryBase

logger = logging.getLogger(__name__)


class FaissSearchRepository(SearchRepositoryBase):
    """FAISS-based search repository."""

    def __init__(self):
        # Import FaissService lazily to avoid circular imports
        from ...search.service import faiss_service
        self.faiss_service = faiss_service

    async def index_entity(
        self,
        entity_path: str,
        entity_data: Dict[str, Any],
        entity_type: str,
        is_enabled: bool
    ) -> None:
        """Add or update entity in FAISS index."""
        await self.faiss_service.add_or_update_entity(
            entity_path=entity_path,
            entity_info=entity_data,
            entity_type=entity_type,
            is_enabled=is_enabled
        )

    async def remove_entity(self, entity_path: str) -> None:
        """Remove entity from FAISS index."""
        await self.faiss_service.remove_entity(entity_path)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        entity_type: str = None,
        enabled_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Search entities using FAISS."""
        return await self.faiss_service.search(
            query=query,
            top_k=top_k,
            entity_type=entity_type,
            enabled_only=enabled_only
        )

    async def rebuild_index(self) -> None:
        """Rebuild FAISS index from scratch."""
        await self.faiss_service.rebuild_index()

    async def initialize(self) -> None:
        """Initialize the search repository."""
        # FAISS service initializes itself
        pass

    async def index_server(self, server_path: str, server_data: Dict[str, Any], is_enabled: bool) -> None:
        """Index a server."""
        await self.index_entity(server_path, server_data, "server", is_enabled)

    async def index_agent(self, agent_path: str, agent_data: Dict[str, Any], is_enabled: bool) -> None:
        """Index an agent."""
        await self.index_entity(agent_path, agent_data, "agent", is_enabled)
