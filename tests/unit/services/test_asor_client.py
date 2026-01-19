"""
Unit tests for registry.services.federation.asor_client module.

Tests the Workday ASOR federation client.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from registry.services.federation.asor_client import AsorFederationClient
from registry.schemas.federation_schema import AsorAgentConfig


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: AsorFederationClient Initialization
# =============================================================================


@pytest.mark.unit
class TestAsorFederationClientInit:
    """Tests for AsorFederationClient initialization."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        client = AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1"
        )

        assert client.endpoint == "https://api.workday.com/asor/v1"
        assert client.auth_type == "oauth2"
        assert client.timeout_seconds == 30
        assert client.retry_attempts == 3

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        client = AsorFederationClient(
            endpoint="https://custom.endpoint.com",
            auth_type="api-key",
            auth_env_var="ASOR_CREDS",
            tenant_url="https://tenant.workday.com",
            timeout_seconds=60,
            retry_attempts=5
        )

        assert client.endpoint == "https://custom.endpoint.com"
        assert client.auth_type == "api-key"
        assert client.auth_env_var == "ASOR_CREDS"
        assert client.tenant_url == "https://tenant.workday.com"


# =============================================================================
# TEST: _get_access_token
# =============================================================================


@pytest.mark.unit
class TestGetAccessToken:
    """Tests for the _get_access_token method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1",
            auth_env_var="ASOR_CREDENTIALS"
        )

    def test_get_access_token_from_env(self, client):
        """Test getting access token from ASOR_ACCESS_TOKEN env var."""
        with patch.dict(os.environ, {"ASOR_ACCESS_TOKEN": "test-token-12345"}):
            token = client._get_access_token()

        assert token == "test-token-12345"
        assert client._access_token == "test-token-12345"

    def test_get_access_token_cached(self, client):
        """Test using cached access token."""
        client._access_token = "cached-token"
        client._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

        # Clear env var to ensure we use cached token
        with patch.dict(os.environ, {}, clear=True):
            token = client._get_access_token()

        assert token == "cached-token"

    def test_get_access_token_no_env_var_configured(self):
        """Test when no auth_env_var is configured."""
        client = AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1"
        )

        with patch.dict(os.environ, {}, clear=True):
            token = client._get_access_token()

        assert token is None

    def test_get_access_token_missing_credentials(self, client):
        """Test when credentials env var is missing."""
        with patch.dict(os.environ, {}, clear=True):
            token = client._get_access_token()

        assert token is None


# =============================================================================
# TEST: fetch_agent
# =============================================================================


@pytest.mark.unit
class TestFetchAgent:
    """Tests for the fetch_agent method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1"
        )

    @pytest.fixture
    def mock_response(self):
        """Create mock API response."""
        return {
            "name": "Test Agent",
            "description": "A test agent",
            "version": "2.0.0",
            "endpoint": "https://test.agent.com/api",
            "capabilities": ["chat", "search"],
            "tools": [{"name": "tool1"}, {"name": "tool2"}]
        }

    def test_fetch_agent_success(self, client, mock_response):
        """Test successful agent fetch."""
        with patch.object(client, "_get_access_token", return_value="test-token"):
            with patch.object(client, "_make_request", return_value=mock_response):
                result = client.fetch_agent("agent-123")

        assert result is not None
        assert result["source"] == "asor"
        assert result["server_name"] == "asor/agent-123"
        assert result["description"] == "A test agent"

    def test_fetch_agent_auth_failure(self, client):
        """Test agent fetch with authentication failure."""
        with patch.object(client, "_get_access_token", return_value=None):
            result = client.fetch_agent("agent-123")

        assert result is None

    def test_fetch_agent_request_failure(self, client):
        """Test agent fetch with request failure."""
        with patch.object(client, "_get_access_token", return_value="test-token"):
            with patch.object(client, "_make_request", return_value=None):
                result = client.fetch_agent("agent-123")

        assert result is None

    def test_fetch_agent_with_config(self, client, mock_response):
        """Test agent fetch with config."""
        config = AsorAgentConfig(id="agent-123")

        with patch.object(client, "_get_access_token", return_value="test-token"):
            with patch.object(client, "_make_request", return_value=mock_response):
                result = client.fetch_agent("agent-123", config)

        assert result is not None


# =============================================================================
# TEST: list_all_agents
# =============================================================================


@pytest.mark.unit
class TestListAllAgents:
    """Tests for the list_all_agents method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1"
        )

    def test_list_all_agents_success_with_data_field(self, client):
        """Test listing agents when response has data field."""
        mock_response = {
            "data": [
                {"id": "agent-1", "name": "Agent 1"},
                {"id": "agent-2", "name": "Agent 2"},
            ],
            "total": 2
        }

        with patch.object(client, "_get_access_token", return_value="test-token"):
            with patch.object(client, "_make_request", return_value=mock_response):
                result = client.list_all_agents()

        assert len(result) == 2

    def test_list_all_agents_success_with_list(self, client):
        """Test listing agents when response is a list."""
        mock_response = [
            {"id": "agent-1", "name": "Agent 1"},
            {"id": "agent-2", "name": "Agent 2"},
        ]

        with patch.object(client, "_get_access_token", return_value="test-token"):
            with patch.object(client, "_make_request", return_value=mock_response):
                result = client.list_all_agents()

        assert len(result) == 2

    def test_list_all_agents_auth_failure(self, client):
        """Test listing agents with auth failure."""
        with patch.object(client, "_get_access_token", return_value=None):
            result = client.list_all_agents()

        assert result == []

    def test_list_all_agents_request_failure(self, client):
        """Test listing agents with request failure."""
        with patch.object(client, "_get_access_token", return_value="test-token"):
            with patch.object(client, "_make_request", return_value=None):
                result = client.list_all_agents()

        assert result == []

    def test_list_all_agents_unexpected_response(self, client):
        """Test listing agents with unexpected response format."""
        mock_response = {"unexpected": "format"}

        with patch.object(client, "_get_access_token", return_value="test-token"):
            with patch.object(client, "_make_request", return_value=mock_response):
                result = client.list_all_agents()

        assert result == []


# =============================================================================
# TEST: fetch_all_agents
# =============================================================================


@pytest.mark.unit
class TestFetchAllAgents:
    """Tests for the fetch_all_agents method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1"
        )

    def test_fetch_all_agents_empty_configs(self, client):
        """Test fetching with empty config list calls list_all_agents."""
        with patch.object(client, "list_all_agents", return_value=[{"id": "1"}]) as mock_list:
            result = client.fetch_all_agents([])

        mock_list.assert_called_once()
        assert len(result) == 1

    def test_fetch_all_agents_success(self, client):
        """Test fetching multiple agents successfully."""
        configs = [
            AsorAgentConfig(id="agent-1"),
            AsorAgentConfig(id="agent-2"),
        ]

        mock_agent_data = {
            "source": "asor",
            "server_name": "asor/test",
        }

        with patch.object(client, "fetch_agent", return_value=mock_agent_data):
            result = client.fetch_all_agents(configs)

        assert len(result) == 2

    def test_fetch_all_agents_partial_failure(self, client):
        """Test fetching with some failures."""
        configs = [
            AsorAgentConfig(id="agent-1"),
            AsorAgentConfig(id="agent-2"),
            AsorAgentConfig(id="agent-3"),
        ]

        # First succeeds, second fails, third succeeds
        side_effects = [
            {"server_name": "agent-1"},
            None,
            {"server_name": "agent-3"},
        ]

        with patch.object(client, "fetch_agent", side_effect=side_effects):
            result = client.fetch_all_agents(configs)

        assert len(result) == 2


# =============================================================================
# TEST: fetch_server (alias)
# =============================================================================


@pytest.mark.unit
class TestFetchServer:
    """Tests for the fetch_server method (alias for fetch_agent)."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1"
        )

    def test_fetch_server_calls_fetch_agent(self, client):
        """Test that fetch_server calls fetch_agent."""
        with patch.object(client, "fetch_agent", return_value={"id": "1"}) as mock_fetch:
            result = client.fetch_server("agent-123")

        mock_fetch.assert_called_once_with("agent-123", None)
        assert result == {"id": "1"}


# =============================================================================
# TEST: fetch_all_servers (alias)
# =============================================================================


@pytest.mark.unit
class TestFetchAllServers:
    """Tests for the fetch_all_servers method (alias)."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1"
        )

    def test_fetch_all_servers_converts_to_agent_configs(self, client):
        """Test that server names are converted to agent configs."""
        with patch.object(client, "fetch_all_agents", return_value=[]) as mock_fetch:
            client.fetch_all_servers(["agent-1", "agent-2"])

        # Verify it was called with agent configs
        call_args = mock_fetch.call_args[0][0]
        assert len(call_args) == 2
        assert all(isinstance(c, AsorAgentConfig) for c in call_args)


# =============================================================================
# TEST: _transform_agent_response
# =============================================================================


@pytest.mark.unit
class TestTransformAgentResponse:
    """Tests for the _transform_agent_response method."""

    @pytest.fixture
    def client(self):
        """Create a client for testing."""
        return AsorFederationClient(
            endpoint="https://api.workday.com/asor/v1"
        )

    def test_transform_basic_response(self, client):
        """Test transforming a basic response."""
        response = {
            "name": "Test Agent",
            "description": "A test agent",
            "version": "2.0.0",
            "endpoint": "https://test.com/api",
            "capabilities": ["chat"],
            "tools": [{"name": "tool1"}]
        }

        result = client._transform_agent_response(response, "agent-123", None)

        assert result["source"] == "asor"
        assert result["server_name"] == "asor/agent-123"
        assert result["description"] == "A test agent"
        assert result["version"] == "2.0.0"
        assert result["proxy_pass_url"] == "https://test.com/api"
        assert result["is_read_only"] is True
        assert "asor" in result["tags"]
        assert "workday" in result["tags"]
        assert "federated" in result["tags"]
        assert result["num_tools"] == 1

    def test_transform_response_with_url_field(self, client):
        """Test transforming response with url field instead of endpoint."""
        response = {
            "name": "Test Agent",
            "url": "https://alt.url.com/api"
        }

        result = client._transform_agent_response(response, "agent-123", None)

        assert result["proxy_pass_url"] == "https://alt.url.com/api"

    def test_transform_response_default_values(self, client):
        """Test default values when fields are missing."""
        response = {}

        result = client._transform_agent_response(response, "agent-123", None)

        assert result["server_name"] == "asor/agent-123"
        assert result["title"] == "agent-123"
        assert result["description"] == ""
        assert result["version"] == "1.0.0"
        assert result["requires_auth"] is True
        assert result["is_enabled"] is True
        assert result["health_status"] == "unknown"
        assert result["num_tools"] == 0

    def test_transform_response_path_generation(self, client):
        """Test that path is correctly generated."""
        response = {"name": "Test"}

        result = client._transform_agent_response(response, "my-agent", None)

        assert result["path"] == "/asor-my-agent"

    def test_transform_response_with_tools(self, client):
        """Test that tools count is correct."""
        response = {
            "tools": [
                {"name": "tool1"},
                {"name": "tool2"},
                {"name": "tool3"}
            ]
        }

        result = client._transform_agent_response(response, "agent-123", None)

        assert result["num_tools"] == 3
        assert result["metadata"]["tools"] == response["tools"]

    def test_transform_response_includes_metadata(self, client):
        """Test that original response is preserved in metadata."""
        response = {
            "name": "Test",
            "custom_field": "custom_value"
        }

        result = client._transform_agent_response(response, "agent-123", None)

        assert result["metadata"]["original_response"] == response
        assert result["metadata"]["agent_id"] == "agent-123"
