"""
Unit tests for Peer Federation Service Sync Methods.

Tests for sync_peer, sync_all_peers, and storage methods
(_store_synced_servers and _store_synced_agents).
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock, AsyncMock
from typing import Dict, Any, List

from registry.services.peer_federation_service import (
    PeerFederationService,
    get_peer_federation_service,
)
from registry.repositories.file.peer_federation_repository import (
    FilePeerFederationRepository,
)
from registry.schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
    SyncResult,
    SyncHistoryEntry,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    PeerFederationService._instance = None
    yield
    PeerFederationService._instance = None


@pytest.fixture
def temp_peers_dir(tmp_path):
    """Create temp directory for peer configs."""
    peers_dir = tmp_path / "peers"
    peers_dir.mkdir()
    return peers_dir


@pytest.fixture
def mock_file_repo(temp_peers_dir, tmp_path):
    """Create a file-based repository with temp directories."""
    sync_state_file = tmp_path / "peer_sync_state.json"
    return FilePeerFederationRepository(
        peers_dir=temp_peers_dir,
        sync_state_file=sync_state_file
    )


@pytest.fixture
def mock_repo_factory(mock_file_repo):
    """Mock the get_peer_federation_repository factory to return file-based repo."""
    with patch(
        "registry.services.peer_federation_service.get_peer_federation_repository",
        return_value=mock_file_repo
    ):
        yield mock_file_repo


@pytest.fixture
def mock_server_service():
    """Mock server_service for storage tests."""
    with patch("registry.services.peer_federation_service.server_service") as mock:
        mock.registered_servers = {}
        mock.register_server.return_value = True
        mock.update_server.return_value = True
        yield mock


@pytest.fixture
def mock_agent_service():
    """Mock agent_service for storage tests."""
    with patch("registry.services.peer_federation_service.agent_service") as mock:
        mock.registered_agents = {}
        mock.register_agent.return_value = MagicMock()
        mock.update_agent.return_value = MagicMock()
        yield mock


@pytest.fixture
def sample_peer_config():
    """Sample peer config for testing."""
    return PeerRegistryConfig(
        peer_id="test-peer",
        name="Test Peer Registry",
        endpoint="https://peer.example.com",
        enabled=True,
    )


@pytest.fixture
def sample_peer_config_disabled():
    """Sample disabled peer config for testing."""
    return PeerRegistryConfig(
        peer_id="disabled-peer",
        name="Disabled Peer Registry",
        endpoint="https://disabled.example.com",
        enabled=False,
    )


@pytest.fixture
def sample_server_data():
    """Sample server data returned from peer."""
    return {
        "path": "/test-server",
        "name": "Test Server",
        "description": "A test server",
        "url": "http://test.example.com:8000",
    }


@pytest.fixture
def sample_agent_data():
    """Sample agent data returned from peer."""
    return {
        "path": "/test-agent",
        "name": "Test Agent",
        "version": "1.0.0",
        "description": "A test agent",
        "url": "https://test.example.com/agent",
    }


@pytest.mark.unit
class TestSyncPeer:
    """Tests for sync_peer method."""

    @pytest.mark.asyncio
    async def test_sync_peer_successful_with_servers_and_agents(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test successful sync with servers and agents."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = [
                {"path": "/server1", "name": "Server 1"},
                {"path": "/server2", "name": "Server 2"},
            ]
            mock_client.fetch_agents.return_value = [
                {
                    "path": "/agent1",
                    "name": "Agent 1",
                    "version": "1.0.0",
                    "description": "Agent 1 description",
                    "url": "https://example.com/agent1",
                },
            ]
            mock_client_class.return_value = mock_client

            result = await service.sync_peer(sample_peer_config.peer_id)

            # Verify result
            assert result.success is True
            assert result.peer_id == sample_peer_config.peer_id
            assert result.servers_synced == 2
            assert result.agents_synced == 1
            assert result.error_message is None
            assert result.duration_seconds > 0
            assert result.new_generation == 1

            # Verify sync status updated
            sync_status = await service.get_sync_status(sample_peer_config.peer_id)
            assert sync_status.sync_in_progress is False
            assert sync_status.last_successful_sync is not None
            assert sync_status.current_generation == 1
            assert sync_status.total_servers_synced == 2
            assert sync_status.total_agents_synced == 1
            assert sync_status.consecutive_failures == 0
            assert sync_status.is_healthy is True

            # Verify history entry created
            assert len(sync_status.sync_history) == 1
            history = sync_status.sync_history[0]
            assert history.success is True
            assert history.servers_synced == 2
            assert history.agents_synced == 1

    @pytest.mark.asyncio
    async def test_sync_peer_disabled_peer_raises_error(
        self, mock_repo_factory, sample_peer_config_disabled
    ):
        """Test sync disabled peer raises ValueError."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config_disabled)

        with pytest.raises(ValueError, match="is disabled"):
            await service.sync_peer(sample_peer_config_disabled.peer_id)

    @pytest.mark.asyncio
    async def test_sync_peer_nonexistent_peer_raises_error(self, mock_repo_factory):
        """Test sync non-existent peer raises ValueError."""
        service = PeerFederationService()

        with pytest.raises(ValueError, match="Peer not found"):
            await service.sync_peer("nonexistent-peer")

    @pytest.mark.asyncio
    async def test_sync_peer_network_error_handling(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test network error handling during sync."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Mock PeerRegistryClient to raise exception
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.side_effect = Exception("Network error")
            mock_client_class.return_value = mock_client

            result = await service.sync_peer(sample_peer_config.peer_id)

            # Verify result
            assert result.success is False
            assert result.peer_id == sample_peer_config.peer_id
            assert result.servers_synced == 0
            assert result.agents_synced == 0
            assert "Network error" in result.error_message
            assert result.duration_seconds > 0

            # Verify sync status updated with failure
            sync_status = await service.get_sync_status(sample_peer_config.peer_id)
            assert sync_status.sync_in_progress is False
            assert sync_status.consecutive_failures == 1
            assert sync_status.is_healthy is False

            # Verify history entry created for failure
            assert len(sync_status.sync_history) == 1
            history = sync_status.sync_history[0]
            assert history.success is False
            assert "Network error" in history.error_message

    @pytest.mark.asyncio
    async def test_sync_peer_uses_since_generation_for_incremental_sync(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test incremental sync uses since_generation."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Set existing sync status with generation 5
        sync_status = await service.get_sync_status(sample_peer_config.peer_id)
        sync_status.current_generation = 5
        await service.update_sync_status(sample_peer_config.peer_id, sync_status)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = [
                {"path": "/server1", "name": "Server 1"}
            ]
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            result = await service.sync_peer(sample_peer_config.peer_id)

            # Verify fetch_servers was called with since_generation=5
            mock_client.fetch_servers.assert_called_once_with(since_generation=5)
            mock_client.fetch_agents.assert_called_once_with(since_generation=5)

            # Verify generation incremented
            assert result.new_generation == 6

    @pytest.mark.asyncio
    async def test_sync_peer_generation_only_increments_when_items_synced(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test generation only increments when items are synced."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Set existing sync status with generation 5
        sync_status = await service.get_sync_status(sample_peer_config.peer_id)
        sync_status.current_generation = 5
        await service.update_sync_status(sample_peer_config.peer_id, sync_status)

        # Mock PeerRegistryClient - return empty lists
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = []
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            result = await service.sync_peer(sample_peer_config.peer_id)

            # Verify generation DID NOT increment (no items synced)
            assert result.new_generation == 5

    @pytest.mark.asyncio
    async def test_sync_peer_generation_increments_on_first_sync(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test generation increments on first sync even with no items."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Mock PeerRegistryClient - return empty lists
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = []
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            result = await service.sync_peer(sample_peer_config.peer_id)

            # Verify generation incremented (since_generation was 0)
            assert result.new_generation == 1

    @pytest.mark.asyncio
    async def test_sync_peer_status_updated_correctly(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test sync status updated correctly during sync."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = [
                {"path": "/server1", "name": "Server 1"}
            ]
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            # Get initial status
            initial_status = await service.get_sync_status(sample_peer_config.peer_id)
            assert initial_status.sync_in_progress is False

            result = await service.sync_peer(sample_peer_config.peer_id)

            # Get final status
            final_status = await service.get_sync_status(sample_peer_config.peer_id)
            assert final_status.sync_in_progress is False
            assert final_status.last_sync_attempt is not None
            assert final_status.last_successful_sync is not None
            assert final_status.last_health_check is not None

    @pytest.mark.asyncio
    async def test_sync_peer_handles_none_responses_from_client(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test sync handles None responses from client."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Mock PeerRegistryClient to return None
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = None
            mock_client.fetch_agents.return_value = None
            mock_client_class.return_value = mock_client

            result = await service.sync_peer(sample_peer_config.peer_id)

            # Should handle None gracefully and treat as empty list
            assert result.success is True
            assert result.servers_synced == 0
            assert result.agents_synced == 0


@pytest.mark.unit
class TestSyncAllPeers:
    """Tests for sync_all_peers method."""

    @pytest.mark.asyncio
    async def test_sync_all_enabled_peers(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test sync all enabled peers."""
        service = PeerFederationService()

        # Add multiple peers
        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        peer2 = PeerRegistryConfig(
            peer_id="peer2",
            name="Peer 2",
            endpoint="https://peer2.example.com",
            enabled=True,
        )
        peer3 = PeerRegistryConfig(
            peer_id="peer3",
            name="Peer 3",
            endpoint="https://peer3.example.com",
            enabled=False,
        )

        await service.add_peer(peer1)
        await service.add_peer(peer2)
        await service.add_peer(peer3)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = [
                {"path": "/server1", "name": "Server 1"}
            ]
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            results = await service.sync_all_peers(enabled_only=True)

            # Should only sync enabled peers
            assert len(results) == 2
            assert "peer1" in results
            assert "peer2" in results
            assert "peer3" not in results

            # Verify both succeeded
            assert results["peer1"].success is True
            assert results["peer2"].success is True

    @pytest.mark.asyncio
    async def test_sync_all_peers_skip_disabled_when_enabled_only_true(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test skip disabled peers when enabled_only=True."""
        service = PeerFederationService()

        # Add enabled and disabled peers
        enabled_peer = PeerRegistryConfig(
            peer_id="enabled-peer",
            name="Enabled Peer",
            endpoint="https://enabled.example.com",
            enabled=True,
        )
        disabled_peer = PeerRegistryConfig(
            peer_id="disabled-peer",
            name="Disabled Peer",
            endpoint="https://disabled.example.com",
            enabled=False,
        )

        await service.add_peer(enabled_peer)
        await service.add_peer(disabled_peer)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = []
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            results = await service.sync_all_peers(enabled_only=True)

            # Should only sync enabled peer
            assert len(results) == 1
            assert "enabled-peer" in results
            assert "disabled-peer" not in results

    @pytest.mark.asyncio
    async def test_sync_all_peers_continue_on_individual_failure(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test continue on individual peer failure."""
        service = PeerFederationService()

        # Add multiple peers
        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        peer2 = PeerRegistryConfig(
            peer_id="peer2",
            name="Peer 2",
            endpoint="https://peer2.example.com",
            enabled=True,
        )

        await service.add_peer(peer1)
        await service.add_peer(peer2)

        # Mock PeerRegistryClient to fail for peer1 but succeed for peer2
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            # Create side effect that fails for peer1, succeeds for peer2
            def client_factory(peer_config, **kwargs):
                mock_client = MagicMock()
                if peer_config.peer_id == "peer1":
                    mock_client.fetch_servers.side_effect = Exception("Network error")
                else:
                    mock_client.fetch_servers.return_value = [
                        {"path": "/server1", "name": "Server 1"}
                    ]
                    mock_client.fetch_agents.return_value = []
                return mock_client

            mock_client_class.side_effect = client_factory

            results = await service.sync_all_peers(enabled_only=True)

            # Both should be in results
            assert len(results) == 2
            assert "peer1" in results
            assert "peer2" in results

            # peer1 should have failed
            assert results["peer1"].success is False
            assert "Network error" in results["peer1"].error_message

            # peer2 should have succeeded
            assert results["peer2"].success is True
            assert results["peer2"].servers_synced == 1

    @pytest.mark.asyncio
    async def test_sync_all_peers_returns_correct_result_dictionary(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test returns correct result dictionary."""
        service = PeerFederationService()

        # Add peers
        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        peer2 = PeerRegistryConfig(
            peer_id="peer2",
            name="Peer 2",
            endpoint="https://peer2.example.com",
            enabled=True,
        )

        await service.add_peer(peer1)
        await service.add_peer(peer2)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = [
                {"path": "/server1", "name": "Server 1"}
            ]
            mock_client.fetch_agents.return_value = [
                {
                    "path": "/agent1",
                    "name": "Agent 1",
                    "version": "1.0.0",
                    "description": "Agent 1 description",
                    "url": "https://example.com/agent1",
                }
            ]
            mock_client_class.return_value = mock_client

            results = await service.sync_all_peers(enabled_only=True)

            # Verify result structure
            assert isinstance(results, dict)
            assert len(results) == 2

            for peer_id, result in results.items():
                assert isinstance(result, SyncResult)
                assert result.peer_id == peer_id
                assert result.success is True
                assert result.servers_synced == 1
                assert result.agents_synced == 1

    @pytest.mark.asyncio
    async def test_sync_all_peers_with_enabled_only_false(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test sync all peers including disabled when enabled_only=False."""
        service = PeerFederationService()

        # Add enabled and disabled peers
        enabled_peer = PeerRegistryConfig(
            peer_id="enabled-peer",
            name="Enabled Peer",
            endpoint="https://enabled.example.com",
            enabled=True,
        )
        disabled_peer = PeerRegistryConfig(
            peer_id="disabled-peer",
            name="Disabled Peer",
            endpoint="https://disabled.example.com",
            enabled=False,
        )

        await service.add_peer(enabled_peer)
        await service.add_peer(disabled_peer)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = []
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            results = await service.sync_all_peers(enabled_only=False)

            # Should attempt to sync both, but disabled will fail
            assert len(results) == 2
            assert "enabled-peer" in results
            assert "disabled-peer" in results

            # Enabled peer should succeed
            assert results["enabled-peer"].success is True

            # Disabled peer should fail (raises ValueError)
            assert results["disabled-peer"].success is False


@pytest.mark.unit
class TestStoreSyncedServers:
    """Tests for _store_synced_servers method."""

    @pytest.mark.asyncio
    async def test_store_new_server_with_sync_metadata(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test store new server with sync_metadata."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        servers = [{"path": "/test-server", "name": "Test Server"}]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        assert count == 1

        # Verify register_server was called with correct data
        mock_server_service.register_server.assert_called_once()
        call_args = mock_server_service.register_server.call_args[0][0]

        # Verify path prefixed
        assert call_args["path"] == "/test-peer/test-server"

        # Verify sync_metadata added
        assert "sync_metadata" in call_args
        metadata = call_args["sync_metadata"]
        assert metadata["source_peer_id"] == sample_peer_config.peer_id
        assert metadata["is_federated"] is True
        assert metadata["original_path"] == "/test-server"
        assert "synced_at" in metadata

    @pytest.mark.asyncio
    async def test_store_update_existing_server(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test update existing server."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Simulate existing server
        mock_server_service.registered_servers["/test-peer/test-server"] = {
            "path": "/test-peer/test-server",
            "name": "Old Name",
        }

        servers = [{"path": "/test-server", "name": "New Name"}]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        assert count == 1

        # Verify update_server was called
        mock_server_service.update_server.assert_called_once()
        path_arg = mock_server_service.update_server.call_args[0][0]
        data_arg = mock_server_service.update_server.call_args[0][1]

        assert path_arg == "/test-peer/test-server"
        assert data_arg["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_store_path_normalization_no_leading_slash(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test path normalization when path missing leading slash."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Path without leading slash
        servers = [{"path": "test-server", "name": "Test Server"}]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        assert count == 1

        # Verify path normalized and prefixed
        call_args = mock_server_service.register_server.call_args[0][0]
        assert call_args["path"] == "/test-peer/test-server"

    @pytest.mark.asyncio
    async def test_store_path_prefixing_with_peer_id(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test path prefixing with peer_id."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        servers = [{"path": "/my-server", "name": "My Server"}]

        service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Verify path prefixed correctly
        call_args = mock_server_service.register_server.call_args[0][0]
        assert call_args["path"] == "/test-peer/my-server"

        # Verify original path preserved in metadata
        metadata = call_args["sync_metadata"]
        assert metadata["original_path"] == "/my-server"

    @pytest.mark.asyncio
    async def test_store_skip_servers_missing_path_field(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test skip servers missing path field."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        servers = [
            {"name": "No Path Server"},  # Missing path
            {"path": "/valid-server", "name": "Valid Server"},
        ]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Should only store the valid server
        assert count == 1
        mock_server_service.register_server.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_handle_storage_failures(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test handle storage failures gracefully."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Make register_server fail
        mock_server_service.register_server.return_value = False

        servers = [{"path": "/test-server", "name": "Test Server"}]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Should return 0 for failed storage
        assert count == 0

    @pytest.mark.asyncio
    async def test_store_handle_exceptions_during_storage(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test handle exceptions during storage."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Make register_server raise exception
        mock_server_service.register_server.side_effect = Exception("Storage error")

        servers = [{"path": "/test-server", "name": "Test Server"}]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Should handle exception and return 0
        assert count == 0


@pytest.mark.unit
class TestStoreSyncedAgents:
    """Tests for _store_synced_agents method."""

    @pytest.mark.asyncio
    async def test_store_new_agent_with_sync_metadata(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test store new agent with sync_metadata."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        agents = [
            {
                "path": "/test-agent",
                "name": "Test Agent",
                "version": "1.0.0",
                "description": "Test agent description",
                "url": "https://test.example.com/agent",
            }
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        assert count == 1

        # Verify register_agent was called
        mock_agent_service.register_agent.assert_called_once()
        call_args = mock_agent_service.register_agent.call_args[0][0]

        # Verify path prefixed
        assert call_args.path == "/test-peer/test-agent"

        # Verify sync_metadata added
        assert hasattr(call_args, "sync_metadata")
        metadata = call_args.sync_metadata
        assert metadata["source_peer_id"] == sample_peer_config.peer_id
        assert metadata["is_federated"] is True
        assert metadata["original_path"] == "/test-agent"

    @pytest.mark.asyncio
    async def test_store_update_existing_agent(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test update existing agent."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Simulate existing agent with model_dump method
        existing_agent = MagicMock(
            path="/test-peer/test-agent",
            model_dump=lambda: {
                "path": "/test-peer/test-agent",
                "name": "Old Agent",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "local_overrides": False,  # Not locally overridden
                },
            },
        )
        mock_agent_service.registered_agents["/test-peer/test-agent"] = existing_agent
        mock_agent_service.update_agent.return_value = MagicMock()

        agents = [
            {
                "path": "/test-agent",
                "name": "Updated Agent",
                "version": "2.0.0",
                "description": "Updated description",
                "url": "https://test.example.com/agent",
            }
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        assert count == 1

        # Verify update_agent was called
        mock_agent_service.update_agent.assert_called_once()
        path_arg = mock_agent_service.update_agent.call_args[0][0]
        data_arg = mock_agent_service.update_agent.call_args[0][1]

        assert path_arg == "/test-peer/test-agent"
        assert data_arg["name"] == "Updated Agent"
        assert data_arg["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_store_path_normalization(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test path normalization for agents."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Path without leading slash
        agents = [
            {
                "path": "test-agent",
                "name": "Test Agent",
                "version": "1.0.0",
                "description": "Test description",
                "url": "https://test.example.com/agent",
            }
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        assert count == 1

        # Verify path normalized and prefixed
        call_args = mock_agent_service.register_agent.call_args[0][0]
        assert call_args.path == "/test-peer/test-agent"

    @pytest.mark.asyncio
    async def test_store_handle_validation_errors(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test handle validation errors gracefully."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Make register_agent raise ValueError (validation error)
        mock_agent_service.register_agent.side_effect = ValueError(
            "Invalid agent data"
        )

        agents = [
            {
                "path": "/test-agent",
                "name": "Test Agent",
                "version": "1.0.0",
                "description": "Test description",
                "url": "https://test.example.com/agent",
            }
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        # Should handle validation error and return 0
        assert count == 0

    @pytest.mark.asyncio
    async def test_store_handle_storage_failures(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test handle storage failures gracefully."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Make register_agent return None (failure)
        mock_agent_service.register_agent.return_value = None

        agents = [
            {
                "path": "/test-agent",
                "name": "Test Agent",
                "version": "1.0.0",
                "description": "Test description",
                "url": "https://test.example.com/agent",
            }
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        # Should return 0 for failed storage
        assert count == 0

    @pytest.mark.asyncio
    async def test_store_skip_agents_missing_path_field(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test skip agents missing path field."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        agents = [
            {"name": "No Path Agent", "version": "1.0.0"},  # Missing path
            {
                "path": "/valid-agent",
                "name": "Valid Agent",
                "version": "1.0.0",
                "description": "Valid description",
                "url": "https://valid.example.com/agent",
            },
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        # Should only store the valid agent
        assert count == 1
        mock_agent_service.register_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_handle_exceptions_during_storage(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test handle exceptions during storage."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Make register_agent raise exception
        mock_agent_service.register_agent.side_effect = Exception("Storage error")

        agents = [
            {
                "path": "/test-agent",
                "name": "Test Agent",
                "version": "1.0.0",
                "description": "Test description",
                "url": "https://test.example.com/agent",
            }
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        # Should handle exception and return 0
        assert count == 0

    @pytest.mark.asyncio
    async def test_store_update_agent_returns_none_on_failure(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test update agent when it returns None (failure)."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Simulate existing agent
        existing_agent = MagicMock()
        existing_agent.path = "/test-peer/test-agent"
        mock_agent_service.registered_agents["/test-peer/test-agent"] = existing_agent

        # Make update_agent return None (failure)
        mock_agent_service.update_agent.return_value = None

        agents = [
            {
                "path": "/test-agent",
                "name": "Updated Agent",
                "version": "2.0.0",
                "description": "Updated description",
                "url": "https://test.example.com/agent",
            }
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        # Should return 0 for failed update
        assert count == 0


@pytest.fixture
def sample_servers():
    """Sample servers for filtering tests."""
    return [
        {"path": "/server-a", "tags": ["production", "api"]},
        {"path": "/server-b", "tags": ["staging"]},
        {"path": "/server-c", "categories": ["internal"]},
        {"path": "/server-d", "tags": ["production", "database"]},
        {"path": "/server-e"},  # No tags or categories
    ]


@pytest.fixture
def sample_agents():
    """Sample agents for filtering tests."""
    return [
        {"path": "/agent-a", "tags": ["ai", "production"]},
        {"path": "/agent-b", "tags": ["utility"]},
        {"path": "/agent-c", "categories": ["automation"]},
        {"path": "/agent-d"},  # No tags or categories
    ]


@pytest.fixture
def whitelist_peer_config():
    """Peer config with whitelist sync mode."""
    return PeerRegistryConfig(
        peer_id="test-peer",
        name="Test Peer",
        endpoint="https://peer.example.com",
        enabled=True,
        sync_mode="whitelist",
        whitelist_servers=["/server-a", "/server-c"],
        whitelist_agents=["/agent-a"],
    )


@pytest.fixture
def tag_filter_peer_config():
    """Peer config with tag_filter sync mode."""
    return PeerRegistryConfig(
        peer_id="test-peer",
        name="Test Peer",
        endpoint="https://peer.example.com",
        enabled=True,
        sync_mode="tag_filter",
        tag_filters=["production"],
    )


@pytest.fixture
def all_mode_peer_config():
    """Peer config with all sync mode."""
    return PeerRegistryConfig(
        peer_id="test-peer",
        name="Test Peer",
        endpoint="https://peer.example.com",
        enabled=True,
        sync_mode="all",
    )


@pytest.mark.unit
class TestFilterServersByConfig:
    """Tests for _filter_servers_by_config method."""

    @pytest.mark.asyncio
    async def test_sync_mode_all_returns_all_servers(
        self, mock_repo_factory, all_mode_peer_config, sample_servers
    ):
        """Test sync_mode='all' returns all servers."""
        service = PeerFederationService()
        await service.add_peer(all_mode_peer_config)

        filtered = service._filter_servers_by_config(
            sample_servers, all_mode_peer_config
        )

        assert len(filtered) == len(sample_servers)
        assert filtered == sample_servers

    @pytest.mark.asyncio
    async def test_sync_mode_whitelist_filters_by_whitelist_servers(
        self, mock_repo_factory, whitelist_peer_config, sample_servers
    ):
        """Test sync_mode='whitelist' filters by whitelist_servers."""
        service = PeerFederationService()
        await service.add_peer(whitelist_peer_config)

        filtered = service._filter_servers_by_config(
            sample_servers, whitelist_peer_config
        )

        # Should only include /server-a and /server-c
        assert len(filtered) == 2
        paths = [s["path"] for s in filtered]
        assert "/server-a" in paths
        assert "/server-c" in paths
        assert "/server-b" not in paths

    @pytest.mark.asyncio
    async def test_sync_mode_whitelist_with_empty_whitelist_returns_empty(
        self, mock_repo_factory, sample_servers
    ):
        """Test sync_mode='whitelist' with empty whitelist returns empty list."""
        peer_config = PeerRegistryConfig(
            peer_id="test-peer",
            name="Test Peer",
            endpoint="https://peer.example.com",
            enabled=True,
            sync_mode="whitelist",
            whitelist_servers=[],  # Empty whitelist
        )

        service = PeerFederationService()
        await service.add_peer(peer_config)

        filtered = service._filter_servers_by_config(sample_servers, peer_config)

        assert len(filtered) == 0
        assert filtered == []

    @pytest.mark.asyncio
    async def test_sync_mode_whitelist_with_none_whitelist_returns_empty(
        self, mock_repo_factory, sample_servers, whitelist_peer_config
    ):
        """Test sync_mode='whitelist' with None whitelist returns empty list."""
        # Modify config to have None for whitelist_servers
        # Note: Pydantic will convert None to empty list, so we test the behavior
        whitelist_peer_config.whitelist_servers = []

        service = PeerFederationService()
        await service.add_peer(whitelist_peer_config)

        filtered = service._filter_servers_by_config(sample_servers, whitelist_peer_config)

        assert len(filtered) == 0
        assert filtered == []

    @pytest.mark.asyncio
    async def test_sync_mode_tag_filter_filters_by_tags(
        self, mock_repo_factory, tag_filter_peer_config, sample_servers
    ):
        """Test sync_mode='tag_filter' filters by tags."""
        service = PeerFederationService()
        await service.add_peer(tag_filter_peer_config)

        filtered = service._filter_servers_by_config(
            sample_servers, tag_filter_peer_config
        )

        # Should include servers with "production" tag
        assert len(filtered) == 2
        paths = [s["path"] for s in filtered]
        assert "/server-a" in paths  # has production tag
        assert "/server-d" in paths  # has production tag
        assert "/server-b" not in paths  # only has staging
        assert "/server-c" not in paths  # only has internal category
        assert "/server-e" not in paths  # has no tags

    @pytest.mark.asyncio
    async def test_sync_mode_tag_filter_with_empty_tag_filters_returns_empty(
        self, mock_repo_factory, sample_servers
    ):
        """Test sync_mode='tag_filter' with empty tag_filters returns empty list."""
        peer_config = PeerRegistryConfig(
            peer_id="test-peer",
            name="Test Peer",
            endpoint="https://peer.example.com",
            enabled=True,
            sync_mode="tag_filter",
            tag_filters=[],  # Empty tag filters
        )

        service = PeerFederationService()
        await service.add_peer(peer_config)

        filtered = service._filter_servers_by_config(sample_servers, peer_config)

        assert len(filtered) == 0
        assert filtered == []

    @pytest.mark.asyncio
    async def test_sync_mode_tag_filter_with_none_tag_filters_returns_empty(
        self, mock_repo_factory, sample_servers, tag_filter_peer_config
    ):
        """Test sync_mode='tag_filter' with None tag_filters returns empty list."""
        # Modify config to have empty tag_filters
        # Note: Pydantic converts None to empty list, so we test the behavior
        tag_filter_peer_config.tag_filters = []

        service = PeerFederationService()
        await service.add_peer(tag_filter_peer_config)

        filtered = service._filter_servers_by_config(sample_servers, tag_filter_peer_config)

        assert len(filtered) == 0
        assert filtered == []

    @pytest.mark.asyncio
    async def test_sync_mode_tag_filter_matches_categories(
        self, mock_repo_factory, sample_servers
    ):
        """Test sync_mode='tag_filter' matches categories field."""
        peer_config = PeerRegistryConfig(
            peer_id="test-peer",
            name="Test Peer",
            endpoint="https://peer.example.com",
            enabled=True,
            sync_mode="tag_filter",
            tag_filters=["internal"],
        )

        service = PeerFederationService()
        await service.add_peer(peer_config)

        filtered = service._filter_servers_by_config(sample_servers, peer_config)

        # Should include /server-c which has "internal" in categories
        assert len(filtered) == 1
        assert filtered[0]["path"] == "/server-c"

    @pytest.mark.asyncio
    async def test_sync_mode_unknown_returns_all_servers(
        self, mock_repo_factory, sample_servers, all_mode_peer_config
    ):
        """Test that code handles unknown sync_mode gracefully."""
        service = PeerFederationService()
        await service.add_peer(all_mode_peer_config)

        # Directly modify sync_mode to simulate an unknown mode
        # This bypasses Pydantic validation to test fallback behavior
        all_mode_peer_config.sync_mode = "unknown_mode"

        filtered = service._filter_servers_by_config(sample_servers, all_mode_peer_config)

        # Should return all servers as fallback
        assert len(filtered) == len(sample_servers)
        assert filtered == sample_servers


@pytest.mark.unit
class TestFilterAgentsByConfig:
    """Tests for _filter_agents_by_config method."""

    @pytest.mark.asyncio
    async def test_sync_mode_all_returns_all_agents(
        self, mock_repo_factory, all_mode_peer_config, sample_agents
    ):
        """Test sync_mode='all' returns all agents."""
        service = PeerFederationService()
        await service.add_peer(all_mode_peer_config)

        filtered = service._filter_agents_by_config(sample_agents, all_mode_peer_config)

        assert len(filtered) == len(sample_agents)
        assert filtered == sample_agents

    @pytest.mark.asyncio
    async def test_sync_mode_whitelist_filters_by_whitelist_agents(
        self, mock_repo_factory, whitelist_peer_config, sample_agents
    ):
        """Test sync_mode='whitelist' filters by whitelist_agents."""
        service = PeerFederationService()
        await service.add_peer(whitelist_peer_config)

        filtered = service._filter_agents_by_config(sample_agents, whitelist_peer_config)

        # Should only include /agent-a
        assert len(filtered) == 1
        assert filtered[0]["path"] == "/agent-a"

    @pytest.mark.asyncio
    async def test_sync_mode_whitelist_with_empty_whitelist_returns_empty(
        self, mock_repo_factory, sample_agents
    ):
        """Test sync_mode='whitelist' with empty whitelist returns empty list."""
        peer_config = PeerRegistryConfig(
            peer_id="test-peer",
            name="Test Peer",
            endpoint="https://peer.example.com",
            enabled=True,
            sync_mode="whitelist",
            whitelist_agents=[],  # Empty whitelist
        )

        service = PeerFederationService()
        await service.add_peer(peer_config)

        filtered = service._filter_agents_by_config(sample_agents, peer_config)

        assert len(filtered) == 0
        assert filtered == []

    @pytest.mark.asyncio
    async def test_sync_mode_whitelist_with_none_whitelist_returns_empty(
        self, mock_repo_factory, sample_agents, whitelist_peer_config
    ):
        """Test sync_mode='whitelist' with None whitelist returns empty list."""
        # Modify config to have empty whitelist_agents
        # Note: Pydantic converts None to empty list, so we test the behavior
        whitelist_peer_config.whitelist_agents = []

        service = PeerFederationService()
        await service.add_peer(whitelist_peer_config)

        filtered = service._filter_agents_by_config(sample_agents, whitelist_peer_config)

        assert len(filtered) == 0
        assert filtered == []

    @pytest.mark.asyncio
    async def test_sync_mode_tag_filter_filters_by_tags(
        self, mock_repo_factory, tag_filter_peer_config, sample_agents
    ):
        """Test sync_mode='tag_filter' filters by tags."""
        service = PeerFederationService()
        await service.add_peer(tag_filter_peer_config)

        filtered = service._filter_agents_by_config(sample_agents, tag_filter_peer_config)

        # Should include agents with "production" tag
        assert len(filtered) == 1
        assert filtered[0]["path"] == "/agent-a"  # has production tag

    @pytest.mark.asyncio
    async def test_sync_mode_tag_filter_with_empty_tag_filters_returns_empty(
        self, mock_repo_factory, sample_agents
    ):
        """Test sync_mode='tag_filter' with empty tag_filters returns empty list."""
        peer_config = PeerRegistryConfig(
            peer_id="test-peer",
            name="Test Peer",
            endpoint="https://peer.example.com",
            enabled=True,
            sync_mode="tag_filter",
            tag_filters=[],  # Empty tag filters
        )

        service = PeerFederationService()
        await service.add_peer(peer_config)

        filtered = service._filter_agents_by_config(sample_agents, peer_config)

        assert len(filtered) == 0
        assert filtered == []

    @pytest.mark.asyncio
    async def test_sync_mode_tag_filter_with_none_tag_filters_returns_empty(
        self, mock_repo_factory, sample_agents, tag_filter_peer_config
    ):
        """Test sync_mode='tag_filter' with None tag_filters returns empty list."""
        # Modify config to have empty tag_filters
        # Note: Pydantic converts None to empty list, so we test the behavior
        tag_filter_peer_config.tag_filters = []

        service = PeerFederationService()
        await service.add_peer(tag_filter_peer_config)

        filtered = service._filter_agents_by_config(sample_agents, tag_filter_peer_config)

        assert len(filtered) == 0
        assert filtered == []

    @pytest.mark.asyncio
    async def test_sync_mode_tag_filter_matches_categories(self, mock_repo_factory, sample_agents):
        """Test sync_mode='tag_filter' matches categories field."""
        peer_config = PeerRegistryConfig(
            peer_id="test-peer",
            name="Test Peer",
            endpoint="https://peer.example.com",
            enabled=True,
            sync_mode="tag_filter",
            tag_filters=["automation"],
        )

        service = PeerFederationService()
        await service.add_peer(peer_config)

        filtered = service._filter_agents_by_config(sample_agents, peer_config)

        # Should include /agent-c which has "automation" in categories
        assert len(filtered) == 1
        assert filtered[0]["path"] == "/agent-c"

    @pytest.mark.asyncio
    async def test_sync_mode_unknown_returns_all_agents(
        self, mock_repo_factory, sample_agents, all_mode_peer_config
    ):
        """Test that code handles unknown sync_mode gracefully."""
        service = PeerFederationService()
        await service.add_peer(all_mode_peer_config)

        # Directly modify sync_mode to simulate an unknown mode
        # This bypasses Pydantic validation to test fallback behavior
        all_mode_peer_config.sync_mode = "unknown_mode"

        filtered = service._filter_agents_by_config(sample_agents, all_mode_peer_config)

        # Should return all agents as fallback
        assert len(filtered) == len(sample_agents)
        assert filtered == sample_agents


@pytest.mark.unit
class TestMatchesTagFilter:
    """Tests for _matches_tag_filter method."""

    @pytest.mark.asyncio
    async def test_matches_when_tag_in_tags_field(self, mock_repo_factory):
        """Test matches when tag is in 'tags' field."""
        service = PeerFederationService()

        item = {"path": "/test", "tags": ["production", "api"]}
        tag_filters = ["production"]

        assert service._matches_tag_filter(item, tag_filters) is True

    @pytest.mark.asyncio
    async def test_matches_when_tag_in_categories_field(self, mock_repo_factory):
        """Test matches when tag is in 'categories' field."""
        service = PeerFederationService()

        item = {"path": "/test", "categories": ["internal", "database"]}
        tag_filters = ["internal"]

        assert service._matches_tag_filter(item, tag_filters) is True

    @pytest.mark.asyncio
    async def test_matches_with_multiple_filters(self, mock_repo_factory):
        """Test matches with multiple tag filters."""
        service = PeerFederationService()

        item = {"path": "/test", "tags": ["staging"]}
        tag_filters = ["production", "staging", "development"]

        # Should match if any filter matches
        assert service._matches_tag_filter(item, tag_filters) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_match(self, mock_repo_factory):
        """Test returns False when no match."""
        service = PeerFederationService()

        item = {"path": "/test", "tags": ["staging"]}
        tag_filters = ["production"]

        assert service._matches_tag_filter(item, tag_filters) is False

    @pytest.mark.asyncio
    async def test_returns_false_for_empty_tag_filters(self, mock_repo_factory):
        """Test returns False for empty tag_filters."""
        service = PeerFederationService()

        item = {"path": "/test", "tags": ["production"]}
        tag_filters = []

        assert service._matches_tag_filter(item, tag_filters) is False

    @pytest.mark.asyncio
    async def test_handles_missing_tags_field(self, mock_repo_factory):
        """Test handles missing 'tags' field."""
        service = PeerFederationService()

        item = {"path": "/test"}  # No tags field
        tag_filters = ["production"]

        assert service._matches_tag_filter(item, tag_filters) is False

    @pytest.mark.asyncio
    async def test_handles_missing_categories_field(self, mock_repo_factory):
        """Test handles missing 'categories' field."""
        service = PeerFederationService()

        item = {"path": "/test", "tags": ["staging"]}  # No categories field
        tag_filters = ["internal"]

        assert service._matches_tag_filter(item, tag_filters) is False

    @pytest.mark.asyncio
    async def test_handles_non_list_tags_field(self, mock_repo_factory):
        """Test handles non-list 'tags' field."""
        service = PeerFederationService()

        item = {"path": "/test", "tags": "not-a-list"}
        tag_filters = ["production"]

        # Should handle gracefully and return False
        assert service._matches_tag_filter(item, tag_filters) is False

    @pytest.mark.asyncio
    async def test_handles_non_list_categories_field(self, mock_repo_factory):
        """Test handles non-list 'categories' field."""
        service = PeerFederationService()

        item = {"path": "/test", "categories": "not-a-list"}
        tag_filters = ["internal"]

        # Should handle gracefully and return False
        assert service._matches_tag_filter(item, tag_filters) is False

    @pytest.mark.asyncio
    async def test_matches_combined_tags_and_categories(self, mock_repo_factory):
        """Test matches when combining tags and categories."""
        service = PeerFederationService()

        item = {
            "path": "/test",
            "tags": ["production"],
            "categories": ["internal"],
        }
        tag_filters = ["internal"]

        # Should match from categories
        assert service._matches_tag_filter(item, tag_filters) is True

        tag_filters = ["production"]
        # Should match from tags
        assert service._matches_tag_filter(item, tag_filters) is True


@pytest.mark.unit
class TestSyncPeerWithFiltering:
    """Integration tests for sync_peer with filtering."""

    @pytest.mark.asyncio
    async def test_sync_peer_applies_whitelist_filters(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        whitelist_peer_config,
    ):
        """Test sync_peer applies whitelist filters correctly."""
        service = PeerFederationService()
        await service.add_peer(whitelist_peer_config)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            # Return servers that should be filtered
            mock_client.fetch_servers.return_value = [
                {"path": "/server-a", "name": "Server A"},  # In whitelist
                {"path": "/server-b", "name": "Server B"},  # Not in whitelist
                {"path": "/server-c", "name": "Server C"},  # In whitelist
            ]
            # Return agents that should be filtered
            mock_client.fetch_agents.return_value = [
                {
                    "path": "/agent-a",
                    "name": "Agent A",
                    "version": "1.0.0",
                    "description": "Agent A",
                    "url": "https://example.com/agent-a",
                },  # In whitelist
                {
                    "path": "/agent-b",
                    "name": "Agent B",
                    "version": "1.0.0",
                    "description": "Agent B",
                    "url": "https://example.com/agent-b",
                },  # Not in whitelist
            ]
            mock_client_class.return_value = mock_client

            result = await service.sync_peer(whitelist_peer_config.peer_id)

            # Should only sync whitelisted items
            assert result.success is True
            assert result.servers_synced == 2  # server-a and server-c
            assert result.agents_synced == 1  # agent-a

    @pytest.mark.asyncio
    async def test_sync_peer_applies_tag_filters(
        self,
        mock_repo_factory,
        mock_server_service,
        mock_agent_service,
        tag_filter_peer_config,
    ):
        """Test sync_peer applies tag filters correctly."""
        service = PeerFederationService()
        await service.add_peer(tag_filter_peer_config)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            # Return servers with various tags
            mock_client.fetch_servers.return_value = [
                {"path": "/server-a", "name": "Server A", "tags": ["production"]},
                {"path": "/server-b", "name": "Server B", "tags": ["staging"]},
                {"path": "/server-c", "name": "Server C", "tags": ["production", "api"]},
            ]
            # Return agents with various tags
            mock_client.fetch_agents.return_value = [
                {
                    "path": "/agent-a",
                    "name": "Agent A",
                    "version": "1.0.0",
                    "description": "Agent A",
                    "url": "https://example.com/agent-a",
                    "tags": ["production"],
                },
                {
                    "path": "/agent-b",
                    "name": "Agent B",
                    "version": "1.0.0",
                    "description": "Agent B",
                    "url": "https://example.com/agent-b",
                    "tags": ["utility"],
                },
            ]
            mock_client_class.return_value = mock_client

            result = await service.sync_peer(tag_filter_peer_config.peer_id)

            # Should only sync items with production tag
            assert result.success is True
            assert result.servers_synced == 2  # server-a and server-c
            assert result.agents_synced == 1  # agent-a


@pytest.mark.unit
class TestDetectOrphanedItems:
    """Tests for detect_orphaned_items method."""

    @pytest.mark.asyncio
    async def test_detects_servers_missing_from_peer(
        self, mock_repo_factory, mock_server_service, mock_agent_service, sample_peer_config
    ):
        """Test detects servers that exist locally but are missing from peer."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Set up local servers with sync_metadata
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Server 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "original_path": "/server-1",
                },
            },
            "/test-peer/server-2": {
                "path": "/test-peer/server-2",
                "name": "Server 2",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "original_path": "/server-2",
                },
            },
        }

        # Current peer only has server-1
        current_server_paths = ["/server-1"]
        current_agent_paths = []

        orphaned_servers, orphaned_agents = service.detect_orphaned_items(
            "test-peer", current_server_paths, current_agent_paths
        )

        # server-2 should be detected as orphaned
        assert len(orphaned_servers) == 1
        assert "/test-peer/server-2" in orphaned_servers
        assert len(orphaned_agents) == 0

    @pytest.mark.asyncio
    async def test_detects_agents_missing_from_peer(
        self, mock_repo_factory, mock_server_service, mock_agent_service, sample_peer_config
    ):
        """Test detects agents that exist locally but are missing from peer."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Set up local agents with sync_metadata
        mock_agent_service.registered_agents = {
            "/test-peer/agent-1": MagicMock(
                path="/test-peer/agent-1",
                name="Agent 1",
                model_dump=lambda: {
                    "path": "/test-peer/agent-1",
                    "name": "Agent 1",
                    "sync_metadata": {
                        "source_peer_id": "test-peer",
                        "original_path": "/agent-1",
                    },
                },
            ),
            "/test-peer/agent-2": MagicMock(
                path="/test-peer/agent-2",
                name="Agent 2",
                model_dump=lambda: {
                    "path": "/test-peer/agent-2",
                    "name": "Agent 2",
                    "sync_metadata": {
                        "source_peer_id": "test-peer",
                        "original_path": "/agent-2",
                    },
                },
            ),
        }

        # Current peer only has agent-1
        current_server_paths = []
        current_agent_paths = ["/agent-1"]

        orphaned_servers, orphaned_agents = service.detect_orphaned_items(
            "test-peer", current_server_paths, current_agent_paths
        )

        # agent-2 should be detected as orphaned
        assert len(orphaned_servers) == 0
        assert len(orphaned_agents) == 1
        assert "/test-peer/agent-2" in orphaned_agents

    @pytest.mark.asyncio
    async def test_returns_empty_lists_when_no_orphans(
        self, mock_repo_factory, mock_server_service, mock_agent_service, sample_peer_config
    ):
        """Test returns empty lists when there are no orphaned items."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Set up local items that all exist in peer
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Server 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "original_path": "/server-1",
                },
            },
        }

        mock_agent_service.registered_agents = {
            "/test-peer/agent-1": MagicMock(
                model_dump=lambda: {
                    "path": "/test-peer/agent-1",
                    "name": "Agent 1",
                    "sync_metadata": {
                        "source_peer_id": "test-peer",
                        "original_path": "/agent-1",
                    },
                }
            ),
        }

        # All items exist in peer
        current_server_paths = ["/server-1"]
        current_agent_paths = ["/agent-1"]

        orphaned_servers, orphaned_agents = service.detect_orphaned_items(
            "test-peer", current_server_paths, current_agent_paths
        )

        assert len(orphaned_servers) == 0
        assert len(orphaned_agents) == 0

    @pytest.mark.asyncio
    async def test_path_normalization_handles_with_without_leading_slash(
        self, mock_repo_factory, mock_server_service, mock_agent_service, sample_peer_config
    ):
        """Test path normalization handles paths with and without leading slash."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Local server with original_path "/server-1"
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Server 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "original_path": "/server-1",
                },
            },
        }

        # Current peer returns path without leading slash
        current_server_paths = ["server-1"]  # No leading slash
        current_agent_paths = []

        orphaned_servers, orphaned_agents = service.detect_orphaned_items(
            "test-peer", current_server_paths, current_agent_paths
        )

        # Should not be detected as orphaned (path normalization should work)
        assert len(orphaned_servers) == 0

    @pytest.mark.asyncio
    async def test_only_considers_items_from_specified_peer(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test only considers items from the specified peer."""
        service = PeerFederationService()

        # Set up items from different peers
        mock_server_service.registered_servers = {
            "/peer-a/server-1": {
                "path": "/peer-a/server-1",
                "name": "Server 1",
                "sync_metadata": {
                    "source_peer_id": "peer-a",
                    "original_path": "/server-1",
                },
            },
            "/peer-b/server-2": {
                "path": "/peer-b/server-2",
                "name": "Server 2",
                "sync_metadata": {
                    "source_peer_id": "peer-b",
                    "original_path": "/server-2",
                },
            },
        }

        # Check for orphans from peer-a only
        current_server_paths = []  # peer-a has no servers
        current_agent_paths = []

        orphaned_servers, orphaned_agents = service.detect_orphaned_items(
            "peer-a", current_server_paths, current_agent_paths
        )

        # Only peer-a's server should be detected
        assert len(orphaned_servers) == 1
        assert "/peer-a/server-1" in orphaned_servers
        assert "/peer-b/server-2" not in orphaned_servers


@pytest.mark.unit
class TestMarkItemAsOrphaned:
    """Tests for mark_item_as_orphaned method."""

    @pytest.mark.asyncio
    async def test_marks_server_as_orphaned(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test successfully marks a server as orphaned."""
        service = PeerFederationService()

        # Set up existing server
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Server 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                },
            }
        }
        mock_server_service.update_server.return_value = True

        result = service.mark_item_as_orphaned("/test-peer/server-1", "server")

        assert result is True
        mock_server_service.update_server.assert_called_once()

        # Check that update was called with correct metadata
        call_args = mock_server_service.update_server.call_args
        updated_data = call_args[0][1]
        assert updated_data["sync_metadata"]["is_orphaned"] is True
        assert "orphaned_at" in updated_data["sync_metadata"]

    @pytest.mark.asyncio
    async def test_marks_agent_as_orphaned(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test successfully marks an agent as orphaned."""
        service = PeerFederationService()

        # Set up existing agent
        existing_agent = MagicMock(
            path="/test-peer/agent-1",
            name="Agent 1",
            model_dump=lambda: {
                "path": "/test-peer/agent-1",
                "name": "Agent 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                },
            },
        )
        mock_agent_service.registered_agents = {
            "/test-peer/agent-1": existing_agent,
        }
        mock_agent_service.update_agent.return_value = MagicMock()

        result = service.mark_item_as_orphaned("/test-peer/agent-1", "agent")

        assert result is True
        mock_agent_service.update_agent.assert_called_once()

        # Check that update was called with correct metadata
        call_args = mock_agent_service.update_agent.call_args
        updated_data = call_args[0][1]
        assert updated_data["sync_metadata"]["is_orphaned"] is True
        assert "orphaned_at" in updated_data["sync_metadata"]

    @pytest.mark.asyncio
    async def test_handles_non_existent_server(
        self, mock_repo_factory, mock_server_service
    ):
        """Test handles non-existent server gracefully."""
        service = PeerFederationService()

        mock_server_service.registered_servers = {}

        result = service.mark_item_as_orphaned("/non-existent", "server")

        assert result is False
        mock_server_service.update_server.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_non_existent_agent(
        self, mock_repo_factory, mock_agent_service
    ):
        """Test handles non-existent agent gracefully."""
        service = PeerFederationService()

        mock_agent_service.registered_agents = {}

        result = service.mark_item_as_orphaned("/non-existent", "agent")

        assert result is False
        mock_agent_service.update_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_sync_metadata_correctly(
        self, mock_repo_factory, mock_server_service
    ):
        """Test updates sync_metadata with orphaned flag and timestamp."""
        service = PeerFederationService()

        # Set up existing server with existing metadata
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Server 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "original_path": "/server-1",
                    "synced_at": "2024-01-01T00:00:00Z",
                },
            }
        }
        mock_server_service.update_server.return_value = True

        service.mark_item_as_orphaned("/test-peer/server-1", "server")

        # Check that existing metadata is preserved and new fields added
        call_args = mock_server_service.update_server.call_args
        updated_data = call_args[0][1]
        metadata = updated_data["sync_metadata"]

        assert metadata["source_peer_id"] == "test-peer"
        assert metadata["original_path"] == "/server-1"
        assert metadata["synced_at"] == "2024-01-01T00:00:00Z"
        assert metadata["is_orphaned"] is True
        assert "orphaned_at" in metadata


@pytest.mark.unit
class TestHandleOrphanedItems:
    """Tests for handle_orphaned_items method."""

    @pytest.mark.asyncio
    async def test_mark_action_marks_all_orphans(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test mark action marks all orphaned items."""
        service = PeerFederationService()

        # Set up existing items
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "sync_metadata": {"source_peer_id": "test-peer"},
            },
            "/test-peer/server-2": {
                "path": "/test-peer/server-2",
                "sync_metadata": {"source_peer_id": "test-peer"},
            },
        }
        mock_agent_service.registered_agents = {
            "/test-peer/agent-1": MagicMock(
                model_dump=lambda: {
                    "path": "/test-peer/agent-1",
                    "sync_metadata": {"source_peer_id": "test-peer"},
                }
            ),
        }
        mock_server_service.update_server.return_value = True
        mock_agent_service.update_agent.return_value = MagicMock()

        orphaned_servers = ["/test-peer/server-1", "/test-peer/server-2"]
        orphaned_agents = ["/test-peer/agent-1"]

        count = service.handle_orphaned_items(
            "test-peer", orphaned_servers, orphaned_agents, action="mark"
        )

        assert count == 3
        assert mock_server_service.update_server.call_count == 2
        assert mock_agent_service.update_agent.call_count == 1

    @pytest.mark.asyncio
    async def test_delete_action_removes_orphans(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test delete action removes orphaned items."""
        service = PeerFederationService()

        mock_server_service.remove_server.return_value = True
        mock_agent_service.remove_agent.return_value = True

        orphaned_servers = ["/test-peer/server-1"]
        orphaned_agents = ["/test-peer/agent-1"]

        count = service.handle_orphaned_items(
            "test-peer", orphaned_servers, orphaned_agents, action="delete"
        )

        assert count == 2
        mock_server_service.remove_server.assert_called_once_with("/test-peer/server-1")
        mock_agent_service.remove_agent.assert_called_once_with("/test-peer/agent-1")

    @pytest.mark.asyncio
    async def test_returns_count_of_handled_items(
        self, mock_repo_factory, mock_server_service, mock_agent_service
    ):
        """Test returns correct count of handled items."""
        service = PeerFederationService()

        # Set up one success and one failure
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "sync_metadata": {"source_peer_id": "test-peer"},
            },
        }
        mock_server_service.update_server.side_effect = [True, False]

        orphaned_servers = ["/test-peer/server-1", "/test-peer/server-2"]
        orphaned_agents = []

        count = service.handle_orphaned_items(
            "test-peer", orphaned_servers, orphaned_agents, action="mark"
        )

        # Only one should be counted as handled (the success)
        assert count == 1

    @pytest.mark.asyncio
    async def test_handles_empty_lists(self, mock_repo_factory, mock_server_service, mock_agent_service):
        """Test handles empty orphan lists gracefully."""
        service = PeerFederationService()

        count = service.handle_orphaned_items(
            "test-peer", [], [], action="mark"
        )

        assert count == 0
        mock_server_service.update_server.assert_not_called()
        mock_agent_service.update_agent.assert_not_called()


@pytest.mark.unit
class TestSetLocalOverride:
    """Tests for set_local_override method."""

    @pytest.mark.asyncio
    async def test_sets_override_to_true_for_server(
        self, mock_repo_factory, mock_server_service
    ):
        """Test sets local override to True for a server."""
        service = PeerFederationService()

        # Set up existing server
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Server 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                },
            }
        }
        mock_server_service.update_server.return_value = True

        result = service.set_local_override("/test-peer/server-1", "server", True)

        assert result is True
        mock_server_service.update_server.assert_called_once()

        # Check that override flag was set
        call_args = mock_server_service.update_server.call_args
        updated_data = call_args[0][1]
        assert updated_data["sync_metadata"]["local_overrides"] is True

    @pytest.mark.asyncio
    async def test_clears_override_for_server(
        self, mock_repo_factory, mock_server_service
    ):
        """Test clears local override (sets to False) for a server."""
        service = PeerFederationService()

        # Set up existing server with override
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Server 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "local_overrides": True,
                },
            }
        }
        mock_server_service.update_server.return_value = True

        result = service.set_local_override("/test-peer/server-1", "server", False)

        assert result is True

        # Check that override flag was cleared
        call_args = mock_server_service.update_server.call_args
        updated_data = call_args[0][1]
        assert updated_data["sync_metadata"]["local_overrides"] is False

    @pytest.mark.asyncio
    async def test_sets_override_to_true_for_agent(
        self, mock_repo_factory, mock_agent_service
    ):
        """Test sets local override to True for an agent."""
        service = PeerFederationService()

        # Set up existing agent
        existing_agent = MagicMock(
            path="/test-peer/agent-1",
            model_dump=lambda: {
                "path": "/test-peer/agent-1",
                "name": "Agent 1",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                },
            },
        )
        mock_agent_service.registered_agents = {
            "/test-peer/agent-1": existing_agent,
        }
        mock_agent_service.update_agent.return_value = MagicMock()

        result = service.set_local_override("/test-peer/agent-1", "agent", True)

        assert result is True
        mock_agent_service.update_agent.assert_called_once()

        # Check that override flag was set
        call_args = mock_agent_service.update_agent.call_args
        updated_data = call_args[0][1]
        assert updated_data["sync_metadata"]["local_overrides"] is True

    @pytest.mark.asyncio
    async def test_handles_non_existent_server(
        self, mock_repo_factory, mock_server_service
    ):
        """Test handles non-existent server gracefully."""
        service = PeerFederationService()

        mock_server_service.registered_servers = {}

        result = service.set_local_override("/non-existent", "server", True)

        assert result is False
        mock_server_service.update_server.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_non_existent_agent(
        self, mock_repo_factory, mock_agent_service
    ):
        """Test handles non-existent agent gracefully."""
        service = PeerFederationService()

        mock_agent_service.registered_agents = {}

        result = service.set_local_override("/non-existent", "agent", True)

        assert result is False
        mock_agent_service.update_agent.assert_not_called()


@pytest.mark.unit
class TestIsLocallyOverridden:
    """Tests for is_locally_overridden method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_override_is_set(self, mock_repo_factory):
        """Test returns True when local_overrides is True."""
        service = PeerFederationService()

        item = {
            "path": "/test-peer/server-1",
            "name": "Server 1",
            "sync_metadata": {
                "local_overrides": True,
            },
        }

        assert service.is_locally_overridden(item) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_override_not_set(self, mock_repo_factory):
        """Test returns False when local_overrides is False or not present."""
        service = PeerFederationService()

        item = {
            "path": "/test-peer/server-1",
            "name": "Server 1",
            "sync_metadata": {
                "local_overrides": False,
            },
        }

        assert service.is_locally_overridden(item) is False

    @pytest.mark.asyncio
    async def test_returns_false_when_local_overrides_field_missing(self, mock_repo_factory):
        """Test returns False when local_overrides field is missing."""
        service = PeerFederationService()

        item = {
            "path": "/test-peer/server-1",
            "name": "Server 1",
            "sync_metadata": {
                "source_peer_id": "test-peer",
            },
        }

        assert service.is_locally_overridden(item) is False

    @pytest.mark.asyncio
    async def test_handles_missing_sync_metadata(self, mock_repo_factory):
        """Test handles missing sync_metadata gracefully."""
        service = PeerFederationService()

        item = {
            "path": "/test-peer/server-1",
            "name": "Server 1",
        }

        assert service.is_locally_overridden(item) is False


@pytest.mark.unit
class TestLocalOverrideIntegration:
    """Integration tests for local override preventing sync updates."""

    @pytest.mark.asyncio
    async def test_local_override_prevents_server_sync_update(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test local override prevents update during sync for servers."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Set up existing server with local override
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Original Name",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "original_path": "/server-1",
                    "local_overrides": True,
                },
            }
        }

        # Try to sync updated server data
        servers = [
            {
                "path": "/server-1",
                "name": "Updated Name",  # This should be ignored
            }
        ]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Should not update (returns 0)
        assert count == 0
        mock_server_service.update_server.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_override_prevents_agent_sync_update(
        self, mock_repo_factory, mock_agent_service, sample_peer_config
    ):
        """Test local override prevents update during sync for agents."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Set up existing agent with local override
        existing_agent = MagicMock(
            path="/test-peer/agent-1",
            model_dump=lambda: {
                "path": "/test-peer/agent-1",
                "name": "Original Agent",
                "version": "1.0.0",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "original_path": "/agent-1",
                    "local_overrides": True,
                },
            },
        )
        mock_agent_service.registered_agents = {
            "/test-peer/agent-1": existing_agent,
        }

        # Try to sync updated agent data
        agents = [
            {
                "path": "/agent-1",
                "name": "Updated Agent",  # This should be ignored
                "version": "2.0.0",
                "description": "Updated description",
                "url": "https://example.com/agent",
            }
        ]

        count = service._store_synced_agents(sample_peer_config.peer_id, agents)

        # Should not update (returns 0)
        assert count == 0
        mock_agent_service.update_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_updates_items_without_local_override(
        self, mock_repo_factory, mock_server_service, sample_peer_config
    ):
        """Test sync updates items that don't have local override."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Set up existing server WITHOUT local override
        mock_server_service.registered_servers = {
            "/test-peer/server-1": {
                "path": "/test-peer/server-1",
                "name": "Original Name",
                "sync_metadata": {
                    "source_peer_id": "test-peer",
                    "original_path": "/server-1",
                    "local_overrides": False,
                },
            }
        }
        mock_server_service.update_server.return_value = True

        # Try to sync updated server data
        servers = [
            {
                "path": "/server-1",
                "name": "Updated Name",  # This should be applied
            }
        ]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Should update (returns 1)
        assert count == 1
        mock_server_service.update_server.assert_called_once()
