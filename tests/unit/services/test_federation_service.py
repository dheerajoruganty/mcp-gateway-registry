"""
Unit tests for registry.services.federation_service module.

This module tests the federation service for managing federated registry
integrations including Anthropic MCP Registry and ASOR.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from registry.services.federation_service import (
    FederationService,
    get_federation_service,
)
from registry.schemas.federation_schema import FederationConfig


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_federation_config_repo():
    """Create a mock federation config repository."""
    mock = AsyncMock()
    mock.get_config = AsyncMock(return_value=None)
    mock.save_config = AsyncMock()
    return mock


@pytest.fixture
def sample_federation_config():
    """Create a sample federation configuration."""
    return FederationConfig()


# =============================================================================
# TEST: get_federation_service (singleton)
# =============================================================================


@pytest.mark.unit
class TestGetFederationService:
    """Tests for the get_federation_service singleton function."""

    def test_get_federation_service_returns_instance(self):
        """Test that get_federation_service returns a FederationService instance."""
        with patch("registry.services.federation_service._federation_service", None):
            service = get_federation_service()

        assert isinstance(service, FederationService)

    def test_get_federation_service_singleton(self):
        """Test that get_federation_service returns same instance."""
        with patch("registry.services.federation_service._federation_service", None):
            service1 = get_federation_service()
            service2 = get_federation_service()

        assert service1 is service2


# =============================================================================
# TEST: FederationService initialization
# =============================================================================


@pytest.mark.unit
class TestFederationServiceInit:
    """Tests for FederationService initialization."""

    def test_init_creates_service(self):
        """Test that __init__ creates service with default state."""
        service = FederationService()

        assert service._config is None
        assert service._config_loaded is False
        assert service.anthropic_client is None
        assert service.asor_client is None

    def test_config_property_returns_default(self):
        """Test config property returns default when not loaded."""
        service = FederationService()

        config = service.config

        assert isinstance(config, FederationConfig)


# =============================================================================
# TEST: FederationService._ensure_config_loaded
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestFederationServiceEnsureConfigLoaded:
    """Tests for the _ensure_config_loaded method."""

    async def test_ensure_config_loaded_loads_once(self, mock_federation_config_repo):
        """Test that config is loaded only once."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()

            await service._ensure_config_loaded()
            await service._ensure_config_loaded()

        mock_federation_config_repo.get_config.assert_called_once()

    async def test_ensure_config_loaded_sets_flag(self, mock_federation_config_repo):
        """Test that config loaded flag is set."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()

            await service._ensure_config_loaded()

        assert service._config_loaded is True


# =============================================================================
# TEST: FederationService._load_config
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestFederationServiceLoadConfig:
    """Tests for the _load_config method."""

    async def test_load_config_returns_default_on_none(self, mock_federation_config_repo):
        """Test that default config is returned when repo returns None."""
        mock_federation_config_repo.get_config.return_value = None

        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            config = await service._load_config()

        assert isinstance(config, FederationConfig)

    async def test_load_config_returns_repo_config(self, mock_federation_config_repo, sample_federation_config):
        """Test that config from repo is returned."""
        mock_federation_config_repo.get_config.return_value = sample_federation_config

        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            config = await service._load_config()

        assert config is sample_federation_config

    async def test_load_config_handles_exception(self, mock_federation_config_repo):
        """Test that exception returns default config."""
        mock_federation_config_repo.get_config.side_effect = Exception("DB error")

        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            config = await service._load_config()

        assert isinstance(config, FederationConfig)


# =============================================================================
# TEST: FederationService._init_clients
# =============================================================================


@pytest.mark.unit
class TestFederationServiceInitClients:
    """Tests for the _init_clients method."""

    def test_init_clients_no_config(self):
        """Test that _init_clients does nothing without config."""
        service = FederationService()
        service._config = None

        service._init_clients()

        assert service.anthropic_client is None
        assert service.asor_client is None

    def test_init_clients_with_disabled_config(self, sample_federation_config):
        """Test _init_clients with disabled federations."""
        service = FederationService()
        service._config = sample_federation_config
        service._config.anthropic.enabled = False
        service._config.asor.enabled = False

        service._init_clients()

        assert service.anthropic_client is None
        assert service.asor_client is None


# =============================================================================
# TEST: FederationService.sync_all
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestFederationServiceSyncAll:
    """Tests for the sync_all method."""

    async def test_sync_all_empty_when_disabled(self, mock_federation_config_repo):
        """Test sync_all returns empty when federations disabled."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            service._config = FederationConfig()
            service._config_loaded = True

            result = await service.sync_all()

        assert result == {}

    async def test_sync_all_calls_anthropic(self, mock_federation_config_repo):
        """Test sync_all calls _sync_anthropic when enabled."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            config = FederationConfig()
            config.anthropic.enabled = True
            service._config = config
            service._config_loaded = True

            with patch.object(service, "_sync_anthropic", new_callable=AsyncMock) as mock_sync:
                mock_sync.return_value = [{"path": "/server1"}]
                result = await service.sync_all()

        assert "anthropic" in result
        mock_sync.assert_called_once()

    async def test_sync_all_calls_asor(self, mock_federation_config_repo):
        """Test sync_all calls _sync_asor when enabled."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            config = FederationConfig()
            config.asor.enabled = True
            service._config = config
            service._config_loaded = True

            with patch.object(service, "_sync_asor", new_callable=AsyncMock) as mock_sync:
                mock_sync.return_value = [{"name": "agent1"}]
                result = await service.sync_all()

        assert "asor" in result
        mock_sync.assert_called_once()


# =============================================================================
# TEST: FederationService.get_federated_servers
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestFederationServiceGetFederatedServers:
    """Tests for the get_federated_servers method."""

    async def test_get_federated_servers_all_sources(self, mock_federation_config_repo):
        """Test getting servers from all sources."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            service._config = FederationConfig()
            service._config_loaded = True

            with patch.object(service, "_sync_anthropic", new_callable=AsyncMock) as mock_anthropic:
                with patch.object(service, "_sync_asor", new_callable=AsyncMock) as mock_asor:
                    mock_anthropic.return_value = [{"path": "/server1"}]
                    mock_asor.return_value = [{"name": "agent1"}]

                    result = await service.get_federated_servers(source=None)

        assert len(result) == 2

    async def test_get_federated_servers_anthropic_only(self, mock_federation_config_repo):
        """Test getting servers from Anthropic only."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            service._config = FederationConfig()
            service._config_loaded = True

            with patch.object(service, "_sync_anthropic", new_callable=AsyncMock) as mock_anthropic:
                mock_anthropic.return_value = [{"path": "/server1"}]

                result = await service.get_federated_servers(source="anthropic")

        assert len(result) == 1
        mock_anthropic.assert_called_once()


# =============================================================================
# TEST: FederationService.get_federated_items
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestFederationServiceGetFederatedItems:
    """Tests for the get_federated_items method."""

    async def test_get_federated_items_returns_dict(self, mock_federation_config_repo):
        """Test get_federated_items returns servers and agents."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            service._config = FederationConfig()
            service._config_loaded = True

            with patch.object(service, "_sync_anthropic", new_callable=AsyncMock) as mock_anthropic:
                with patch.object(service, "_sync_asor", new_callable=AsyncMock) as mock_asor:
                    mock_anthropic.return_value = [{"path": "/server1"}]
                    mock_asor.return_value = [{"name": "agent1"}]

                    result = await service.get_federated_items(source=None)

        assert "servers" in result
        assert "agents" in result
        assert len(result["servers"]) == 1
        assert len(result["agents"]) == 1


# =============================================================================
# TEST: FederationService._sync_anthropic
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestFederationServiceSyncAnthropic:
    """Tests for the _sync_anthropic method."""

    async def test_sync_anthropic_no_client(self, mock_federation_config_repo):
        """Test _sync_anthropic returns empty when client not initialized."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            service._config = FederationConfig()
            service.anthropic_client = None

            result = await service._sync_anthropic()

        assert result == []

    async def test_sync_anthropic_no_config(self, mock_federation_config_repo):
        """Test _sync_anthropic returns empty when config is None."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            service._config = None
            service.anthropic_client = MagicMock()

            result = await service._sync_anthropic()

        assert result == []


# =============================================================================
# TEST: FederationService._sync_asor
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestFederationServiceSyncAsor:
    """Tests for the _sync_asor method."""

    async def test_sync_asor_no_client(self, mock_federation_config_repo):
        """Test _sync_asor returns empty when client not initialized."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            service._config = FederationConfig()
            service.asor_client = None

            result = await service._sync_asor()

        assert result == []

    async def test_sync_asor_no_config(self, mock_federation_config_repo):
        """Test _sync_asor returns empty when config is None."""
        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            service = FederationService()
            service._config = None
            service.asor_client = MagicMock()

            result = await service._sync_asor()

        assert result == []


# =============================================================================
# TEST: FederationService.get_unified_topology
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestFederationServiceGetUnifiedTopology:
    """Tests for the get_unified_topology method."""

    async def test_get_unified_topology_basic(self, mock_federation_config_repo):
        """Test get_unified_topology returns topology response."""
        # Mock the services at their source modules before they're imported locally
        mock_server_service = MagicMock()
        mock_server_service.registered_servers = {}

        mock_agent_service = MagicMock()
        mock_agent_service.registered_agents = {}

        mock_peer_service = AsyncMock()
        mock_peer_service.list_peers = AsyncMock(return_value=[])

        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            with patch.dict("sys.modules", {
                "registry.services.server_service": MagicMock(server_service=mock_server_service),
                "registry.services.agent_service": MagicMock(agent_service=mock_agent_service),
            }):
                with patch("registry.services.peer_federation_service.get_peer_federation_service", return_value=mock_peer_service):
                    service = FederationService()
                    service._config = FederationConfig()
                    service._config_loaded = True

                    result = await service.get_unified_topology()

        assert result is not None
        assert hasattr(result, "nodes")
        assert hasattr(result, "edges")
        assert hasattr(result, "metadata")

    async def test_get_unified_topology_includes_local_node(self, mock_federation_config_repo):
        """Test that topology includes local registry node."""
        mock_server_service = MagicMock()
        mock_server_service.registered_servers = {"server1": {}}

        mock_agent_service = MagicMock()
        mock_agent_service.registered_agents = {"agent1": {}}

        mock_peer_service = AsyncMock()
        mock_peer_service.list_peers = AsyncMock(return_value=[])

        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            with patch.dict("sys.modules", {
                "registry.services.server_service": MagicMock(server_service=mock_server_service),
                "registry.services.agent_service": MagicMock(agent_service=mock_agent_service),
            }):
                with patch("registry.services.peer_federation_service.get_peer_federation_service", return_value=mock_peer_service):
                    service = FederationService()
                    service._config = FederationConfig()
                    service._config_loaded = True

                    result = await service.get_unified_topology()

        # Find local node
        local_nodes = [n for n in result.nodes if n.id == "this-registry"]
        assert len(local_nodes) == 1
        assert local_nodes[0].servers_count == 1
        assert local_nodes[0].agents_count == 1

    async def test_get_unified_topology_metadata(self, mock_federation_config_repo):
        """Test that topology metadata is calculated correctly."""
        mock_server_service = MagicMock()
        mock_server_service.registered_servers = {}

        mock_agent_service = MagicMock()
        mock_agent_service.registered_agents = {}

        mock_peer_service = AsyncMock()
        mock_peer_service.list_peers = AsyncMock(return_value=[])

        with patch("registry.services.federation_service.get_federation_config_repository", return_value=mock_federation_config_repo):
            with patch.dict("sys.modules", {
                "registry.services.server_service": MagicMock(server_service=mock_server_service),
                "registry.services.agent_service": MagicMock(agent_service=mock_agent_service),
            }):
                with patch("registry.services.peer_federation_service.get_peer_federation_service", return_value=mock_peer_service):
                    service = FederationService()
                    service._config = FederationConfig()
                    service._config_loaded = True

                    result = await service.get_unified_topology()

        assert result.metadata.total_sources >= 1
        assert result.metadata.enabled_sources >= 1
