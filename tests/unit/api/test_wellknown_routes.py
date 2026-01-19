"""
Unit tests for registry.api.wellknown_routes module.

Tests the well-known discovery endpoint for MCP servers.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_server_service():
    """Create mock server service."""
    service = MagicMock()
    service.get_all_servers = AsyncMock()
    service.is_service_enabled = AsyncMock()
    return service


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    mock = MagicMock()
    mock.enable_wellknown_discovery = True
    mock.wellknown_cache_ttl = 300
    return mock


@pytest.fixture
def test_app_with_discovery_enabled(mock_server_service, mock_settings):
    """Create test app with discovery enabled."""
    with patch("registry.api.wellknown_routes.server_service", mock_server_service):
        with patch("registry.api.wellknown_routes.settings", mock_settings):
            from registry.api.wellknown_routes import router

            app = FastAPI()
            app.include_router(router, prefix="/.well-known")

            client = TestClient(app)
            client.mock_server_service = mock_server_service
            yield client


@pytest.fixture
def test_app_with_discovery_disabled(mock_server_service, mock_settings):
    """Create test app with discovery disabled."""
    mock_settings.enable_wellknown_discovery = False

    with patch("registry.api.wellknown_routes.server_service", mock_server_service):
        with patch("registry.api.wellknown_routes.settings", mock_settings):
            from registry.api.wellknown_routes import router

            app = FastAPI()
            app.include_router(router, prefix="/.well-known")

            client = TestClient(app)
            yield client


# =============================================================================
# TEST: get_wellknown_mcp_servers
# =============================================================================


@pytest.mark.unit
class TestGetWellknownMcpServers:
    """Tests for the get_wellknown_mcp_servers endpoint."""

    def test_discovery_disabled_returns_404(self, test_app_with_discovery_disabled):
        """Test that discovery returns 404 when disabled."""
        response = test_app_with_discovery_disabled.get("/.well-known/mcp-servers")

        assert response.status_code == 404
        assert "disabled" in response.json()["detail"].lower()

    def test_discovery_returns_empty_servers(self, test_app_with_discovery_enabled):
        """Test discovery returns empty list when no servers."""
        client = test_app_with_discovery_enabled
        client.mock_server_service.get_all_servers.return_value = {}

        response = client.get("/.well-known/mcp-servers")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "1.0"
        assert data["servers"] == []
        assert "registry" in data

    def test_discovery_returns_enabled_servers(self, test_app_with_discovery_enabled):
        """Test discovery returns enabled servers."""
        client = test_app_with_discovery_enabled
        client.mock_server_service.get_all_servers.return_value = {
            "/server1": {
                "path": "/server1",
                "server_name": "Test Server",
                "description": "A test server"
            }
        }
        client.mock_server_service.is_service_enabled.return_value = True

        response = client.get("/.well-known/mcp-servers")

        assert response.status_code == 200
        data = response.json()
        assert len(data["servers"]) == 1
        assert data["servers"][0]["name"] == "Test Server"

    def test_discovery_filters_disabled_servers(self, test_app_with_discovery_enabled):
        """Test that disabled servers are filtered out."""
        client = test_app_with_discovery_enabled
        client.mock_server_service.get_all_servers.return_value = {
            "/enabled": {"path": "/enabled", "server_name": "Enabled"},
            "/disabled": {"path": "/disabled", "server_name": "Disabled"}
        }

        async def mock_is_enabled(path):
            return path == "/enabled"

        client.mock_server_service.is_service_enabled.side_effect = mock_is_enabled

        response = client.get("/.well-known/mcp-servers")

        assert response.status_code == 200
        data = response.json()
        assert len(data["servers"]) == 1
        assert data["servers"][0]["name"] == "Enabled"

    def test_discovery_includes_cache_headers(self, test_app_with_discovery_enabled):
        """Test that response includes cache control headers."""
        client = test_app_with_discovery_enabled
        client.mock_server_service.get_all_servers.return_value = {}

        response = client.get("/.well-known/mcp-servers")

        assert response.status_code == 200
        assert "Cache-Control" in response.headers
        assert "max-age=300" in response.headers["Cache-Control"]

    def test_discovery_includes_registry_info(self, test_app_with_discovery_enabled):
        """Test that response includes registry information."""
        client = test_app_with_discovery_enabled
        client.mock_server_service.get_all_servers.return_value = {}

        response = client.get("/.well-known/mcp-servers")

        assert response.status_code == 200
        data = response.json()
        assert data["registry"]["name"] == "Enterprise MCP Gateway"
        assert "description" in data["registry"]
        assert "contact" in data["registry"]


# =============================================================================
# TEST: _format_server_discovery
# =============================================================================


@pytest.mark.unit
class TestFormatServerDiscovery:
    """Tests for the _format_server_discovery function."""

    def test_format_basic_server(self):
        """Test formatting a basic server."""
        with patch("registry.api.wellknown_routes.settings") as mock_settings:
            mock_settings.enable_wellknown_discovery = True

            from registry.api.wellknown_routes import _format_server_discovery

            mock_request = MagicMock()
            mock_request.headers = {"host": "example.com"}
            mock_request.url.scheme = "https"

            server_info = {
                "path": "/test-server",
                "server_name": "Test Server",
                "description": "A test server"
            }

            result = _format_server_discovery(server_info, mock_request)

            assert result["name"] == "Test Server"
            assert result["description"] == "A test server"
            assert "url" in result
            assert result["transport"] == "streamable-http"
            assert "authentication" in result
            assert result["capabilities"] == ["tools", "resources"]

    def test_format_server_with_custom_transport(self):
        """Test formatting server with custom transport."""
        with patch("registry.api.wellknown_routes.settings") as mock_settings:
            mock_settings.enable_wellknown_discovery = True

            from registry.api.wellknown_routes import _format_server_discovery

            mock_request = MagicMock()
            mock_request.headers = {"host": "example.com"}
            mock_request.url.scheme = "https"

            server_info = {
                "path": "/sse-server",
                "server_name": "SSE Server",
                "transport": "sse"
            }

            result = _format_server_discovery(server_info, mock_request)

            assert result["transport"] == "sse"

    def test_format_server_with_tools(self):
        """Test formatting server with tools preview."""
        with patch("registry.api.wellknown_routes.settings") as mock_settings:
            mock_settings.enable_wellknown_discovery = True

            from registry.api.wellknown_routes import _format_server_discovery

            mock_request = MagicMock()
            mock_request.headers = {"host": "example.com"}
            mock_request.url.scheme = "https"

            server_info = {
                "path": "/tools-server",
                "server_name": "Tools Server",
                "tool_list": [
                    {"name": "tool1", "description": "First tool"},
                    {"name": "tool2", "description": "Second tool"}
                ]
            }

            result = _format_server_discovery(server_info, mock_request)

            assert len(result["tools_preview"]) == 2
            assert result["tools_preview"][0]["name"] == "tool1"


# =============================================================================
# TEST: _get_server_url
# =============================================================================


@pytest.mark.unit
class TestGetServerUrl:
    """Tests for the _get_server_url function."""

    def test_get_url_with_host_header(self):
        """Test URL generation with host header."""
        from registry.api.wellknown_routes import _get_server_url

        mock_request = MagicMock()
        mock_request.headers = {"host": "api.example.com"}
        mock_request.url.scheme = "https"

        result = _get_server_url("/test-server/", mock_request)

        assert result == "https://api.example.com/test-server/mcp"

    def test_get_url_with_forwarded_proto(self):
        """Test URL generation with X-Forwarded-Proto header."""
        from registry.api.wellknown_routes import _get_server_url

        mock_request = MagicMock()
        mock_request.headers = {
            "host": "api.example.com",
            "x-forwarded-proto": "https"
        }
        mock_request.url.scheme = "http"

        result = _get_server_url("/test-server", mock_request)

        # Should use X-Forwarded-Proto over scheme
        assert result.startswith("https://")

    def test_get_url_default_host(self):
        """Test URL generation with default host."""
        from registry.api.wellknown_routes import _get_server_url

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.url.scheme = "http"

        result = _get_server_url("/test-server", mock_request)

        assert "localhost:7860" in result

    def test_get_url_strips_slashes(self):
        """Test URL generation strips leading/trailing slashes from path."""
        from registry.api.wellknown_routes import _get_server_url

        mock_request = MagicMock()
        mock_request.headers = {"host": "api.example.com"}
        mock_request.url.scheme = "https"

        result = _get_server_url("///test-server///", mock_request)

        assert result == "https://api.example.com/test-server/mcp"


# =============================================================================
# TEST: _get_transport_type
# =============================================================================


@pytest.mark.unit
class TestGetTransportType:
    """Tests for the _get_transport_type function."""

    def test_get_default_transport(self):
        """Test default transport type."""
        from registry.api.wellknown_routes import _get_transport_type

        result = _get_transport_type({})

        assert result == "streamable-http"

    def test_get_custom_transport(self):
        """Test custom transport type."""
        from registry.api.wellknown_routes import _get_transport_type

        result = _get_transport_type({"transport": "sse"})

        assert result == "sse"

    def test_get_stdio_transport(self):
        """Test stdio transport type."""
        from registry.api.wellknown_routes import _get_transport_type

        result = _get_transport_type({"transport": "stdio"})

        assert result == "stdio"


# =============================================================================
# TEST: _get_authentication_info
# =============================================================================


@pytest.mark.unit
class TestGetAuthenticationInfo:
    """Tests for the _get_authentication_info function."""

    def test_get_oauth_auth(self):
        """Test OAuth2 authentication info."""
        from registry.api.wellknown_routes import _get_authentication_info

        server_info = {
            "auth_type": "oauth",
            "auth_provider": "keycloak"
        }

        result = _get_authentication_info(server_info)

        assert result["type"] == "oauth2"
        assert result["required"] is True
        assert result["provider"] == "keycloak"
        assert "keycloak:read" in result["scopes"]

    def test_get_api_key_auth(self):
        """Test API key authentication info."""
        from registry.api.wellknown_routes import _get_authentication_info

        server_info = {
            "auth_type": "api-key"
        }

        result = _get_authentication_info(server_info)

        assert result["type"] == "api-key"
        assert result["required"] is True
        assert result["header"] == "X-API-Key"

    def test_get_default_auth(self):
        """Test default authentication info for unknown type."""
        from registry.api.wellknown_routes import _get_authentication_info

        server_info = {
            "auth_type": "unknown",
            "server_name": "TestServer"
        }

        result = _get_authentication_info(server_info)

        assert result["type"] == "oauth2"
        assert result["required"] is True
        assert "testserver:read" in result["scopes"]

    def test_get_auth_with_defaults(self):
        """Test authentication with default values."""
        from registry.api.wellknown_routes import _get_authentication_info

        server_info = {}

        result = _get_authentication_info(server_info)

        assert result["type"] == "oauth2"
        assert result["provider"] == "default"


# =============================================================================
# TEST: _get_tools_preview
# =============================================================================


@pytest.mark.unit
class TestGetToolsPreview:
    """Tests for the _get_tools_preview function."""

    def test_get_empty_tools(self):
        """Test getting tools preview with no tools."""
        from registry.api.wellknown_routes import _get_tools_preview

        result = _get_tools_preview({})

        assert result == []

    def test_get_tools_as_dicts(self):
        """Test getting tools preview with dict tools."""
        from registry.api.wellknown_routes import _get_tools_preview

        server_info = {
            "tool_list": [
                {"name": "tool1", "description": "First tool"},
                {"name": "tool2", "description": "Second tool"}
            ]
        }

        result = _get_tools_preview(server_info)

        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[0]["description"] == "First tool"

    def test_get_tools_as_strings(self):
        """Test getting tools preview with string tools."""
        from registry.api.wellknown_routes import _get_tools_preview

        server_info = {
            "tool_list": ["tool1", "tool2", "tool3"]
        }

        result = _get_tools_preview(server_info)

        assert len(result) == 3
        assert result[0]["name"] == "tool1"
        assert result[0]["description"] == "No description available"

    def test_get_tools_max_limit(self):
        """Test that tools preview respects max limit."""
        from registry.api.wellknown_routes import _get_tools_preview

        server_info = {
            "tool_list": [
                {"name": f"tool{i}", "description": f"Tool {i}"}
                for i in range(10)
            ]
        }

        result = _get_tools_preview(server_info, max_tools=5)

        assert len(result) == 5

    def test_get_tools_with_parsed_description(self):
        """Test getting tools preview with parsed_description."""
        from registry.api.wellknown_routes import _get_tools_preview

        server_info = {
            "tool_list": [
                {
                    "name": "tool1",
                    "description": "Fallback description",
                    "parsed_description": {"main": "Primary description"}
                }
            ]
        }

        result = _get_tools_preview(server_info)

        assert len(result) == 1
        assert result[0]["description"] == "Primary description"

    def test_get_tools_without_name(self):
        """Test getting tools preview when name is missing."""
        from registry.api.wellknown_routes import _get_tools_preview

        server_info = {
            "tool_list": [
                {"description": "Tool without name"}
            ]
        }

        result = _get_tools_preview(server_info)

        assert len(result) == 1
        assert result[0]["name"] == "unknown"
