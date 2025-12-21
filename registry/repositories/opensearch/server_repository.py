"""OpenSearch-based repository for MCP server storage."""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from opensearchpy import AsyncOpenSearch, NotFoundError

from ...core.config import settings
from ..interfaces import ServerRepositoryBase
from .client import get_opensearch_client, get_index_name

logger = logging.getLogger(__name__)


class OpenSearchServerRepository(ServerRepositoryBase):
    """OpenSearch implementation of server repository."""

    def __init__(self):
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._client: Optional[AsyncOpenSearch] = None
        self._index_name = get_index_name(settings.opensearch_index_servers)

    async def _get_client(self) -> AsyncOpenSearch:
        """Get OpenSearch client."""
        if self._client is None:
            self._client = await get_opensearch_client()
        return self._client

    def _path_to_doc_id(self, path: str) -> str:
        """Convert path to document ID."""
        return path.replace("/", "_").strip("_")

    async def load_all(self) -> None:
        """Load all servers from OpenSearch."""
        logger.info(f"Loading servers from OpenSearch index: {self._index_name}")
        client = await self._get_client()

        try:
            response = await client.search(
                index=self._index_name,
                body={
                    "query": {"match_all": {}},
                    "size": 10000
                }
            )

            self._servers = {}
            for hit in response["hits"]["hits"]:
                server_info = hit["_source"]
                path = server_info["path"]
                self._servers[path] = server_info

            logger.info(f"Loaded {len(self._servers)} servers from OpenSearch")

        except NotFoundError:
            logger.warning(f"Index {self._index_name} not found, starting with empty servers")
            self._servers = {}
        except Exception as e:
            logger.error(f"Error loading servers from OpenSearch: {e}", exc_info=True)
            self._servers = {}

    async def get(self, path: str) -> Optional[Dict[str, Any]]:
        """Get server by path."""
        server_info = self._servers.get(path)
        if server_info:
            return server_info

        if path.endswith('/'):
            alternate_path = path.rstrip('/')
        else:
            alternate_path = path + '/'

        return self._servers.get(alternate_path)

    async def list_all(self) -> Dict[str, Dict[str, Any]]:
        """List all servers."""
        return self._servers.copy()

    async def create(self, server_info: Dict[str, Any]) -> bool:
        """Create a new server."""
        path = server_info["path"]

        if path in self._servers:
            logger.error(f"Server path '{path}' already exists")
            return False

        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        server_info["registered_at"] = datetime.utcnow().isoformat()
        server_info["updated_at"] = datetime.utcnow().isoformat()
        server_info.setdefault("is_enabled", False)

        try:
            await client.index(
                index=self._index_name,
                id=doc_id,
                body=server_info,
                refresh=True
            )

            self._servers[path] = server_info
            logger.info(f"Created server '{server_info['server_name']}' at '{path}'")
            return True

        except Exception as e:
            logger.error(f"Failed to create server in OpenSearch: {e}", exc_info=True)
            return False

    async def update(self, path: str, server_info: Dict[str, Any]) -> bool:
        """Update an existing server."""
        if path not in self._servers:
            logger.error(f"Cannot update server at '{path}': not found")
            return False

        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        server_info["path"] = path
        server_info["updated_at"] = datetime.utcnow().isoformat()

        try:
            await client.index(
                index=self._index_name,
                id=doc_id,
                body=server_info,
                refresh=True
            )

            self._servers[path] = server_info
            logger.info(f"Updated server '{server_info['server_name']}' ({path})")
            return True

        except Exception as e:
            logger.error(f"Failed to update server in OpenSearch: {e}", exc_info=True)
            return False

    async def delete(self, path: str) -> bool:
        """Delete a server."""
        if path not in self._servers:
            logger.error(f"Cannot delete server at '{path}': not found")
            return False

        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        try:
            await client.delete(
                index=self._index_name,
                id=doc_id,
                refresh=True
            )

            server_name = self._servers[path].get('server_name', 'Unknown')
            del self._servers[path]

            logger.info(f"Deleted server '{server_name}' from '{path}'")
            return True

        except Exception as e:
            logger.error(f"Failed to delete server from OpenSearch: {e}", exc_info=True)
            return False

    async def get_state(self, path: str) -> bool:
        """Get server enabled/disabled state."""
        server_info = await self.get(path)
        if server_info:
            return server_info.get("is_enabled", False)
        return False

    async def set_state(self, path: str, enabled: bool) -> bool:
        """Set server enabled/disabled state."""
        if path not in self._servers:
            logger.error(f"Cannot toggle service at '{path}': not found")
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

            self._servers[path]["is_enabled"] = enabled
            server_name = self._servers[path]["server_name"]
            logger.info(f"Toggled '{server_name}' ({path}) to {enabled}")
            return True

        except Exception as e:
            logger.error(f"Failed to update server state in OpenSearch: {e}", exc_info=True)
            return False
