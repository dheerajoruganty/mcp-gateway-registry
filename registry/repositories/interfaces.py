"""
Repository base classes for data access abstraction.

These abstract base classes define the contract that ALL repository implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

from ..schemas.agent_models import AgentCard


class ServerRepositoryBase(ABC):
    """Abstract base class for MCP server data access."""

    @abstractmethod
    async def get(
        self,
        path: str,
    ) -> Optional[Dict[str, Any]]:
        """Get server by path."""
        pass

    @abstractmethod
    async def list_all(self) -> Dict[str, Dict[str, Any]]:
        """List all servers."""
        pass

    @abstractmethod
    async def create(
        self,
        server_info: Dict[str, Any],
    ) -> bool:
        """Create a new server."""
        pass

    @abstractmethod
    async def update(
        self,
        path: str,
        server_info: Dict[str, Any],
    ) -> bool:
        """Update an existing server."""
        pass

    @abstractmethod
    async def delete(
        self,
        path: str,
    ) -> bool:
        """Delete a server."""
        pass

    @abstractmethod
    async def get_state(
        self,
        path: str,
    ) -> bool:
        """Get server enabled/disabled state."""
        pass

    @abstractmethod
    async def set_state(
        self,
        path: str,
        enabled: bool,
    ) -> bool:
        """Set server enabled/disabled state."""
        pass

    @abstractmethod
    async def load_all(self) -> None:
        """Load/reload all servers from storage."""
        pass


class AgentRepositoryBase(ABC):
    """Abstract base class for A2A agent data access."""

    @abstractmethod
    async def get(
        self,
        path: str,
    ) -> Optional[AgentCard]:
        """Get agent by path."""
        pass

    @abstractmethod
    async def list_all(self) -> List[AgentCard]:
        """List all agents."""
        pass

    @abstractmethod
    async def create(
        self,
        agent: AgentCard,
    ) -> AgentCard:
        """Create a new agent."""
        pass

    @abstractmethod
    async def update(
        self,
        path: str,
        updates: Dict[str, Any],
    ) -> AgentCard:
        """Update an existing agent."""
        pass

    @abstractmethod
    async def delete(
        self,
        path: str,
    ) -> bool:
        """Delete an agent."""
        pass

    @abstractmethod
    async def get_state(
        self,
        path: str,
    ) -> bool:
        """Get agent enabled/disabled state."""
        pass

    @abstractmethod
    async def set_state(
        self,
        path: str,
        enabled: bool,
    ) -> bool:
        """Set agent enabled/disabled state."""
        pass

    @abstractmethod
    async def load_all(self) -> None:
        """Load/reload all agents from storage."""
        pass


class SearchRepositoryBase(ABC):
    """Abstract base class for semantic/hybrid search."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the search service."""
        pass

    @abstractmethod
    async def index_server(
        self,
        path: str,
        server_info: Dict[str, Any],
        is_enabled: bool = False,
    ) -> None:
        """Index a server for search."""
        pass

    @abstractmethod
    async def index_agent(
        self,
        path: str,
        agent_card: AgentCard,
        is_enabled: bool = False,
    ) -> None:
        """Index an agent for search."""
        pass

    @abstractmethod
    async def remove_entity(
        self,
        path: str,
    ) -> None:
        """Remove entity from search index."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        max_results: int = 10,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Perform search."""
        pass
