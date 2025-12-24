"""OpenSearch-based repository for security scan results storage."""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from opensearchpy import AsyncOpenSearch, NotFoundError

from ...core.config import settings
from ..interfaces import SecurityScanRepositoryBase
from .client import get_opensearch_client, get_index_name

logger = logging.getLogger(__name__)


class OpenSearchSecurityScanRepository(SecurityScanRepositoryBase):
    """OpenSearch implementation of security scan repository."""

    def __init__(self):
        self._scans: Dict[str, Dict[str, Any]] = {}
        self._client: Optional[AsyncOpenSearch] = None
        self._index_name = get_index_name(settings.opensearch_index_security_scans)

    async def _get_client(self) -> AsyncOpenSearch:
        """Get OpenSearch client."""
        if self._client is None:
            self._client = await get_opensearch_client()
        return self._client

    def _path_to_doc_id(
        self,
        path: str,
    ) -> str:
        """Convert path to document ID."""
        return path.replace("/", "_").strip("_")

    async def load_all(self) -> None:
        """Load all security scan results from OpenSearch."""
        logger.info(f"Loading security scans from OpenSearch index: {self._index_name}")
        client = await self._get_client()

        try:
            response = await client.search(
                index=self._index_name,
                body={
                    "query": {"match_all": {}},
                    "size": 10000,
                    "sort": [{"scan_timestamp": {"order": "desc"}}]
                }
            )

            self._scans = {}
            for hit in response["hits"]["hits"]:
                scan_data = hit["_source"]
                server_path = scan_data.get("server_path")
                if server_path:
                    if server_path not in self._scans:
                        self._scans[server_path] = scan_data

            logger.info(f"Loaded {len(self._scans)} security scan results from OpenSearch")

        except NotFoundError:
            logger.warning(f"Index {self._index_name} not found, starting with empty scans")
            self._scans = {}
        except Exception as e:
            logger.error(f"Error loading security scans from OpenSearch: {e}", exc_info=True)
            self._scans = {}

    async def get(
        self,
        server_path: str,
    ) -> Optional[Dict[str, Any]]:
        """Get latest security scan result for a server."""
        return self._scans.get(server_path)

    async def list_all(self) -> List[Dict[str, Any]]:
        """List all security scan results."""
        return list(self._scans.values())

    async def create(
        self,
        scan_result: Dict[str, Any],
    ) -> bool:
        """Create/update a security scan result."""
        try:
            # Support both server_path (for servers) and agent_path (for agents)
            path = scan_result.get("server_path") or scan_result.get("agent_path")
            if not path:
                logger.error("Scan result must contain either 'server_path' or 'agent_path' field")
                return False

            client = await self._get_client()
            server_path = path

            # Normalize to server_path for storage consistency
            if "agent_path" in scan_result and "server_path" not in scan_result:
                scan_result["server_path"] = scan_result["agent_path"]

            if "scan_timestamp" not in scan_result:
                scan_result["scan_timestamp"] = datetime.utcnow().isoformat()

            if "vulnerabilities" in scan_result and isinstance(scan_result["vulnerabilities"], list):
                vuln_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
                for vuln in scan_result["vulnerabilities"]:
                    severity = vuln.get("severity", "").lower()
                    if severity in vuln_counts:
                        vuln_counts[severity] += 1

                scan_result["total_vulnerabilities"] = len(scan_result["vulnerabilities"])
                scan_result["critical_count"] = vuln_counts["critical"]
                scan_result["high_count"] = vuln_counts["high"]
                scan_result["medium_count"] = vuln_counts["medium"]
                scan_result["low_count"] = vuln_counts["low"]

            doc_id = self._path_to_doc_id(server_path) + "_" + scan_result["scan_timestamp"].replace(":", "-").replace(".", "-")

            await client.index(
                index=self._index_name,
                id=doc_id,
                body=scan_result,
                refresh=True
            )

            self._scans[server_path] = scan_result

            logger.info(f"Indexed security scan for {server_path} in OpenSearch")
            return True

        except Exception as e:
            logger.error(f"Failed to index security scan in OpenSearch: {e}", exc_info=True)
            return False

    async def get_latest(
        self,
        server_path: str,
    ) -> Optional[Dict[str, Any]]:
        """Get latest scan result for a server."""
        try:
            client = await self._get_client()

            response = await client.search(
                index=self._index_name,
                body={
                    "query": {
                        "term": {"server_path": server_path}
                    },
                    "size": 1,
                    "sort": [{"scan_timestamp": {"order": "desc"}}]
                }
            )

            hits = response["hits"]["hits"]
            if hits:
                return hits[0]["_source"]

            return None

        except Exception as e:
            logger.error(f"Failed to get latest scan from OpenSearch: {e}", exc_info=True)
            return None

    async def query_by_status(
        self,
        status: str,
    ) -> List[Dict[str, Any]]:
        """Query scan results by status."""
        try:
            client = await self._get_client()

            response = await client.search(
                index=self._index_name,
                body={
                    "query": {
                        "term": {"scan_status": status}
                    },
                    "size": 10000,
                    "sort": [{"scan_timestamp": {"order": "desc"}}]
                }
            )

            return [hit["_source"] for hit in response["hits"]["hits"]]

        except Exception as e:
            logger.error(f"Failed to query scans by status from OpenSearch: {e}", exc_info=True)
            return []
