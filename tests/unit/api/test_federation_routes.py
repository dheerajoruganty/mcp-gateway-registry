"""
Unit tests for registry.api.federation_routes module.

This module tests the federation configuration API endpoints.
"""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry.api.federation_routes import router, nginx_proxied_auth
from registry.schemas.federation_schema import (
    FederationConfig,
    AnthropicFederationConfig,
    AsorFederationConfig,
)
from registry.schemas.federation_topology_schema import (
    UnifiedTopologyResponse,
    UnifiedFederationNode,
    FederationEdge,
    TopologyMetadata,
    FederationSourceType,
)


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_user_context() -> dict[str, Any]:
    """Create mock user context."""
    return {
        "username": "testuser",
        "groups": ["mcp-registry-admin"],
        "scopes": ["admin:all"],
        "auth_method": "session",
        "provider": "local",
        "accessible_servers": ["all"],
        "accessible_services": ["all"],
        "accessible_agents": ["all"],
        "ui_permissions": {
            "publish_agent": ["all"],
            "toggle_service": ["all"],
            "modify_service": ["all"],
        },
        "can_modify_servers": True,
        "is_admin": True,
    }


@pytest.fixture
def test_app(mock_user_context):
    """Create a test FastAPI application with federation routes."""
    app = FastAPI()
    app.include_router(router)

    # Override auth dependency
    app.dependency_overrides[nginx_proxied_auth] = lambda: mock_user_context

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture
def mock_federation_config():
    """Create mock federation configuration."""
    return FederationConfig(
        anthropic=AnthropicFederationConfig(enabled=True),
        asor=AsorFederationConfig(enabled=True),
    )


@pytest.fixture
def mock_disabled_config():
    """Create mock federation config with sources disabled."""
    return FederationConfig(
        anthropic=AnthropicFederationConfig(enabled=False),
        asor=AsorFederationConfig(enabled=False),
    )


@pytest.fixture
def mock_topology_response():
    """Create mock topology response."""
    return UnifiedTopologyResponse(
        nodes=[
            UnifiedFederationNode(
                id="this-registry",
                name="Local Registry",
                type=FederationSourceType.LOCAL,
                status="healthy",
                servers_count=5,
                agents_count=3,
            ),
        ],
        edges=[],
        metadata=TopologyMetadata(
            total_sources=1,
            enabled_sources=1,
            total_servers=5,
            total_agents=3,
        ),
    )


# =============================================================================
# TEST: GET /federation/unified-topology
# =============================================================================


@pytest.mark.unit
class TestGetUnifiedTopology:
    """Tests for the unified topology endpoint."""

    def test_get_unified_topology_success(self, test_app, mock_topology_response):
        """Test successful topology retrieval."""
        with patch("registry.api.federation_routes.get_federation_service") as mock_service:
            mock_service.return_value.get_unified_topology = AsyncMock(
                return_value=mock_topology_response
            )

            response = test_app.get("/federation/unified-topology")

        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert "metadata" in data

    def test_get_unified_topology_with_nodes(self, test_app, mock_topology_response):
        """Test topology includes expected nodes."""
        with patch("registry.api.federation_routes.get_federation_service") as mock_service:
            mock_service.return_value.get_unified_topology = AsyncMock(
                return_value=mock_topology_response
            )

            response = test_app.get("/federation/unified-topology")

        data = response.json()
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "this-registry"
        assert data["nodes"][0]["type"] == "local"


# =============================================================================
# TEST: POST /federation/anthropic/sync
# =============================================================================


@pytest.mark.unit
class TestSyncAnthropic:
    """Tests for the Anthropic sync endpoint."""

    def test_sync_anthropic_config_not_found(self, test_app):
        """Test sync fails when config not found."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post("/federation/anthropic/sync")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_sync_anthropic_not_enabled(self, test_app, mock_disabled_config):
        """Test sync fails when Anthropic is not enabled."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=mock_disabled_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post("/federation/anthropic/sync")

        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"]


# =============================================================================
# TEST: POST /federation/asor/sync
# =============================================================================


@pytest.mark.unit
class TestSyncAsor:
    """Tests for the ASOR sync endpoint."""

    def test_sync_asor_config_not_found(self, test_app):
        """Test sync fails when config not found."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post("/federation/asor/sync")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_sync_asor_not_enabled(self, test_app, mock_disabled_config):
        """Test sync fails when ASOR is not enabled."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=mock_disabled_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post("/federation/asor/sync")

        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"]


# =============================================================================
# TEST: GET /federation/config
# =============================================================================


@pytest.mark.unit
class TestGetFederationConfig:
    """Tests for the get federation config endpoint."""

    def test_get_config_success(self, test_app, mock_federation_config):
        """Test successful config retrieval."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=mock_federation_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.get("/federation/config")

        assert response.status_code == 200
        data = response.json()
        assert "anthropic" in data
        assert "asor" in data

    def test_get_config_not_found(self, test_app):
        """Test returns 404 when config not found."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.get("/federation/config")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


# =============================================================================
# TEST: POST /federation/config
# =============================================================================


@pytest.mark.unit
class TestSaveFederationConfig:
    """Tests for the save federation config endpoint."""

    def test_save_config_success(self, test_app, mock_federation_config):
        """Test successful config save."""
        mock_repo = AsyncMock()
        mock_repo.save_config = AsyncMock(return_value=mock_federation_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post(
                "/federation/config",
                json=mock_federation_config.model_dump(),
            )

        assert response.status_code == 201
        assert "message" in response.json()
        mock_repo.save_config.assert_called_once()

    def test_save_config_error(self, test_app, mock_federation_config):
        """Test config save error handling."""
        mock_repo = AsyncMock()
        mock_repo.save_config = AsyncMock(side_effect=Exception("DB Error"))

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post(
                "/federation/config",
                json=mock_federation_config.model_dump(),
            )

        assert response.status_code == 500


# =============================================================================
# TEST: PUT /federation/config/{config_id}
# =============================================================================


@pytest.mark.unit
class TestUpdateFederationConfig:
    """Tests for the update federation config endpoint."""

    def test_update_config_success(self, test_app, mock_federation_config):
        """Test successful config update."""
        mock_repo = AsyncMock()
        mock_repo.save_config = AsyncMock(return_value=mock_federation_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.put(
                "/federation/config/default",
                json=mock_federation_config.model_dump(),
            )

        assert response.status_code == 200
        assert "message" in response.json()
        mock_repo.save_config.assert_called_once()

    def test_update_config_error(self, test_app, mock_federation_config):
        """Test config update error handling."""
        mock_repo = AsyncMock()
        mock_repo.save_config = AsyncMock(side_effect=Exception("DB Error"))

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.put(
                "/federation/config/default",
                json=mock_federation_config.model_dump(),
            )

        assert response.status_code == 500


# =============================================================================
# TEST: DELETE /federation/config/{config_id}
# =============================================================================


@pytest.mark.unit
class TestDeleteFederationConfig:
    """Tests for the delete federation config endpoint."""

    def test_delete_config_success(self, test_app):
        """Test successful config deletion."""
        mock_repo = AsyncMock()
        mock_repo.delete_config = AsyncMock(return_value=True)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.delete("/federation/config/default")

        assert response.status_code == 200
        assert "message" in response.json()

    def test_delete_config_not_found(self, test_app):
        """Test delete fails when config not found."""
        mock_repo = AsyncMock()
        mock_repo.delete_config = AsyncMock(return_value=False)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.delete("/federation/config/nonexistent")

        assert response.status_code == 404


# =============================================================================
# TEST: GET /federation/configs
# =============================================================================


@pytest.mark.unit
class TestListFederationConfigs:
    """Tests for the list federation configs endpoint."""

    def test_list_configs_success(self, test_app):
        """Test successful configs listing."""
        mock_repo = AsyncMock()
        mock_repo.list_configs = AsyncMock(return_value=[
            {"config_id": "default", "created_at": "2024-01-01T00:00:00Z"},
            {"config_id": "custom", "created_at": "2024-01-02T00:00:00Z"},
        ])

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.get("/federation/configs")

        assert response.status_code == 200
        data = response.json()
        assert "configs" in data
        assert "total" in data
        assert data["total"] == 2

    def test_list_configs_empty(self, test_app):
        """Test listing when no configs exist."""
        mock_repo = AsyncMock()
        mock_repo.list_configs = AsyncMock(return_value=[])

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.get("/federation/configs")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


# =============================================================================
# TEST: PUT /federation/anthropic/config
# =============================================================================


@pytest.mark.unit
class TestUpdateAnthropicConfig:
    """Tests for the Anthropic config update endpoint."""

    def test_update_anthropic_config_success(self, test_app, mock_federation_config):
        """Test successful Anthropic config update."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=mock_federation_config)
        mock_repo.save_config = AsyncMock(return_value=mock_federation_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.put(
                "/federation/anthropic/config",
                json={"enabled": True, "endpoint": "https://new.endpoint.com"},
            )

        assert response.status_code == 200
        assert "message" in response.json()

    def test_update_anthropic_config_creates_default(self, test_app, mock_federation_config):
        """Test creates default config if not exists."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)
        mock_repo.save_config = AsyncMock(return_value=mock_federation_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.put(
                "/federation/anthropic/config",
                json={"enabled": True},
            )

        assert response.status_code == 200


# =============================================================================
# TEST: PUT /federation/asor/config
# =============================================================================


@pytest.mark.unit
class TestUpdateAsorConfig:
    """Tests for the ASOR config update endpoint."""

    def test_update_asor_config_success(self, test_app, mock_federation_config):
        """Test successful ASOR config update."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=mock_federation_config)
        mock_repo.save_config = AsyncMock(return_value=mock_federation_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.put(
                "/federation/asor/config",
                json={"enabled": True, "endpoint": "https://asor.endpoint.com"},
            )

        assert response.status_code == 200
        assert "message" in response.json()


# =============================================================================
# TEST: POST /federation/sync
# =============================================================================


@pytest.mark.unit
class TestSyncFederation:
    """Tests for the federation sync endpoint."""

    def test_sync_federation_config_not_found(self, test_app):
        """Test sync fails when config not found."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post("/federation/sync")

        assert response.status_code == 404


# =============================================================================
# TEST: POST /federation/config/{config_id}/anthropic/servers
# =============================================================================


@pytest.mark.unit
class TestAddAnthropicServer:
    """Tests for the add Anthropic server endpoint."""

    def test_add_anthropic_server_config_not_found(self, test_app):
        """Test add server fails when config not found."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post(
                "/federation/config/default/anthropic/servers?server_name=test-server"
            )

        assert response.status_code == 404

    def test_add_anthropic_server_success(self, test_app, mock_federation_config):
        """Test successful server addition."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=mock_federation_config)
        mock_repo.save_config = AsyncMock(return_value=mock_federation_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post(
                "/federation/config/default/anthropic/servers?server_name=test-server"
            )

        assert response.status_code == 200


# =============================================================================
# TEST: DELETE /federation/config/{config_id}/anthropic/servers/{server_name}
# =============================================================================


@pytest.mark.unit
class TestRemoveAnthropicServer:
    """Tests for the remove Anthropic server endpoint."""

    def test_remove_anthropic_server_config_not_found(self, test_app):
        """Test remove server fails when config not found."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.delete(
                "/federation/config/default/anthropic/servers/test-server"
            )

        assert response.status_code == 404


# =============================================================================
# TEST: POST /federation/config/{config_id}/asor/agents
# =============================================================================


@pytest.mark.unit
class TestAddAsorAgent:
    """Tests for the add ASOR agent endpoint."""

    def test_add_asor_agent_config_not_found(self, test_app):
        """Test add agent fails when config not found."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post(
                "/federation/config/default/asor/agents?agent_id=test-agent"
            )

        assert response.status_code == 404

    def test_add_asor_agent_success(self, test_app, mock_federation_config):
        """Test successful agent addition."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=mock_federation_config)
        mock_repo.save_config = AsyncMock(return_value=mock_federation_config)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.post(
                "/federation/config/default/asor/agents?agent_id=test-agent"
            )

        assert response.status_code == 200


# =============================================================================
# TEST: DELETE /federation/config/{config_id}/asor/agents/{agent_id}
# =============================================================================


@pytest.mark.unit
class TestRemoveAsorAgent:
    """Tests for the remove ASOR agent endpoint."""

    def test_remove_asor_agent_config_not_found(self, test_app):
        """Test remove agent fails when config not found."""
        mock_repo = AsyncMock()
        mock_repo.get_config = AsyncMock(return_value=None)

        with patch("registry.api.federation_routes.get_federation_config_repository", return_value=mock_repo):
            response = test_app.delete(
                "/federation/config/default/asor/agents/test-agent"
            )

        assert response.status_code == 404
