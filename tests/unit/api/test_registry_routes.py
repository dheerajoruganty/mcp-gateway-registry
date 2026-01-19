"""
Unit tests for registry.api.registry_routes module.

Tests Anthropic MCP Registry API endpoints.
"""

import logging
from typing import Any
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry.auth.dependencies import nginx_proxied_auth


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def admin_user_context() -> dict[str, Any]:
    """Create admin user context."""
    return {
        "username": "admin",
        "is_admin": True,
        "groups": ["mcp-registry-admin"],
        "scopes": ["admin:all"],
        "auth_method": "session",
        "accessible_servers": [],
        "accessible_services": [],
    }


@pytest.fixture
def regular_user_context() -> dict[str, Any]:
    """Create regular (non-admin) user context."""
    return {
        "username": "testuser",
        "is_admin": False,
        "groups": ["test-group"],
        "scopes": ["test-server/read"],
        "auth_method": "session",
        "accessible_servers": ["test-server"],
        "accessible_services": ["test-server"],
    }


@pytest.fixture
def mock_server_info():
    """Create mock server info."""
    return {
        "server_name": "test-server",
        "name": "Test Server",
        "path": "/test-server/",
        "proxy_pass_url": "http://localhost:8080",
        "description": "A test server",
        "enabled": True,
        "headers": [],
    }


@pytest.fixture
def mock_server_service():
    """Create mock server service."""
    mock = MagicMock()
    mock.get_all_servers = AsyncMock(return_value={})
    mock.get_all_servers_with_permissions = AsyncMock(return_value={})
    mock.get_server_info = AsyncMock(return_value=None)
    mock.is_service_enabled = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_health_service():
    """Create mock health service."""
    mock = MagicMock()
    mock._get_service_health_data.return_value = {
        "status": "healthy",
        "last_checked_iso": "2024-01-01T00:00:00Z"
    }
    return mock


@pytest.fixture
def test_app_admin(admin_user_context, mock_server_service, mock_health_service):
    """Create test app with admin auth and mocked services."""
    with patch("registry.api.registry_routes.server_service", mock_server_service):
        with patch("registry.api.registry_routes.health_service", mock_health_service):
            # Import router AFTER patching so it uses mocked services
            from registry.api.registry_routes import router

            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[nginx_proxied_auth] = lambda: admin_user_context

            # Store mocks on the client for test access
            client = TestClient(app)
            client.mock_server_service = mock_server_service
            client.mock_health_service = mock_health_service

            yield client
            app.dependency_overrides.clear()


@pytest.fixture
def test_app_regular(regular_user_context, mock_server_service, mock_health_service):
    """Create test app with regular user auth and mocked services."""
    with patch("registry.api.registry_routes.server_service", mock_server_service):
        with patch("registry.api.registry_routes.health_service", mock_health_service):
            from registry.api.registry_routes import router

            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[nginx_proxied_auth] = lambda: regular_user_context

            client = TestClient(app)
            client.mock_server_service = mock_server_service
            client.mock_health_service = mock_health_service

            yield client
            app.dependency_overrides.clear()


# =============================================================================
# TEST: List Servers
# =============================================================================


@pytest.mark.unit
class TestListServers:
    """Tests for the list servers endpoint."""

    def test_list_servers_admin_success(self, test_app_admin, mock_server_info):
        """Test admin can list all servers."""
        test_app_admin.mock_server_service.get_all_servers = AsyncMock(return_value={
            "/test-server/": mock_server_info
        })

        response = test_app_admin.get("/v0.1/servers")

        assert response.status_code == 200
        data = response.json()
        assert "servers" in data
        assert "metadata" in data

    def test_list_servers_with_pagination(self, test_app_admin, mock_server_info):
        """Test server listing with pagination."""
        test_app_admin.mock_server_service.get_all_servers = AsyncMock(return_value={
            "/test-server/": mock_server_info
        })

        response = test_app_admin.get("/v0.1/servers?limit=10")

        assert response.status_code == 200

    def test_list_servers_regular_user(self, test_app_regular, mock_server_info):
        """Test regular user sees only accessible servers."""
        test_app_regular.mock_server_service.get_all_servers_with_permissions = AsyncMock(return_value={
            "/test-server/": mock_server_info
        })

        response = test_app_regular.get("/v0.1/servers")

        assert response.status_code == 200

    def test_list_servers_empty(self, test_app_admin):
        """Test listing servers when none exist."""
        test_app_admin.mock_server_service.get_all_servers = AsyncMock(return_value={})

        response = test_app_admin.get("/v0.1/servers")

        assert response.status_code == 200
        data = response.json()
        assert data["servers"] == []


# =============================================================================
# TEST: List Server Versions
# =============================================================================


@pytest.mark.unit
class TestListServerVersions:
    """Tests for the list server versions endpoint."""

    def test_list_versions_invalid_name_format(self, test_app_admin):
        """Test listing versions with invalid server name format."""
        # Server name doesn't start with expected prefix
        server_name = "invalid-name"

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions")

        assert response.status_code == 404

    def test_list_versions_server_not_found(self, test_app_admin):
        """Test listing versions for non-existent server."""
        server_name = "io.mcpgateway/nonexistent"

        # Mock returns None for server lookup
        test_app_admin.mock_server_service.get_server_info = AsyncMock(return_value=None)

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions")

        assert response.status_code == 404

    def test_list_versions_success(self, test_app_admin, mock_server_info):
        """Test listing versions for a server."""
        server_name = "io.mcpgateway/test-server"

        # Mock returns server info
        test_app_admin.mock_server_service.get_server_info = AsyncMock(return_value=mock_server_info)

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions")

        assert response.status_code == 200
        data = response.json()
        assert "servers" in data

    def test_list_versions_unauthorized_user(self, test_app_regular, mock_server_info):
        """Test regular user cannot access unauthorized server versions."""
        # Server name that user doesn't have access to
        server_name = "io.mcpgateway/unauthorized-server"

        # Create a modified server info for unauthorized server
        unauthorized_server_info = mock_server_info.copy()
        unauthorized_server_info["server_name"] = "unauthorized-server"

        test_app_regular.mock_server_service.get_server_info = AsyncMock(
            return_value=unauthorized_server_info
        )

        response = test_app_regular.get(f"/v0.1/servers/{server_name}/versions")

        assert response.status_code == 404


# =============================================================================
# TEST: Get Server Version
# =============================================================================


@pytest.mark.unit
class TestGetServerVersion:
    """Tests for the get server version endpoint."""

    def test_get_version_invalid_name(self, test_app_admin):
        """Test getting version with invalid server name."""
        server_name = "invalid-name"
        version = "latest"

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions/{version}")

        assert response.status_code == 404

    def test_get_version_not_found(self, test_app_admin):
        """Test getting version for non-existent server."""
        server_name = "io.mcpgateway/nonexistent"
        version = "latest"

        test_app_admin.mock_server_service.get_server_info = AsyncMock(return_value=None)

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions/{version}")

        assert response.status_code == 404

    def test_get_version_success(self, test_app_admin, mock_server_info):
        """Test getting a specific server version."""
        server_name = "io.mcpgateway/test-server"
        version = "latest"

        test_app_admin.mock_server_service.get_server_info = AsyncMock(return_value=mock_server_info)

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions/{version}")

        assert response.status_code == 200
        data = response.json()
        assert "server" in data

    def test_get_version_1_0_0(self, test_app_admin, mock_server_info):
        """Test getting version 1.0.0."""
        server_name = "io.mcpgateway/test-server"
        version = "1.0.0"

        test_app_admin.mock_server_service.get_server_info = AsyncMock(return_value=mock_server_info)

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions/{version}")

        assert response.status_code == 200

    def test_get_version_unsupported_version(self, test_app_admin, mock_server_info):
        """Test getting unsupported version."""
        server_name = "io.mcpgateway/test-server"
        version = "2.0.0"  # Unsupported version

        test_app_admin.mock_server_service.get_server_info = AsyncMock(return_value=mock_server_info)

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions/{version}")

        assert response.status_code == 404
        assert "2.0.0" in response.json()["detail"]

    def test_get_version_unauthorized(self, test_app_regular, mock_server_info):
        """Test regular user cannot get unauthorized server version."""
        server_name = "io.mcpgateway/unauthorized-server"
        version = "latest"

        unauthorized_server_info = mock_server_info.copy()
        unauthorized_server_info["server_name"] = "unauthorized-server"

        test_app_regular.mock_server_service.get_server_info = AsyncMock(
            return_value=unauthorized_server_info
        )

        response = test_app_regular.get(f"/v0.1/servers/{server_name}/versions/{version}")

        assert response.status_code == 404

    def test_get_version_with_trailing_slash(self, test_app_admin, mock_server_info):
        """Test getting version when first lookup fails but trailing slash works."""
        server_name = "io.mcpgateway/test-server"
        version = "latest"

        # First call returns None, second call with trailing slash returns server
        test_app_admin.mock_server_service.get_server_info = AsyncMock(
            side_effect=[None, mock_server_info]
        )

        response = test_app_admin.get(f"/v0.1/servers/{server_name}/versions/{version}")

        assert response.status_code == 200
