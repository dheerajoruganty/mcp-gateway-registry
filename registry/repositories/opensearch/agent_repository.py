"""OpenSearch-based repository for A2A agent storage."""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from opensearchpy import AsyncOpenSearch, NotFoundError

from ...core.config import settings
from ...schemas.agent_models import AgentCard
from ..interfaces import AgentRepositoryBase
from .client import get_opensearch_client, get_index_name

logger = logging.getLogger(__name__)


class OpenSearchAgentRepository(AgentRepositoryBase):
    """OpenSearch implementation of agent repository."""

    def __init__(self):
        self._agents: Dict[str, AgentCard] = {}
        self._state: Dict[str, List[str]] = {"enabled": [], "disabled": []}
        self._client: Optional[AsyncOpenSearch] = None
        self._index_name = get_index_name(settings.opensearch_index_agents)

    async def _get_client(self) -> AsyncOpenSearch:
        """Get OpenSearch client."""
        if self._client is None:
            self._client = await get_opensearch_client()
        return self._client

    def _path_to_doc_id(self, path: str) -> str:
        """Convert path to document ID."""
        return path.replace("/", "_").strip("_")

    async def load_all(self) -> None:
        """Load all agents from OpenSearch."""
        logger.info(f"Loading agents from OpenSearch index: {self._index_name}")
        client = await self._get_client()

        try:
            response = await client.search(
                index=self._index_name,
                body={
                    "query": {"match_all": {}},
                    "size": 10000
                }
            )

            self._agents = {}
            self._state = {"enabled": [], "disabled": []}
            
            for hit in response["hits"]["hits"]:
                agent_data = hit["_source"]
                path = agent_data["path"]
                
                try:
                    agent_card = AgentCard(**agent_data)
                    self._agents[path] = agent_card
                    
                    # Build state from is_enabled field
                    if agent_data.get("is_enabled", False):
                        self._state["enabled"].append(path)
                    else:
                        self._state["disabled"].append(path)
                        
                except Exception as e:
                    logger.error(f"Failed to parse agent {path}: {e}")

            logger.info(f"Loaded {len(self._agents)} agents from OpenSearch")

        except NotFoundError:
            logger.warning(f"Index {self._index_name} not found, starting with empty agents")
            self._agents = {}
            self._state = {"enabled": [], "disabled": []}
        except Exception as e:
            logger.error(f"Error loading agents from OpenSearch: {e}", exc_info=True)
            self._agents = {}
            self._state = {"enabled": [], "disabled": []}

    async def get(self, path: str) -> Optional[AgentCard]:
        """Get agent by path."""
        agent = self._agents.get(path)
        if agent:
            return agent

        if path.endswith('/'):
            alternate_path = path.rstrip('/')
        else:
            alternate_path = path + '/'

        return self._agents.get(alternate_path)

    async def list_all(self) -> List[AgentCard]:
        """List all agents."""
        return list(self._agents.values())

    async def create(self, agent: AgentCard) -> AgentCard:
        """Create a new agent."""
        path = agent.path

        if path in self._agents:
            logger.error(f"Agent path '{path}' already exists")
            raise ValueError(f"Agent path '{path}' already exists")

        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        # Set timestamps
        if not agent.registered_at:
            agent.registered_at = datetime.utcnow()
        if not agent.updated_at:
            agent.updated_at = datetime.utcnow()

        agent_dict = agent.model_dump(mode="json")
        agent_dict["is_enabled"] = False

        try:
            await client.index(
                index=self._index_name,
                id=doc_id,
                body=agent_dict,
                refresh=True
            )

            self._agents[path] = agent
            self._state["disabled"].append(path)
            logger.info(f"Created agent '{agent.name}' at '{path}'")
            return agent

        except Exception as e:
            logger.error(f"Failed to create agent in OpenSearch: {e}", exc_info=True)
            raise ValueError(f"Failed to create agent: {e}")

    async def update(self, path: str, updates: Dict[str, Any]) -> AgentCard:
        """Update an existing agent."""
        if path not in self._agents:
            logger.error(f"Cannot update agent at '{path}': not found")
            raise ValueError(f"Agent not found at path: {path}")

        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        # Merge updates with existing agent
        existing_agent = self._agents[path]
        agent_dict = existing_agent.model_dump()
        agent_dict.update(updates)
        agent_dict["path"] = path
        agent_dict["updated_at"] = datetime.utcnow()

        try:
            updated_agent = AgentCard(**agent_dict)
        except Exception as e:
            logger.error(f"Failed to validate updated agent: {e}")
            raise ValueError(f"Invalid agent update: {e}")

        agent_dict = updated_agent.model_dump(mode="json")

        try:
            await client.index(
                index=self._index_name,
                id=doc_id,
                body=agent_dict,
                refresh=True
            )

            self._agents[path] = updated_agent
            logger.info(f"Updated agent '{updated_agent.name}' ({path})")
            return updated_agent

        except Exception as e:
            logger.error(f"Failed to update agent in OpenSearch: {e}", exc_info=True)
            raise ValueError(f"Failed to update agent: {e}")

    async def delete(self, path: str) -> bool:
        """Delete an agent."""
        if path not in self._agents:
            logger.error(f"Cannot delete agent at '{path}': not found")
            return False

        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        try:
            await client.delete(
                index=self._index_name,
                id=doc_id,
                refresh=True
            )

            agent_name = self._agents[path].name
            del self._agents[path]

            # Remove from state
            if path in self._state["enabled"]:
                self._state["enabled"].remove(path)
            if path in self._state["disabled"]:
                self._state["disabled"].remove(path)

            logger.info(f"Deleted agent '{agent_name}' from '{path}'")
            return True

        except Exception as e:
            logger.error(f"Failed to delete agent from OpenSearch: {e}", exc_info=True)
            return False

    async def get_state(self, path: str = None) -> Dict[str, List[str]] | bool:
        """Get agent state - all state if no path, individual state if path provided."""
        if path is None:
            # Return all state (for service initialization)
            return self._state

        # Return individual agent state
        if path in self._state["enabled"]:
            return True

        # Try alternate form
        if path.endswith('/'):
            alternate_path = path.rstrip('/')
        else:
            alternate_path = path + '/'

        return alternate_path in self._state["enabled"]

    async def set_state(self, path: str, enabled: bool) -> bool:
        """Set agent enabled/disabled state."""
        if path not in self._agents:
            logger.error(f"Cannot toggle agent at '{path}': not found")
            return False

        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        try:
            await client.update(
                index=self._index_name,
                id=doc_id,
                body={"doc": {"is_enabled": enabled, "updated_at": datetime.utcnow().isoformat()}},
                refresh=True
            )

            # Update state lists
            if enabled:
                if path in self._state["disabled"]:
                    self._state["disabled"].remove(path)
                if path not in self._state["enabled"]:
                    self._state["enabled"].append(path)
            else:
                if path in self._state["enabled"]:
                    self._state["enabled"].remove(path)
                if path not in self._state["disabled"]:
                    self._state["disabled"].append(path)

            agent_name = self._agents[path].name
            logger.info(f"Toggled '{agent_name}' ({path}) to {enabled}")
            return True

        except Exception as e:
            logger.error(f"Failed to update agent state in OpenSearch: {e}", exc_info=True)
            return False


    async def save_state(self, state: Dict[str, List[str]]) -> None:
        """Save agent state (compatibility method for file repository interface)."""
        # For OpenSearch, state is managed per-agent via set_state()
        # This method updates internal state cache
        self._state = state
        logger.debug(f"Updated agent state cache: {len(state['enabled'])} enabled, {len(state['disabled'])} disabled")
