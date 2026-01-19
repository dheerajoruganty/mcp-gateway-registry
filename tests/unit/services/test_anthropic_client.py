"""
Unit tests for registry.services.federation.anthropic_client module.

Tests the Anthropic MCP Registry federation client.
"""

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from registry.services.federation.anthropic_client import AnthropicFederationClient
from registry.schemas.federation_schema import AnthropicServerConfig


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: AnthropicFederationClient Initialization
# =============================================================================


@pytest.mark.unit
class TestAnthropicFederationClientInit:
    """Tests for AnthropicFederationClient initialization."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        client = AnthropicFederationClient(
            endpoint="https://api.anthropic.com/registry"
        )

        assert client.endpoint == "https://api.anthropic.com/registry"
        assert client.api_version == "v0.1"
        assert client.timeout_seconds == 30
        assert client.retry_attempts == 3

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        client = AnthropicFederationClient(
            endpoint="https://custom.endpoint.com",
            api_version="v1.0",
            timeout_seconds=60,
            retry_attempts=5
        )

        assert client.endpoint == "https://custom.endpoint.com"
        assert client.api_version == "v1.0"
        assert client.timeout_seconds == 60
        assert client.retry_attempts == 5


# =============================================================================
# TEST: fetch_server
# =============================================================================


@pytest.mark.unit
class TestFetchServer:
    """Tests for the fetch_server method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AnthropicFederationClient(
            endpoint="https://api.anthropic.com/registry"
        )

    @pytest.fixture
    def mock_response(self):
        """Create mock API response."""
        return {
            "server": {
                "description": "Test server description",
                "version": "1.0.0",
                "title": "Test Server",
                "remotes": [
                    {
                        "type": "streamable-http",
                        "url": "https://test.server.com/mcp"
                    }
                ],
                "_meta": {}
            }
        }

    def test_fetch_server_success(self, client, mock_response):
        """Test successful server fetch."""
        with patch.object(client, "_make_request", return_value=mock_response):
            result = client.fetch_server("test/server")

        assert result is not None
        assert result["server_name"] == "test/server"
        assert result["source"] == "anthropic"
        assert result["description"] == "Test server description"

    def test_fetch_server_failure(self, client):
        """Test server fetch failure."""
        with patch.object(client, "_make_request", return_value=None):
            result = client.fetch_server("test/server")

        assert result is None

    def test_fetch_server_with_config(self, client, mock_response):
        """Test server fetch with config."""
        config = AnthropicServerConfig(name="test/server")

        with patch.object(client, "_make_request", return_value=mock_response):
            result = client.fetch_server("test/server", config)

        assert result is not None
        assert result["server_name"] == "test/server"

    def test_fetch_server_url_encoding(self, client, mock_response):
        """Test that server names are properly URL encoded."""
        with patch.object(client, "_make_request", return_value=mock_response) as mock_request:
            client.fetch_server("ai.smithery/github")

        # Verify URL was encoded (/ becomes %2F)
        call_args = mock_request.call_args
        url = call_args[0][0]
        assert "ai.smithery%2Fgithub" in url


# =============================================================================
# TEST: fetch_all_servers
# =============================================================================


@pytest.mark.unit
class TestFetchAllServers:
    """Tests for the fetch_all_servers method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AnthropicFederationClient(
            endpoint="https://api.anthropic.com/registry"
        )

    def test_fetch_all_servers_empty_list(self, client):
        """Test fetching with empty config list."""
        result = client.fetch_all_servers([])

        assert result == []

    def test_fetch_all_servers_success(self, client):
        """Test fetching multiple servers successfully."""
        configs = [
            AnthropicServerConfig(name="server1"),
            AnthropicServerConfig(name="server2"),
        ]

        mock_server_data = {
            "server_name": "test",
            "source": "anthropic",
        }

        with patch.object(client, "fetch_server", return_value=mock_server_data):
            result = client.fetch_all_servers(configs)

        assert len(result) == 2

    def test_fetch_all_servers_partial_failure(self, client):
        """Test fetching with some failures."""
        configs = [
            AnthropicServerConfig(name="server1"),
            AnthropicServerConfig(name="server2"),
            AnthropicServerConfig(name="server3"),
        ]

        # First succeeds, second fails, third succeeds
        side_effects = [
            {"server_name": "server1"},
            None,
            {"server_name": "server3"},
        ]

        with patch.object(client, "fetch_server", side_effect=side_effects):
            result = client.fetch_all_servers(configs)

        assert len(result) == 2


# =============================================================================
# TEST: _transform_server_response
# =============================================================================


@pytest.mark.unit
class TestTransformServerResponse:
    """Tests for the _transform_server_response method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AnthropicFederationClient(
            endpoint="https://api.anthropic.com/registry"
        )

    def test_transform_basic_response(self, client):
        """Test transforming a basic response."""
        response = {
            "server": {
                "description": "Test description",
                "version": "2.0.0",
                "title": "Test Server",
                "remotes": [
                    {
                        "type": "streamable-http",
                        "url": "https://test.com/mcp"
                    }
                ],
            }
        }

        result = client._transform_server_response(response, "test/server", None)

        assert result["source"] == "anthropic"
        assert result["server_name"] == "test/server"
        assert result["description"] == "Test description"
        assert result["version"] == "2.0.0"
        assert result["proxy_pass_url"] == "https://test.com/mcp"
        assert result["transport_type"] == "streamable-http"
        assert result["is_read_only"] is True
        assert "anthropic-registry" in result["tags"]
        assert "federated" in result["tags"]

    def test_transform_response_with_packages_fallback(self, client):
        """Test transforming response using packages (old schema)."""
        response = {
            "server": {
                "description": "Old schema server",
                "version": "1.0.0",
                "title": "Old Server",
                "packages": [
                    {
                        "transport": {
                            "type": "http",
                            "url": "https://old.server.com/mcp"
                        }
                    }
                ],
            }
        }

        result = client._transform_server_response(response, "old/server", None)

        assert result["proxy_pass_url"] == "https://old.server.com/mcp"
        assert result["transport_type"] == "http"

    def test_transform_response_with_stdio_transport(self, client):
        """Test transforming response with stdio transport (no URL)."""
        response = {
            "server": {
                "description": "Stdio server",
                "version": "1.0.0",
                "packages": [
                    {
                        "transport": {
                            "type": "stdio",
                        }
                    }
                ],
            }
        }

        result = client._transform_server_response(response, "stdio/server", None)

        assert result["proxy_pass_url"] is None
        assert result["transport_type"] == "stdio"

    def test_transform_response_with_metadata_tags(self, client):
        """Test transforming response with metadata tags."""
        response = {
            "server": {
                "description": "Server with tags",
                "_meta": {
                    "category": {
                        "tags": ["ai", "automation"]
                    }
                },
            }
        }

        result = client._transform_server_response(response, "tagged/server", None)

        assert "ai" in result["tags"]
        assert "automation" in result["tags"]

    def test_transform_response_path_generation(self, client):
        """Test that path is correctly generated from server name."""
        response = {
            "server": {
                "description": "Test",
            }
        }

        result = client._transform_server_response(response, "namespace/server-name", None)

        # Path should replace / with -
        assert result["path"] == "/namespace-server-name"

    def test_transform_response_tags_from_name(self, client):
        """Test that tags are extracted from server name."""
        response = {
            "server": {
                "description": "Test",
            }
        }

        result = client._transform_server_response(response, "ai.smithery/github", None)

        assert "ai.smithery" in result["tags"]
        assert "github" in result["tags"]

    def test_transform_response_default_values(self, client):
        """Test default values when fields are missing."""
        response = {
            "server": {}
        }

        result = client._transform_server_response(response, "test/server", None)

        assert result["description"] == ""
        assert result["version"] == "1.0.0"
        assert result["title"] == "test/server"
        assert result["requires_auth"] is False
        assert result["is_enabled"] is True
        assert result["health_status"] == "unknown"
        assert result["num_tools"] == 0
