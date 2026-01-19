"""
Unit tests for Peer Management API endpoints.

Tests the CRUD operations, sync operations, and topology endpoint
for peer registry management.
"""

import math
import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from fastapi import status
from fastapi.testclient import TestClient

from registry.main import app
from registry.auth.dependencies import enhanced_auth
from registry.schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
    SyncResult,
)


@pytest.fixture
def mock_admin_auth():
    """Mock enhanced_auth for admin user."""
    return {
        "username": "admin-user",
        "groups": ["admin"],
        "scopes": ["mcp-registry-admin"],
        "auth_method": "oauth2",
        "provider": "keycloak",
        "accessible_servers": [],
        "accessible_services": ["all"],
        "can_modify_servers": True,
        "is_admin": True,
    }


@pytest.fixture
def sample_peer_config() -> PeerRegistryConfig:
    """Create a sample peer config for testing."""
    return PeerRegistryConfig(
        peer_id="test-peer-1",
        name="Test Peer Registry",
        endpoint="https://test-peer.example.com",
        enabled=True,
        sync_mode="all",
        sync_interval_minutes=60,
    )


@pytest.fixture
def sample_peer_config_disabled() -> PeerRegistryConfig:
    """Create a disabled peer config for testing."""
    return PeerRegistryConfig(
        peer_id="test-peer-2",
        name="Disabled Peer Registry",
        endpoint="https://disabled-peer.example.com",
        enabled=False,
        sync_mode="whitelist",
        sync_interval_minutes=30,
        whitelist_servers=["/test-server"],  # Add to avoid warning
    )


@pytest.fixture
def sample_sync_status() -> PeerSyncStatus:
    """Create a sample sync status for testing."""
    return PeerSyncStatus(
        peer_id="test-peer-1",
        is_healthy=True,
        last_successful_sync=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        total_servers_synced=10,
        total_agents_synced=5,
    )


@pytest.fixture
def sample_sync_status_unhealthy() -> PeerSyncStatus:
    """Create an unhealthy sync status for testing."""
    return PeerSyncStatus(
        peer_id="test-peer-2",
        is_healthy=False,
        last_successful_sync=None,
        total_servers_synced=0,
        total_agents_synced=0,
        consecutive_failures=5,
    )


@pytest.fixture(autouse=True)
def cleanup_overrides():
    """Clean up dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


# --- Topology Endpoint Tests ---


class TestGetFederationTopology:
    """Tests for GET /api/v1/peers/topology endpoint."""

    def test_returns_empty_topology_with_no_peers(
        self,
        mock_admin_auth,
    ):
        """Test topology returns only 'this registry' node when no peers exist."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.list_peers = AsyncMock(return_value=[])
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers/topology")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert "nodes" in data
            assert "edges" in data
            assert len(data["nodes"]) == 1  # Only "this registry"
            assert len(data["edges"]) == 0

            # Verify "this registry" node
            this_node = data["nodes"][0]
            assert this_node["id"] == "this-registry"
            assert this_node["type"] == "registry"
            assert this_node["data"]["isLocal"] is True
            assert this_node["data"]["status"] == "healthy"

    def test_returns_nodes_and_edges_for_enabled_peers(
        self,
        mock_admin_auth,
        sample_peer_config,
        sample_sync_status,
    ):
        """Test topology returns nodes and edges for enabled peers."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.list_peers = AsyncMock(return_value=[sample_peer_config])
            mock_service_instance.get_sync_status = AsyncMock(return_value=sample_sync_status)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers/topology")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert len(data["nodes"]) == 2  # "this registry" + 1 peer
            assert len(data["edges"]) == 1  # 1 edge from peer to this registry

            # Find peer node
            peer_node = next(
                n for n in data["nodes"] if n["id"] == "test-peer-1"
            )
            assert peer_node["data"]["label"] == "Test Peer Registry"
            assert peer_node["data"]["enabled"] is True
            assert peer_node["data"]["status"] == "healthy"
            assert peer_node["data"]["serversCount"] == 10
            assert peer_node["data"]["agentsCount"] == 5

            # Verify edge
            edge = data["edges"][0]
            assert edge["source"] == "test-peer-1"
            assert edge["target"] == "this-registry"
            assert edge["animated"] is True  # Healthy status
            assert edge["data"]["status"] == "healthy"

    def test_no_edge_for_disabled_peers(
        self,
        mock_admin_auth,
        sample_peer_config_disabled,
        sample_sync_status_unhealthy,
    ):
        """Test topology does not create edges for disabled peers."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.list_peers = AsyncMock(return_value=[sample_peer_config_disabled])
            mock_service_instance.get_sync_status = AsyncMock(return_value=sample_sync_status_unhealthy)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers/topology")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert len(data["nodes"]) == 2  # "this registry" + 1 peer
            assert len(data["edges"]) == 0  # No edge for disabled peer

            # Verify peer node shows disabled status
            peer_node = next(
                n for n in data["nodes"] if n["id"] == "test-peer-2"
            )
            assert peer_node["data"]["enabled"] is False
            assert peer_node["data"]["status"] == "disabled"

    def test_node_positions_are_circular_layout(
        self,
        mock_admin_auth,
    ):
        """Test that multiple peers are positioned in a circular layout."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        # Create 4 peers
        peers = [
            PeerRegistryConfig(
                peer_id=f"peer-{i}",
                name=f"Peer {i}",
                endpoint=f"https://peer{i}.example.com",
                enabled=True,
                sync_mode="all",
                sync_interval_minutes=60,
            )
            for i in range(4)
        ]

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.list_peers = AsyncMock(return_value=peers)
            mock_service_instance.get_sync_status = AsyncMock(return_value=None)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers/topology")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Get peer node positions (exclude "this registry")
            peer_nodes = [n for n in data["nodes"] if n["id"] != "this-registry"]

            # Verify all positions are within expected radius from center
            center_x, center_y = 400, 300
            radius = 200
            tolerance = 1.0  # Allow for floating point rounding

            for node in peer_nodes:
                x = node["position"]["x"]
                y = node["position"]["y"]
                distance = math.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
                assert abs(distance - radius) < tolerance, (
                    f"Node {node['id']} at ({x}, {y}) is {distance:.2f} from center, "
                    f"expected ~{radius}"
                )

    def test_handles_null_sync_status_gracefully(
        self,
        mock_admin_auth,
        sample_peer_config,
    ):
        """Test topology handles peers with no sync status."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.list_peers = AsyncMock(return_value=[sample_peer_config])
            mock_service_instance.get_sync_status = AsyncMock(return_value=None)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers/topology")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            peer_node = next(
                n for n in data["nodes"] if n["id"] == "test-peer-1"
            )
            assert peer_node["data"]["status"] == "unknown"
            assert peer_node["data"]["serversCount"] == 0
            assert peer_node["data"]["agentsCount"] == 0
            assert peer_node["data"]["lastSync"] is None

    def test_edge_animated_only_for_healthy_peers(
        self,
        mock_admin_auth,
    ):
        """Test that edge animation is only enabled for healthy peers."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        healthy_peer = PeerRegistryConfig(
            peer_id="healthy-peer",
            name="Healthy Peer",
            endpoint="https://healthy.example.com",
            enabled=True,
            sync_mode="all",
            sync_interval_minutes=60,
        )
        unhealthy_peer = PeerRegistryConfig(
            peer_id="unhealthy-peer",
            name="Unhealthy Peer",
            endpoint="https://unhealthy.example.com",
            enabled=True,
            sync_mode="all",
            sync_interval_minutes=60,
        )

        healthy_status = PeerSyncStatus(
            peer_id="healthy-peer",
            is_healthy=True,
            total_servers_synced=5,
            total_agents_synced=2,
        )
        unhealthy_status = PeerSyncStatus(
            peer_id="unhealthy-peer",
            is_healthy=False,
            total_servers_synced=0,
            total_agents_synced=0,
        )

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.list_peers = AsyncMock(return_value=[healthy_peer, unhealthy_peer])

            def get_status_side_effect(peer_id):
                if peer_id == "healthy-peer":
                    return healthy_status
                return unhealthy_status

            mock_service_instance.get_sync_status = AsyncMock(side_effect=get_status_side_effect)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers/topology")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Find edges
            healthy_edge = next(
                e for e in data["edges"] if e["source"] == "healthy-peer"
            )
            unhealthy_edge = next(
                e for e in data["edges"] if e["source"] == "unhealthy-peer"
            )

            assert healthy_edge["animated"] is True
            assert unhealthy_edge["animated"] is False


class TestListPeers:
    """Tests for GET /api/v1/peers endpoint."""

    def test_returns_all_peers(
        self,
        mock_admin_auth,
        sample_peer_config,
        sample_peer_config_disabled,
    ):
        """Test listing all peers without filter."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.list_peers = AsyncMock(return_value=[
                sample_peer_config,
                sample_peer_config_disabled,
            ])
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert len(data) == 2

    def test_filters_enabled_peers(
        self,
        mock_admin_auth,
        sample_peer_config,
    ):
        """Test listing only enabled peers."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.list_peers = AsyncMock(return_value=[sample_peer_config])
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers?enabled=true")

            assert response.status_code == status.HTTP_200_OK
            mock_service_instance.list_peers.assert_called_once_with(enabled=True)


class TestSyncOperations:
    """Tests for sync endpoints."""

    def test_sync_all_peers(
        self,
        mock_admin_auth,
    ):
        """Test syncing all enabled peers."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        sync_result = SyncResult(
            success=True,
            peer_id="test-peer-1",
            servers_synced=10,
            agents_synced=5,
        )

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.sync_all_peers = AsyncMock(return_value={
                "test-peer-1": sync_result,
            })
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.post("/api/v1/peers/sync")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "test-peer-1" in data
            assert data["test-peer-1"]["success"] is True

    def test_sync_single_peer(
        self,
        mock_admin_auth,
    ):
        """Test syncing a single peer."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        sync_result = SyncResult(
            success=True,
            peer_id="test-peer-1",
            servers_synced=10,
            agents_synced=5,
        )

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.sync_peer = AsyncMock(return_value=sync_result)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.post("/api/v1/peers/test-peer-1/sync")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["servers_synced"] == 10

    def test_sync_peer_not_found(
        self,
        mock_admin_auth,
    ):
        """Test syncing non-existent peer returns 404."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.sync_peer = AsyncMock(side_effect=ValueError(
                "Peer not found: nonexistent-peer"
            ))
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.post("/api/v1/peers/nonexistent-peer/sync")

            assert response.status_code == status.HTTP_404_NOT_FOUND


class TestPeerCRUD:
    """Tests for peer CRUD operations."""

    def test_create_peer(
        self,
        mock_admin_auth,
        sample_peer_config,
    ):
        """Test creating a new peer."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.add_peer = AsyncMock(return_value=sample_peer_config)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.post(
                "/api/v1/peers",
                json=sample_peer_config.model_dump(mode="json"),
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["peer_id"] == "test-peer-1"

    def test_create_peer_conflict(
        self,
        mock_admin_auth,
        sample_peer_config,
    ):
        """Test creating duplicate peer returns 409."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.add_peer = AsyncMock(side_effect=ValueError(
                "Peer already exists: test-peer-1"
            ))
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.post(
                "/api/v1/peers",
                json=sample_peer_config.model_dump(mode="json"),
            )

            assert response.status_code == status.HTTP_409_CONFLICT

    def test_get_peer(
        self,
        mock_admin_auth,
        sample_peer_config,
    ):
        """Test getting a peer by ID."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.get_peer = AsyncMock(return_value=sample_peer_config)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers/test-peer-1")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["peer_id"] == "test-peer-1"

    def test_get_peer_not_found(
        self,
        mock_admin_auth,
    ):
        """Test getting non-existent peer returns 404."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.get_peer = AsyncMock(side_effect=ValueError(
                "Peer not found: nonexistent-peer"
            ))
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.get("/api/v1/peers/nonexistent-peer")

            assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_peer(
        self,
        mock_admin_auth,
    ):
        """Test deleting a peer."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.remove_peer = AsyncMock(return_value=True)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.delete("/api/v1/peers/test-peer-1")

            assert response.status_code == status.HTTP_204_NO_CONTENT
            mock_service_instance.remove_peer.assert_called_once_with("test-peer-1")

    def test_enable_peer(
        self,
        mock_admin_auth,
        sample_peer_config,
    ):
        """Test enabling a peer."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        enabled_peer = sample_peer_config.model_copy(update={"enabled": True})

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.update_peer = AsyncMock(return_value=enabled_peer)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.post("/api/v1/peers/test-peer-1/enable")

            assert response.status_code == status.HTTP_200_OK
            mock_service_instance.update_peer.assert_called_once_with(
                "test-peer-1", {"enabled": True}
            )

    def test_disable_peer(
        self,
        mock_admin_auth,
        sample_peer_config,
    ):
        """Test disabling a peer."""
        app.dependency_overrides[enhanced_auth] = lambda: mock_admin_auth

        disabled_peer = sample_peer_config.model_copy(update={"enabled": False})

        with patch(
            "registry.api.peer_management_routes.get_peer_federation_service"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.update_peer = AsyncMock(return_value=disabled_peer)
            mock_service.return_value = mock_service_instance

            client = TestClient(app)
            response = client.post("/api/v1/peers/test-peer-1/disable")

            assert response.status_code == status.HTTP_200_OK
            mock_service_instance.update_peer.assert_called_once_with(
                "test-peer-1", {"enabled": False}
            )
