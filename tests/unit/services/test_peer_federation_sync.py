"""
Unit tests for Peer Federation Service Sync Methods.

Tests for sync_peer, sync_all_peers, and storage methods
(_store_synced_servers and _store_synced_agents).
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from typing import Dict, Any, List

from registry.services.peer_federation_service import (
    PeerFederationService,
    get_peer_federation_service,
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
def mock_settings(tmp_path):
    """Mock settings to use temp directories."""
    with patch("registry.services.peer_federation_service.settings") as mock:
        mock.peers_dir = tmp_path / "peers"
        mock.peers_dir.mkdir(parents=True, exist_ok=True)
        mock.peer_sync_state_file_path = tmp_path / "peer_sync_state.json"
        yield mock


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

    def test_sync_peer_successful_with_servers_and_agents(
        self,
        mock_settings,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test successful sync with servers and agents."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

            result = service.sync_peer(sample_peer_config.peer_id)

            # Verify result
            assert result.success is True
            assert result.peer_id == sample_peer_config.peer_id
            assert result.servers_synced == 2
            assert result.agents_synced == 1
            assert result.error_message is None
            assert result.duration_seconds > 0
            assert result.new_generation == 1

            # Verify sync status updated
            sync_status = service.get_sync_status(sample_peer_config.peer_id)
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

    def test_sync_peer_disabled_peer_raises_error(
        self, mock_settings, sample_peer_config_disabled
    ):
        """Test sync disabled peer raises ValueError."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config_disabled)

        with pytest.raises(ValueError, match="is disabled"):
            service.sync_peer(sample_peer_config_disabled.peer_id)

    def test_sync_peer_nonexistent_peer_raises_error(self, mock_settings):
        """Test sync non-existent peer raises ValueError."""
        service = PeerFederationService()

        with pytest.raises(ValueError, match="Peer not found"):
            service.sync_peer("nonexistent-peer")

    def test_sync_peer_network_error_handling(
        self,
        mock_settings,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test network error handling during sync."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Mock PeerRegistryClient to raise exception
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.side_effect = Exception("Network error")
            mock_client_class.return_value = mock_client

            result = service.sync_peer(sample_peer_config.peer_id)

            # Verify result
            assert result.success is False
            assert result.peer_id == sample_peer_config.peer_id
            assert result.servers_synced == 0
            assert result.agents_synced == 0
            assert "Network error" in result.error_message
            assert result.duration_seconds > 0

            # Verify sync status updated with failure
            sync_status = service.get_sync_status(sample_peer_config.peer_id)
            assert sync_status.sync_in_progress is False
            assert sync_status.consecutive_failures == 1
            assert sync_status.is_healthy is False

            # Verify history entry created for failure
            assert len(sync_status.sync_history) == 1
            history = sync_status.sync_history[0]
            assert history.success is False
            assert "Network error" in history.error_message

    def test_sync_peer_uses_since_generation_for_incremental_sync(
        self,
        mock_settings,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test incremental sync uses since_generation."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Set existing sync status with generation 5
        sync_status = service.get_sync_status(sample_peer_config.peer_id)
        sync_status.current_generation = 5
        service.update_sync_status(sample_peer_config.peer_id, sync_status)

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

            result = service.sync_peer(sample_peer_config.peer_id)

            # Verify fetch_servers was called with since_generation=5
            mock_client.fetch_servers.assert_called_once_with(since_generation=5)
            mock_client.fetch_agents.assert_called_once_with(since_generation=5)

            # Verify generation incremented
            assert result.new_generation == 6

    def test_sync_peer_generation_only_increments_when_items_synced(
        self,
        mock_settings,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test generation only increments when items are synced."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Set existing sync status with generation 5
        sync_status = service.get_sync_status(sample_peer_config.peer_id)
        sync_status.current_generation = 5
        service.update_sync_status(sample_peer_config.peer_id, sync_status)

        # Mock PeerRegistryClient - return empty lists
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = []
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            result = service.sync_peer(sample_peer_config.peer_id)

            # Verify generation DID NOT increment (no items synced)
            assert result.new_generation == 5

    def test_sync_peer_generation_increments_on_first_sync(
        self,
        mock_settings,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test generation increments on first sync even with no items."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Mock PeerRegistryClient - return empty lists
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = []
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            result = service.sync_peer(sample_peer_config.peer_id)

            # Verify generation incremented (since_generation was 0)
            assert result.new_generation == 1

    def test_sync_peer_status_updated_correctly(
        self,
        mock_settings,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test sync status updated correctly during sync."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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
            initial_status = service.get_sync_status(sample_peer_config.peer_id)
            assert initial_status.sync_in_progress is False

            result = service.sync_peer(sample_peer_config.peer_id)

            # Get final status
            final_status = service.get_sync_status(sample_peer_config.peer_id)
            assert final_status.sync_in_progress is False
            assert final_status.last_sync_attempt is not None
            assert final_status.last_successful_sync is not None
            assert final_status.last_health_check is not None

    def test_sync_peer_handles_none_responses_from_client(
        self,
        mock_settings,
        mock_server_service,
        mock_agent_service,
        sample_peer_config,
    ):
        """Test sync handles None responses from client."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Mock PeerRegistryClient to return None
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = None
            mock_client.fetch_agents.return_value = None
            mock_client_class.return_value = mock_client

            result = service.sync_peer(sample_peer_config.peer_id)

            # Should handle None gracefully and treat as empty list
            assert result.success is True
            assert result.servers_synced == 0
            assert result.agents_synced == 0


@pytest.mark.unit
class TestSyncAllPeers:
    """Tests for sync_all_peers method."""

    def test_sync_all_enabled_peers(
        self, mock_settings, mock_server_service, mock_agent_service
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

        service.add_peer(peer1)
        service.add_peer(peer2)
        service.add_peer(peer3)

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

            results = service.sync_all_peers(enabled_only=True)

            # Should only sync enabled peers
            assert len(results) == 2
            assert "peer1" in results
            assert "peer2" in results
            assert "peer3" not in results

            # Verify both succeeded
            assert results["peer1"].success is True
            assert results["peer2"].success is True

    def test_sync_all_peers_skip_disabled_when_enabled_only_true(
        self, mock_settings, mock_server_service, mock_agent_service
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

        service.add_peer(enabled_peer)
        service.add_peer(disabled_peer)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = []
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            results = service.sync_all_peers(enabled_only=True)

            # Should only sync enabled peer
            assert len(results) == 1
            assert "enabled-peer" in results
            assert "disabled-peer" not in results

    def test_sync_all_peers_continue_on_individual_failure(
        self, mock_settings, mock_server_service, mock_agent_service
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

        service.add_peer(peer1)
        service.add_peer(peer2)

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

            results = service.sync_all_peers(enabled_only=True)

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

    def test_sync_all_peers_returns_correct_result_dictionary(
        self, mock_settings, mock_server_service, mock_agent_service
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

        service.add_peer(peer1)
        service.add_peer(peer2)

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

            results = service.sync_all_peers(enabled_only=True)

            # Verify result structure
            assert isinstance(results, dict)
            assert len(results) == 2

            for peer_id, result in results.items():
                assert isinstance(result, SyncResult)
                assert result.peer_id == peer_id
                assert result.success is True
                assert result.servers_synced == 1
                assert result.agents_synced == 1

    def test_sync_all_peers_with_enabled_only_false(
        self, mock_settings, mock_server_service, mock_agent_service
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

        service.add_peer(enabled_peer)
        service.add_peer(disabled_peer)

        # Mock PeerRegistryClient
        with patch(
            "registry.services.peer_federation_service.PeerRegistryClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.fetch_servers.return_value = []
            mock_client.fetch_agents.return_value = []
            mock_client_class.return_value = mock_client

            results = service.sync_all_peers(enabled_only=False)

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

    def test_store_new_server_with_sync_metadata(
        self, mock_settings, mock_server_service, sample_peer_config
    ):
        """Test store new server with sync_metadata."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

    def test_store_update_existing_server(
        self, mock_settings, mock_server_service, sample_peer_config
    ):
        """Test update existing server."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

    def test_store_path_normalization_no_leading_slash(
        self, mock_settings, mock_server_service, sample_peer_config
    ):
        """Test path normalization when path missing leading slash."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Path without leading slash
        servers = [{"path": "test-server", "name": "Test Server"}]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        assert count == 1

        # Verify path normalized and prefixed
        call_args = mock_server_service.register_server.call_args[0][0]
        assert call_args["path"] == "/test-peer/test-server"

    def test_store_path_prefixing_with_peer_id(
        self, mock_settings, mock_server_service, sample_peer_config
    ):
        """Test path prefixing with peer_id."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        servers = [{"path": "/my-server", "name": "My Server"}]

        service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Verify path prefixed correctly
        call_args = mock_server_service.register_server.call_args[0][0]
        assert call_args["path"] == "/test-peer/my-server"

        # Verify original path preserved in metadata
        metadata = call_args["sync_metadata"]
        assert metadata["original_path"] == "/my-server"

    def test_store_skip_servers_missing_path_field(
        self, mock_settings, mock_server_service, sample_peer_config
    ):
        """Test skip servers missing path field."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        servers = [
            {"name": "No Path Server"},  # Missing path
            {"path": "/valid-server", "name": "Valid Server"},
        ]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Should only store the valid server
        assert count == 1
        mock_server_service.register_server.assert_called_once()

    def test_store_handle_storage_failures(
        self, mock_settings, mock_server_service, sample_peer_config
    ):
        """Test handle storage failures gracefully."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Make register_server fail
        mock_server_service.register_server.return_value = False

        servers = [{"path": "/test-server", "name": "Test Server"}]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Should return 0 for failed storage
        assert count == 0

    def test_store_handle_exceptions_during_storage(
        self, mock_settings, mock_server_service, sample_peer_config
    ):
        """Test handle exceptions during storage."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Make register_server raise exception
        mock_server_service.register_server.side_effect = Exception("Storage error")

        servers = [{"path": "/test-server", "name": "Test Server"}]

        count = service._store_synced_servers(sample_peer_config.peer_id, servers)

        # Should handle exception and return 0
        assert count == 0


@pytest.mark.unit
class TestStoreSyncedAgents:
    """Tests for _store_synced_agents method."""

    def test_store_new_agent_with_sync_metadata(
        self, mock_settings, mock_agent_service, sample_peer_config
    ):
        """Test store new agent with sync_metadata."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

    def test_store_update_existing_agent(
        self, mock_settings, mock_agent_service, sample_peer_config
    ):
        """Test update existing agent."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Simulate existing agent
        existing_agent = MagicMock()
        existing_agent.path = "/test-peer/test-agent"
        mock_agent_service.registered_agents["/test-peer/test-agent"] = existing_agent

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

    def test_store_path_normalization(
        self, mock_settings, mock_agent_service, sample_peer_config
    ):
        """Test path normalization for agents."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

    def test_store_handle_validation_errors(
        self, mock_settings, mock_agent_service, sample_peer_config
    ):
        """Test handle validation errors gracefully."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

    def test_store_handle_storage_failures(
        self, mock_settings, mock_agent_service, sample_peer_config
    ):
        """Test handle storage failures gracefully."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

    def test_store_skip_agents_missing_path_field(
        self, mock_settings, mock_agent_service, sample_peer_config
    ):
        """Test skip agents missing path field."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

    def test_store_handle_exceptions_during_storage(
        self, mock_settings, mock_agent_service, sample_peer_config
    ):
        """Test handle exceptions during storage."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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

    def test_store_update_agent_returns_none_on_failure(
        self, mock_settings, mock_agent_service, sample_peer_config
    ):
        """Test update agent when it returns None (failure)."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

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
