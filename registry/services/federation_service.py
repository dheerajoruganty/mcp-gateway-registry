"""
Federation service for managing federated registry integrations.

Handles:
- Loading federation configuration from repository
- Syncing servers from federated registries
- Registering federated items via server/agent services
- Periodic sync scheduling
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..repositories.factory import get_federation_config_repository
from ..schemas.federation_schema import (
    FederationConfig,
)
from ..schemas.federation_topology_schema import (
    FederationEdge,
    FederationSourceType,
    TopologyMetadata,
    UnifiedFederationNode,
    UnifiedTopologyResponse,
)
from .federation.anthropic_client import AnthropicFederationClient
from .federation.asor_client import AsorFederationClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


class FederationService:
    """Service for managing federated registry integrations."""

    def __init__(self):
        """
        Initialize federation service.

        Loads configuration from repository (DocumentDB or file-based depending on
        storage_backend setting).
        """
        # Config will be loaded asynchronously on first use
        self._config: Optional[FederationConfig] = None
        self._config_loaded: bool = False

        # Initialize clients as None - will be created after config is loaded
        self.anthropic_client: Optional[AnthropicFederationClient] = None
        self.asor_client: Optional[AsorFederationClient] = None

        logger.info("Federation service initialized (config will be loaded on first use)")

    async def _ensure_config_loaded(self) -> None:
        """
        Ensure federation configuration is loaded from repository.

        This method is idempotent and will only load config once.
        """
        if self._config_loaded:
            return

        self._config = await self._load_config()
        self._init_clients()
        self._config_loaded = True

        if self._config.is_any_federation_enabled():
            logger.info(f"Enabled federations: {', '.join(self._config.get_enabled_federations())}")
        else:
            logger.info("No federations enabled")

    def _init_clients(self) -> None:
        """Initialize federation clients based on loaded config."""
        if self._config is None:
            return

        # Initialize Anthropic client if enabled
        if self._config.anthropic.enabled:
            self.anthropic_client = AnthropicFederationClient(
                endpoint=self._config.anthropic.endpoint
            )

        # Initialize ASOR client if enabled
        if self._config.asor.enabled:
            # Extract tenant URL from endpoint or use default
            tenant_url = (
                self._config.asor.endpoint.split("/api")[0]
                if "/api" in self._config.asor.endpoint
                else self._config.asor.endpoint
            )

            self.asor_client = AsorFederationClient(
                endpoint=self._config.asor.endpoint,
                auth_env_var=self._config.asor.auth_env_var,
                tenant_url=tenant_url
            )

    @property
    def config(self) -> FederationConfig:
        """
        Get the federation configuration.

        Note: For async access, call _ensure_config_loaded() first.
        Returns default config if not yet loaded.
        """
        if self._config is None:
            return FederationConfig()
        return self._config

    async def _load_config(self) -> FederationConfig:
        """
        Load federation configuration from repository.

        Returns:
            FederationConfig instance
        """
        try:
            repo = get_federation_config_repository()
            config = await repo.get_config("default")

            if config is None:
                logger.warning("Federation config not found in repository, using defaults")
                return FederationConfig()

            logger.info("Loaded federation config from repository")
            return config

        except Exception as e:
            logger.error(f"Failed to load federation config from repository: {e}")
            return FederationConfig()

    async def sync_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Sync servers from all enabled federated registries.

        Returns:
            Dictionary mapping source name to list of synced servers
        """
        # Ensure config is loaded before syncing
        await self._ensure_config_loaded()

        results = {}

        if self._config and self._config.anthropic.enabled:
            logger.info("Syncing servers from Anthropic MCP Registry...")
            anthropic_servers = await self._sync_anthropic()
            results["anthropic"] = anthropic_servers
            logger.info(f"Synced {len(anthropic_servers)} servers from Anthropic")

        # Sync ASOR agents
        if self._config and self._config.asor.enabled:
            logger.info("Syncing agents from ASOR...")
            asor_agents = await self._sync_asor()
            results["asor"] = asor_agents
            logger.info(f"Synced {len(asor_agents)} agents from ASOR")

        return results

    async def _sync_anthropic(self) -> List[Dict[str, Any]]:
        """
        Sync servers from Anthropic MCP Registry.

        Uses server_service to register servers instead of direct file writes,
        ensuring compatibility with both file and DocumentDB backends.

        Returns:
            List of synced server data
        """
        if not self.anthropic_client:
            logger.error("Anthropic client not initialized")
            return []

        if self._config is None:
            logger.error("Config not loaded")
            return []

        # Fetch servers from Anthropic
        servers = self.anthropic_client.fetch_all_servers(
            self._config.anthropic.servers
        )

        # Import server_service for registration
        from .server_service import server_service

        for server_data in servers:
            try:
                # Extract server name and path
                server_name = server_data.get("server_name", "unknown-server")
                server_path = server_data.get("path", f"/{server_name.replace('/', '-')}")

                # Add federation metadata
                server_data["sync_metadata"] = {
                    "source": "anthropic",
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                    "is_federated": True,
                }

                # Ensure path is set
                if "path" not in server_data:
                    server_data["path"] = server_path

                # Check if server already exists (use async method)
                existing_server = await server_service.get_server_info(server_path)

                if existing_server:
                    # Update existing server
                    success = await server_service.update_server(server_path, server_data)
                    if success:
                        logger.info(f"Updated Anthropic server: {server_name}")
                    else:
                        logger.error(f"Failed to update Anthropic server: {server_name}")
                else:
                    # Register new server
                    success = await server_service.register_server(server_data)
                    if success:
                        # Enable the server after registration
                        await server_service.toggle_service(server_path, True)
                        logger.info(f"Registered Anthropic server: {server_name}")
                    else:
                        logger.error(f"Failed to register Anthropic server: {server_name}")

            except Exception as e:
                logger.error(
                    f"Failed to sync Anthropic server "
                    f"{server_data.get('server_name', 'unknown')}: {e}"
                )

        return servers

    async def _sync_asor(self) -> List[Dict[str, Any]]:
        """
        Sync agents from Workday ASOR.

        Uses agent_service to register agents, ensuring compatibility with
        both file and DocumentDB backends.

        Returns:
            List of synced agent data
        """
        if not self.asor_client:
            logger.error("ASOR client not initialized")
            return []

        if self._config is None:
            logger.error("Config not loaded")
            return []

        # Fetch agents from ASOR
        agents = self.asor_client.fetch_all_agents(
            self._config.asor.agents
        )

        # Register agents with the agent service
        from .agent_service import agent_service
        from ..schemas.agent_models import AgentCard

        for agent_data in agents:
            # Extract agent info from ASOR data structure
            agent_name = agent_data.get("name", "Unknown ASOR Agent")
            agent_path = f"/{agent_name.lower().replace('_', '-')}"
            agent_url = agent_data.get("url", "")
            agent_description = agent_data.get("description", "Agent synced from ASOR")
            if agent_description == "None":
                agent_description = f"ASOR agent: {agent_name}"

            # Extract skills
            skills_data = agent_data.get("skills", [])
            skills = []
            for skill in skills_data:
                skills.append({
                    "name": skill.get("name", ""),
                    "description": skill.get("description", ""),
                    "id": skill.get("id", "")
                })

            # Convert ASOR agent data to AgentCard format
            agent_card = AgentCard(
                protocol_version="1.0",  # Required A2A field
                name=agent_name,
                path=agent_path,
                url=agent_url,
                description=agent_description,
                version=agent_data.get("version", "1.0.0"),
                provider="ASOR",  # Add provider field
                author="ASOR",
                license="Unknown",
                skills=skills,
                tags=["asor", "federated", "workday"],
                visibility="public",
                registered_by="asor-federation",
                registered_at=datetime.now(timezone.utc),
                sync_metadata={
                    "source": "asor",
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                    "is_federated": True,
                }
            )

            try:
                # Check if agent already exists (use async method)
                existing_agent = await agent_service.get_agent_info(agent_path)
                if existing_agent:
                    logger.debug(f"ASOR agent {agent_path} already exists, skipping registration")
                    continue

                # Register the agent using the proper method
                await agent_service.register_agent(agent_card)
                logger.info(f"Registered ASOR agent: {agent_card.name} at {agent_card.path}")

            except Exception as e:
                logger.error(
                    f"Failed to register ASOR agent {agent_data.get('name', 'unknown')}: {e}"
                )

        return agents

    async def get_federated_servers(
        self,
        source: Optional[str] = None,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get federated servers by syncing from sources.

        Args:
            source: Filter by source (anthropic, asor, etc.) or None for all
            force_refresh: Ignored (always syncs fresh)

        Returns:
            List of federated server data
        """
        # Ensure config is loaded
        await self._ensure_config_loaded()

        servers = []

        if source is None or source == "anthropic":
            servers.extend(await self._sync_anthropic())

        if source is None or source == "asor":
            servers.extend(await self._sync_asor())

        return servers

    async def get_federated_items(
        self,
        source: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get both federated servers and agents from specified source or all sources.

        Args:
            source: Federation source name (e.g., "anthropic", "asor") or None for all
            force_refresh: Ignored (always syncs fresh)

        Returns:
            Dict with 'servers' and 'agents' keys containing respective federated items
        """
        # Ensure config is loaded
        await self._ensure_config_loaded()

        result = {"servers": [], "agents": []}

        if source is None or source == "anthropic":
            result["servers"].extend(await self._sync_anthropic())

        if source is None or source == "asor":
            # ASOR provides agents, not servers
            asor_agents = await self._sync_asor()
            result["agents"].extend(asor_agents)

        return result

    async def get_unified_topology(self) -> UnifiedTopologyResponse:
        """
        Get unified federation topology including all sources.

        Builds a unified view of:
        - Local registry (center node)
        - Peer registries
        - Anthropic MCP source
        - ASOR agents source

        Returns:
            UnifiedTopologyResponse with nodes, edges, and metadata
        """
        # Ensure config is loaded
        await self._ensure_config_loaded()

        # Layout constants for node positioning
        center_x, center_y = 400, 300
        radius = 200

        nodes: List[UnifiedFederationNode] = []
        edges: List[FederationEdge] = []

        # Count servers and agents in local registry
        from .server_service import server_service
        from .agent_service import agent_service

        local_servers = len(server_service.registered_servers)
        local_agents = len(agent_service.registered_agents)

        # Add local registry node (always at center)
        local_node = UnifiedFederationNode(
            id="this-registry",
            type=FederationSourceType.LOCAL,
            name="This Registry",
            status="healthy",
            enabled=True,
            servers_count=local_servers,
            agents_count=local_agents,
            position={"x": center_x, "y": center_y},
        )
        nodes.append(local_node)

        # Get peer registries from peer_federation_service
        from .peer_federation_service import get_peer_federation_service

        peer_service = get_peer_federation_service()
        peers = await peer_service.list_peers()

        # Calculate positions for all external sources
        # External sources: Anthropic, ASOR, plus all peers
        external_sources = []

        # Add Anthropic node if configured
        if self._config and self._config.anthropic:
            external_sources.append(("anthropic", self._config.anthropic))

        # Add ASOR node if configured
        if self._config and self._config.asor:
            external_sources.append(("asor", self._config.asor))

        # Add peer sources
        for peer in peers:
            external_sources.append(("peer", peer))

        # Calculate positions in a circular layout
        total_external = len(external_sources)

        for i, (source_type, source_config) in enumerate(external_sources):
            # Calculate position on circle
            if total_external > 0:
                angle = (2 * math.pi * i) / total_external - (math.pi / 2)
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
            else:
                x, y = center_x + radius, center_y

            if source_type == "anthropic":
                # Anthropic MCP node
                anthropic_config = source_config
                anthropic_status = "healthy" if anthropic_config.enabled else "disabled"
                servers_count = len(anthropic_config.servers)

                anthropic_node = UnifiedFederationNode(
                    id="anthropic",
                    type=FederationSourceType.ANTHROPIC,
                    name="Anthropic MCP",
                    status=anthropic_status,
                    enabled=anthropic_config.enabled,
                    endpoint=anthropic_config.endpoint,
                    servers_count=servers_count,
                    agents_count=0,
                    sync_on_startup=anthropic_config.sync_on_startup,
                    position={"x": x, "y": y},
                )
                nodes.append(anthropic_node)

                # Add edge if enabled
                if anthropic_config.enabled:
                    edges.append(FederationEdge(
                        id="edge-anthropic",
                        source="anthropic",
                        target="this-registry",
                        status="healthy",
                        animated=True,
                        servers_synced=servers_count,
                        agents_synced=0,
                    ))

            elif source_type == "asor":
                # ASOR agents node
                asor_config = source_config
                asor_status = "healthy" if asor_config.enabled else "disabled"
                agents_count = len(asor_config.agents)

                asor_node = UnifiedFederationNode(
                    id="asor",
                    type=FederationSourceType.ASOR,
                    name="ASOR Agents",
                    status=asor_status,
                    enabled=asor_config.enabled,
                    endpoint=asor_config.endpoint if asor_config.endpoint else None,
                    servers_count=0,
                    agents_count=agents_count,
                    sync_on_startup=asor_config.sync_on_startup,
                    position={"x": x, "y": y},
                )
                nodes.append(asor_node)

                # Add edge if enabled
                if asor_config.enabled:
                    edges.append(FederationEdge(
                        id="edge-asor",
                        source="asor",
                        target="this-registry",
                        status="healthy",
                        animated=True,
                        servers_synced=0,
                        agents_synced=agents_count,
                    ))

            elif source_type == "peer":
                # Peer registry node
                peer_config = source_config
                peer_id = peer_config.peer_id

                # Get sync status for this peer
                sync_status = await peer_service.get_sync_status(peer_id)

                # Determine status
                if not peer_config.enabled:
                    peer_status = "disabled"
                elif sync_status and sync_status.is_healthy:
                    peer_status = "healthy"
                elif sync_status and not sync_status.is_healthy:
                    peer_status = "error"
                else:
                    peer_status = "unknown"

                # Get sync counts
                servers_synced = sync_status.total_servers_synced if sync_status else 0
                agents_synced = sync_status.total_agents_synced if sync_status else 0
                last_sync = sync_status.last_successful_sync if sync_status else None

                peer_node = UnifiedFederationNode(
                    id=peer_id,
                    type=FederationSourceType.PEER,
                    name=peer_config.name,
                    status=peer_status,
                    enabled=peer_config.enabled,
                    endpoint=peer_config.endpoint,
                    servers_count=servers_synced,
                    agents_count=agents_synced,
                    last_sync=last_sync,
                    sync_mode=peer_config.sync_mode,
                    sync_interval_minutes=peer_config.sync_interval_minutes,
                    position={"x": x, "y": y},
                )
                nodes.append(peer_node)

                # Add edge if enabled
                if peer_config.enabled:
                    edges.append(FederationEdge(
                        id=f"edge-{peer_id}",
                        source=peer_id,
                        target="this-registry",
                        status=peer_status,
                        animated=(peer_status == "healthy"),
                        servers_synced=servers_synced,
                        agents_synced=agents_synced,
                    ))

        # Calculate metadata
        total_sources = len(nodes)
        enabled_sources = sum(1 for n in nodes if n.enabled)
        total_servers = sum(n.servers_count for n in nodes)
        total_agents = sum(n.agents_count for n in nodes)

        metadata = TopologyMetadata(
            total_sources=total_sources,
            enabled_sources=enabled_sources,
            total_servers=total_servers,
            total_agents=total_agents,
            last_updated=datetime.now(timezone.utc),
        )

        logger.info(
            f"Built unified topology: {len(nodes)} nodes, {len(edges)} edges, "
            f"{total_servers} servers, {total_agents} agents"
        )

        return UnifiedTopologyResponse(
            nodes=nodes,
            edges=edges,
            metadata=metadata,
        )


# Global instance
_federation_service: Optional[FederationService] = None


def get_federation_service() -> FederationService:
    """
    Get global federation service instance (singleton).

    Returns:
        FederationService instance
    """
    global _federation_service

    if _federation_service is None:
        _federation_service = FederationService()

    return _federation_service
