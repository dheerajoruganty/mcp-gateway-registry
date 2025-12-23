"""
Unit tests for registry.services.server_service module.

This module tests the ServerService class which manages server registration,
state management, and file-based storage operations.
"""

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from registry.services.server_service import ServerService

logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def server_service(
    mock_settings,
) -> ServerService:
    """
    Create a fresh ServerService instance with mocked settings.

    Args:
        mock_settings: Mocked settings fixture

    Returns:
        ServerService instance
    """
    service = ServerService()
    return service


@pytest.fixture
def sample_server_dict() -> dict[str, Any]:
    """
    Create a sample server dictionary for testing.

    Returns:
        Dictionary with sample server data
    """
    return {
        "path": "/test-server",
        "server_name": "test-server",
        "description": "A test server",
        "tags": ["test", "data"],
        "num_tools": 5,
        "num_stars": 4,
        "is_python": True,
        "license": "MIT",
        "proxy_pass_url": "http://localhost:8080",
        "tool_list": ["tool1", "tool2"],
    }


@pytest.fixture
def sample_server_dict_2() -> dict[str, Any]:
    """
    Create a second sample server dictionary for testing.

    Returns:
        Dictionary with sample server data
    """
    return {
        "path": "/another-server",
        "server_name": "another-server",
        "description": "Another test server",
        "tags": ["test"],
        "num_tools": 3,
        "num_stars": 5,
        "is_python": False,
        "license": "Apache-2.0",
        "proxy_pass_url": "http://localhost:9090",
        "tool_list": ["tool3"],
    }


@pytest.fixture
def server_json_files(
    tmp_path: Path,
    sample_server_dict: dict[str, Any],
) -> Path:
    """
    Create sample JSON server files in tmp_path.

    Args:
        tmp_path: Temporary directory path
        sample_server_dict: Sample server data

    Returns:
        Path to servers directory with JSON files
    """
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir(parents=True, exist_ok=True)

    # Create a valid server file
    server_file = servers_dir / "test_server.json"
    with open(server_file, "w") as f:
        json.dump(sample_server_dict, f, indent=2)

    # Create another valid server file
    server_2 = {
        "path": "/another-server",
        "server_name": "another-server",
        "description": "Another server",
    }
    server_file_2 = servers_dir / "another_server.json"
    with open(server_file_2, "w") as f:
        json.dump(server_2, f, indent=2)

    # Create an invalid server file (missing required fields)
    invalid_file = servers_dir / "invalid_server.json"
    with open(invalid_file, "w") as f:
        json.dump({"invalid": "data"}, f)

    # Create a malformed JSON file
    malformed_file = servers_dir / "malformed.json"
    with open(malformed_file, "w") as f:
        f.write("{invalid json")

    return servers_dir


# =============================================================================
# TEST: ServerService Instantiation
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestServerServiceInstantiation:
    """Test ServerService initialization and basic properties."""

    def test_init_creates_empty_registries(
        self,
        server_service: ServerService,
    ):
        """Test that __init__ creates empty registries."""
        # Assert
        assert server_service.registered_servers == {}
        assert server_service.service_state == {}

    def test_init_does_not_load_servers(
        self,
        server_service: ServerService,
    ):
        """Test that __init__ does not automatically load servers."""
        # Assert - should be empty until load_servers_and_state is called
        assert len(server_service.registered_servers) == 0
        assert len(server_service.service_state) == 0


# =============================================================================
# TEST: Loading Servers and State
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestLoadServersAndState:
    """Test loading server definitions and state from disk."""

    def test_load_servers_from_empty_directory(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test loading servers when directory is empty."""
        # Act
        server_service.load_servers_and_state()

        # Assert
        assert server_service.registered_servers == {}
        assert server_service.service_state == {}

    def test_load_servers_creates_directory_if_missing(
        self,
        server_service: ServerService,
        tmp_path: Path,
        mock_settings,
    ):
        """Test that load_servers_and_state creates servers dir if missing."""
        # Arrange
        servers_dir = tmp_path / "nonexistent" / "servers"
        type(mock_settings).servers_dir = property(lambda self: servers_dir)

        # Act
        server_service.load_servers_and_state()

        # Assert
        assert servers_dir.exists()

    def test_load_servers_from_json_files(
        self,
        server_service: ServerService,
        mock_settings,
        server_json_files: Path,
    ):
        """Test loading valid server definitions from JSON files."""
        # Arrange
        type(mock_settings).servers_dir = property(lambda self: server_json_files)

        # Act
        server_service.load_servers_and_state()

        # Assert
        assert len(server_service.registered_servers) == 2  # 2 valid servers
        assert "/test-server" in server_service.registered_servers
        assert "/another-server" in server_service.registered_servers

    def test_load_servers_adds_default_fields(
        self,
        server_service: ServerService,
        mock_settings,
        tmp_path: Path,
    ):
        """Test that loading servers adds default fields when missing."""
        # Arrange
        servers_dir = tmp_path / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)

        minimal_server = {
            "path": "/minimal-server",
            "server_name": "minimal-server",
        }
        server_file = servers_dir / "minimal.json"
        with open(server_file, "w") as f:
            json.dump(minimal_server, f)

        type(mock_settings).servers_dir = property(lambda self: servers_dir)

        # Act
        server_service.load_servers_and_state()

        # Assert
        loaded_server = server_service.registered_servers["/minimal-server"]
        assert loaded_server["description"] == ""
        assert loaded_server["tags"] == []
        assert loaded_server["num_tools"] == 0
        assert loaded_server["num_stars"] == 0
        assert loaded_server["is_python"] is False
        assert loaded_server["license"] == "N/A"
        assert loaded_server["proxy_pass_url"] is None
        assert loaded_server["tool_list"] == []

    def test_load_servers_skips_invalid_entries(
        self,
        server_service: ServerService,
        mock_settings,
        server_json_files: Path,
    ):
        """Test that invalid server entries are skipped with warnings."""
        # Arrange
        type(mock_settings).servers_dir = property(lambda self: server_json_files)

        # Act
        server_service.load_servers_and_state()

        # Assert - should only load valid servers
        assert len(server_service.registered_servers) == 2
        assert "invalid" not in str(server_service.registered_servers)

    def test_load_servers_handles_duplicate_paths(
        self,
        server_service: ServerService,
        mock_settings,
        tmp_path: Path,
    ):
        """Test that duplicate server paths are overwritten with warning."""
        # Arrange
        servers_dir = tmp_path / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)

        server_1 = {"path": "/duplicate", "server_name": "first"}
        server_2 = {"path": "/duplicate", "server_name": "second"}

        with open(servers_dir / "server1.json", "w") as f:
            json.dump(server_1, f)
        with open(servers_dir / "server2.json", "w") as f:
            json.dump(server_2, f)

        type(mock_settings).servers_dir = property(lambda self: servers_dir)

        # Act
        server_service.load_servers_and_state()

        # Assert - one of the servers should overwrite the other (order depends on glob)
        assert len(server_service.registered_servers) == 1
        assert "/duplicate" in server_service.registered_servers
        # The name could be either "first" or "second" depending on file system order
        assert server_service.registered_servers["/duplicate"]["server_name"] in ["first", "second"]

    def test_load_servers_skips_state_file(
        self,
        server_service: ServerService,
        mock_settings,
        tmp_path: Path,
    ):
        """Test that server_state.json file is skipped during loading."""
        # Arrange
        servers_dir = tmp_path / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)

        # Create state file (should be skipped)
        state_file = servers_dir / "server_state.json"
        with open(state_file, "w") as f:
            json.dump({"/test": True}, f)

        type(mock_settings).servers_dir = property(lambda self: servers_dir)
        type(mock_settings).state_file_path = property(lambda self: state_file)

        # Act
        server_service.load_servers_and_state()

        # Assert - state file should not be loaded as a server
        assert len(server_service.registered_servers) == 0

    def test_load_service_state_from_file(
        self,
        server_service: ServerService,
        mock_settings,
        tmp_path: Path,
    ):
        """Test loading persisted service state from disk."""
        # Arrange
        servers_dir = tmp_path / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)

        # Create server file
        server = {"path": "/test-server", "server_name": "test"}
        with open(servers_dir / "test.json", "w") as f:
            json.dump(server, f)

        # Create state file
        state_file = servers_dir / "server_state.json"
        with open(state_file, "w") as f:
            json.dump({"/test-server": True}, f)

        type(mock_settings).servers_dir = property(lambda self: servers_dir)
        type(mock_settings).state_file_path = property(lambda self: state_file)

        # Act
        server_service.load_servers_and_state()

        # Assert
        assert server_service.service_state["/test-server"] is True

    def test_load_service_state_handles_trailing_slash(
        self,
        server_service: ServerService,
        mock_settings,
        tmp_path: Path,
    ):
        """Test state loading handles trailing slash mismatch."""
        # Arrange
        servers_dir = tmp_path / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)

        # Server has trailing slash
        server = {"path": "/test-server/", "server_name": "test"}
        with open(servers_dir / "test.json", "w") as f:
            json.dump(server, f)

        # State file has no trailing slash
        state_file = servers_dir / "server_state.json"
        with open(state_file, "w") as f:
            json.dump({"/test-server": True}, f)

        type(mock_settings).servers_dir = property(lambda self: servers_dir)
        type(mock_settings).state_file_path = property(lambda self: state_file)

        # Act
        server_service.load_servers_and_state()

        # Assert - should match despite trailing slash difference
        assert server_service.service_state["/test-server/"] is True

    def test_load_service_state_with_missing_file(
        self,
        server_service: ServerService,
        mock_settings,
        tmp_path: Path,
    ):
        """Test loading state when state file doesn't exist."""
        # Arrange
        servers_dir = tmp_path / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)

        server = {"path": "/test-server", "server_name": "test"}
        with open(servers_dir / "test.json", "w") as f:
            json.dump(server, f)

        state_file = servers_dir / "nonexistent_state.json"
        type(mock_settings).servers_dir = property(lambda self: servers_dir)
        type(mock_settings).state_file_path = property(lambda self: state_file)

        # Act
        server_service.load_servers_and_state()

        # Assert - should initialize with False
        assert server_service.service_state["/test-server"] is False

    def test_load_service_state_with_invalid_json(
        self,
        server_service: ServerService,
        mock_settings,
        tmp_path: Path,
    ):
        """Test loading state when state file has invalid JSON."""
        # Arrange
        servers_dir = tmp_path / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)

        server = {"path": "/test-server", "server_name": "test"}
        with open(servers_dir / "test.json", "w") as f:
            json.dump(server, f)

        state_file = servers_dir / "server_state.json"
        with open(state_file, "w") as f:
            f.write("{invalid json")

        type(mock_settings).servers_dir = property(lambda self: servers_dir)
        type(mock_settings).state_file_path = property(lambda self: state_file)

        # Act
        server_service.load_servers_and_state()

        # Assert - should initialize with False
        assert server_service.service_state["/test-server"] is False


# =============================================================================
# TEST: Registering Servers
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestRegisterServer:
    """Test server registration functionality."""

    def test_register_new_server_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test successfully registering a new server."""
        # Act
        result = server_service.register_server(sample_server_dict)

        # Assert
        assert result is True
        assert sample_server_dict["path"] in server_service.registered_servers
        assert server_service.service_state[sample_server_dict["path"]] is False

    def test_register_server_saves_to_file(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that registering a server saves it to disk."""
        # Act
        server_service.register_server(sample_server_dict)

        # Assert - file name is generated from path
        expected_file = mock_settings.servers_dir / "test-server.json"
        assert expected_file.exists()

        with open(expected_file) as f:
            saved_data = json.load(f)
        assert saved_data["path"] == sample_server_dict["path"]
        assert saved_data["server_name"] == sample_server_dict["server_name"]

    def test_register_server_duplicate_path_fails(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that registering duplicate path fails."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act - try to register again
        result = server_service.register_server(sample_server_dict)

        # Assert
        assert result is False

    def test_register_server_persists_state(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that registering a server persists state to disk."""
        # Act
        server_service.register_server(sample_server_dict)

        # Assert
        state_file = mock_settings.state_file_path
        assert state_file.exists()

        with open(state_file) as f:
            state = json.load(f)
        assert sample_server_dict["path"] in state
        assert state[sample_server_dict["path"]] is False

    def test_register_server_with_save_failure(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test registering server when file save fails."""
        # Arrange - make servers_dir read-only
        mock_settings.servers_dir.chmod(0o444)

        # Act
        result = server_service.register_server(sample_server_dict)

        # Assert
        assert result is False
        assert sample_server_dict["path"] not in server_service.registered_servers

        # Cleanup
        mock_settings.servers_dir.chmod(0o755)


# =============================================================================
# TEST: Updating Servers
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestUpdateServer:
    """Test server update functionality."""

    def test_update_existing_server_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test successfully updating an existing server."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Modify server data
        updated_server = sample_server_dict.copy()
        updated_server["description"] = "Updated description"
        updated_server["num_tools"] = 10

        # Act - mock asyncio to skip FAISS update
        import asyncio
        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            result = server_service.update_server(sample_server_dict["path"], updated_server)

        # Assert
        assert result is True
        assert server_service.registered_servers[sample_server_dict["path"]]["description"] == "Updated description"
        assert server_service.registered_servers[sample_server_dict["path"]]["num_tools"] == 10

    def test_update_nonexistent_server_fails(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test updating a nonexistent server fails."""
        # Act
        result = server_service.update_server("/nonexistent", sample_server_dict)

        # Assert
        assert result is False

    def test_update_server_ensures_path_consistency(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that update_server ensures path is consistent."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Try to update with different path in data
        updated_server = sample_server_dict.copy()
        updated_server["path"] = "/different-path"

        # Act - mock asyncio to skip FAISS update
        import asyncio
        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            result = server_service.update_server(sample_server_dict["path"], updated_server)

        # Assert
        assert result is True
        # Path should remain as the original
        assert server_service.registered_servers[sample_server_dict["path"]]["path"] == sample_server_dict["path"]

    def test_update_server_saves_to_file(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that updating server saves changes to disk."""
        # Arrange
        server_service.register_server(sample_server_dict)

        updated_server = sample_server_dict.copy()
        updated_server["description"] = "Updated description"

        # Act - mock asyncio to skip FAISS update
        import asyncio
        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            server_service.update_server(sample_server_dict["path"], updated_server)

        # Assert - file name is generated from path
        expected_file = mock_settings.servers_dir / "test-server.json"
        with open(expected_file) as f:
            saved_data = json.load(f)
        assert saved_data["description"] == "Updated description"

    def test_update_enabled_server_regenerates_nginx(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that updating an enabled server regenerates nginx config."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.service_state[sample_server_dict["path"]] = True

        updated_server = sample_server_dict.copy()
        updated_server["proxy_pass_url"] = "http://localhost:9999"

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act - mock asyncio to skip FAISS update
            import asyncio
            with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
                server_service.update_server(sample_server_dict["path"], updated_server)

            # Assert
            mock_nginx_service.generate_config.assert_called_once()
            mock_nginx_service.reload_nginx.assert_called_once()


# =============================================================================
# TEST: Getting Server Info
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestGetServerInfo:
    """Test retrieving server information."""

    def test_get_server_info_exact_match(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test getting server info with exact path match."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act
        result = server_service.get_server_info(sample_server_dict["path"])

        # Assert
        assert result is not None
        assert result["path"] == sample_server_dict["path"]
        assert result["server_name"] == sample_server_dict["server_name"]

    def test_get_server_info_with_trailing_slash(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test getting server info handles trailing slash."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act - query with trailing slash when stored without
        result = server_service.get_server_info(sample_server_dict["path"] + "/")

        # Assert
        assert result is not None
        assert result["server_name"] == sample_server_dict["server_name"]

    def test_get_server_info_without_trailing_slash(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test getting server info handles missing trailing slash."""
        # Arrange
        server_with_slash = {
            "path": "/test-server/",
            "server_name": "test",
            "description": "Test",
        }
        server_service.register_server(server_with_slash)

        # Act - query without trailing slash when stored with
        result = server_service.get_server_info("/test-server")

        # Assert
        assert result is not None
        assert result["server_name"] == "test"

    def test_get_server_info_not_found(
        self,
        server_service: ServerService,
    ):
        """Test getting server info for nonexistent path."""
        # Act
        result = server_service.get_server_info("/nonexistent")

        # Assert
        assert result is None


# =============================================================================
# TEST: Getting All Servers
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestGetAllServers:
    """Test retrieving all servers."""

    def test_get_all_servers_empty(
        self,
        server_service: ServerService,
    ):
        """Test getting all servers when registry is empty."""
        # Act
        result = server_service.get_all_servers(include_federated=False)

        # Assert
        assert result == {}

    def test_get_all_servers_returns_all_local(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_settings,
    ):
        """Test getting all servers returns all local servers."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.register_server(sample_server_dict_2)

        # Act
        result = server_service.get_all_servers(include_federated=False)

        # Assert
        assert len(result) == 2
        assert sample_server_dict["path"] in result
        assert sample_server_dict_2["path"] in result

    def test_get_all_servers_includes_federated(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test getting all servers includes federated servers."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Mock federation service
        mock_federation_service = MagicMock()
        federated_server = {
            "path": "/federated-server",
            "server_name": "federated",
            "description": "Federated server",
        }
        mock_federation_service.get_federated_servers.return_value = [federated_server]

        # Patch at the point of use
        with patch("registry.services.federation_service.get_federation_service", return_value=mock_federation_service):
            # Act
            result = server_service.get_all_servers(include_federated=True)

        # Assert
        assert len(result) == 2
        assert sample_server_dict["path"] in result
        assert "/federated-server" in result

    def test_get_all_servers_skips_duplicate_federated(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that federated servers don't override local servers."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Mock federation service with duplicate path
        mock_federation_service = MagicMock()
        federated_server = {
            "path": sample_server_dict["path"],  # Same path as local
            "server_name": "federated-duplicate",
        }
        mock_federation_service.get_federated_servers.return_value = [federated_server]

        # Patch at the point of use
        with patch("registry.services.federation_service.get_federation_service", return_value=mock_federation_service):
            # Act
            result = server_service.get_all_servers(include_federated=True)

        # Assert
        assert len(result) == 1
        # Local server should be preserved
        assert result[sample_server_dict["path"]]["server_name"] == sample_server_dict["server_name"]


# =============================================================================
# TEST: Filtering Servers
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestGetFilteredServers:
    """Test filtering servers by user access."""

    def test_get_filtered_servers_empty_access_list(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test filtering with empty accessible_servers list."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act
        result = server_service.get_filtered_servers([])

        # Assert
        assert result == {}

    def test_get_filtered_servers_matches_technical_name(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test filtering matches by technical name (path without slashes)."""
        # Arrange
        server = {
            "path": "/test-server",
            "server_name": "Test Server Display Name",
            "description": "Test",
        }
        server_service.register_server(server)

        # Act - use technical name (path without slashes)
        result = server_service.get_filtered_servers(["test-server"])

        # Assert
        assert len(result) == 1
        assert "/test-server" in result

    def test_get_filtered_servers_multiple_servers(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_settings,
    ):
        """Test filtering with multiple servers and partial access."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.register_server(sample_server_dict_2)

        # Act - only grant access to one server
        accessible = ["test-server"]  # Technical name from path
        result = server_service.get_filtered_servers(accessible)

        # Assert
        assert len(result) == 1
        assert "/test-server" in result
        assert "/another-server" not in result

    def test_get_filtered_servers_with_trailing_slash_in_path(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test filtering handles trailing slash in path."""
        # Arrange
        server = {
            "path": "/test-server/",
            "server_name": "test",
            "description": "Test",
        }
        server_service.register_server(server)

        # Act
        result = server_service.get_filtered_servers(["test-server"])

        # Assert
        assert len(result) == 1
        assert "/test-server/" in result

    def test_user_can_access_server_path_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test user_can_access_server_path returns True for accessible server."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act
        result = server_service.user_can_access_server_path(
            sample_server_dict["path"],
            ["test-server"]
        )

        # Assert
        assert result is True

    def test_user_can_access_server_path_denied(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test user_can_access_server_path returns False for inaccessible server."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act
        result = server_service.user_can_access_server_path(
            sample_server_dict["path"],
            ["different-server"]
        )

        # Assert
        assert result is False

    def test_user_can_access_server_path_nonexistent(
        self,
        server_service: ServerService,
    ):
        """Test user_can_access_server_path returns False for nonexistent server."""
        # Act
        result = server_service.user_can_access_server_path(
            "/nonexistent",
            ["test-server"]
        )

        # Assert
        assert result is False


# =============================================================================
# TEST: Get All Servers With Permissions
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestGetAllServersWithPermissions:
    """Test getting servers with permission filtering."""

    def test_get_all_servers_with_permissions_admin_access(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_settings,
    ):
        """Test admin access (accessible_servers=None) returns all servers."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.register_server(sample_server_dict_2)

        # Act
        result = server_service.get_all_servers_with_permissions(
            accessible_servers=None,
            include_federated=False
        )

        # Assert
        assert len(result) == 2
        assert sample_server_dict["path"] in result
        assert sample_server_dict_2["path"] in result

    def test_get_all_servers_with_permissions_filtered_access(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_settings,
    ):
        """Test filtered access returns only accessible servers."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.register_server(sample_server_dict_2)

        # Act
        result = server_service.get_all_servers_with_permissions(
            accessible_servers=["test-server"],
            include_federated=False
        )

        # Assert
        assert len(result) == 1
        assert "/test-server" in result

    def test_get_all_servers_with_permissions_includes_federated(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that federated servers are included when requested."""
        # Arrange
        server_service.register_server(sample_server_dict)

        mock_federation_service = MagicMock()
        federated_server = {
            "path": "/federated-server",
            "server_name": "federated",
        }
        mock_federation_service.get_federated_servers.return_value = [federated_server]

        # Patch at the point of use
        with patch("registry.services.federation_service.get_federation_service", return_value=mock_federation_service):
            # Act
            result = server_service.get_all_servers_with_permissions(
                accessible_servers=["test-server", "federated-server"],
                include_federated=True
            )

        # Assert
        assert len(result) == 2


# =============================================================================
# TEST: Service State Management
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestServiceStateManagement:
    """Test service enabled/disabled state management."""

    def test_is_service_enabled_default_false(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that newly registered servers default to disabled."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act
        result = server_service.is_service_enabled(sample_server_dict["path"])

        # Assert
        assert result is False

    def test_is_service_enabled_with_trailing_slash(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test is_service_enabled handles trailing slash."""
        # Arrange
        server = {
            "path": "/test-server",
            "server_name": "test",
            "description": "Test",
        }
        server_service.register_server(server)
        server_service.service_state["/test-server"] = True

        # Act - query with trailing slash
        result = server_service.is_service_enabled("/test-server/")

        # Assert
        assert result is True

    def test_is_service_enabled_nonexistent_returns_false(
        self,
        server_service: ServerService,
    ):
        """Test is_service_enabled returns False for nonexistent path."""
        # Act
        result = server_service.is_service_enabled("/nonexistent")

        # Assert
        assert result is False

    def test_get_enabled_services_empty(
        self,
        server_service: ServerService,
    ):
        """Test get_enabled_services returns empty list when none enabled."""
        # Act
        result = server_service.get_enabled_services()

        # Assert
        assert result == []

    def test_get_enabled_services_returns_enabled_paths(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_settings,
    ):
        """Test get_enabled_services returns only enabled server paths."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.register_server(sample_server_dict_2)

        server_service.service_state[sample_server_dict["path"]] = True
        server_service.service_state[sample_server_dict_2["path"]] = False

        # Act
        result = server_service.get_enabled_services()

        # Assert
        assert len(result) == 1
        assert sample_server_dict["path"] in result
        assert sample_server_dict_2["path"] not in result


# =============================================================================
# TEST: Toggle Service
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestToggleService:
    """Test toggling service enabled/disabled state."""

    def test_toggle_service_enable(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test enabling a disabled service."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            result = server_service.toggle_service(sample_server_dict["path"], True)

            # Assert
            assert result is True
            assert server_service.service_state[sample_server_dict["path"]] is True
            mock_nginx_service.generate_config.assert_called_once()
            mock_nginx_service.reload_nginx.assert_called_once()

    def test_toggle_service_disable(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test disabling an enabled service."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.service_state[sample_server_dict["path"]] = True

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            result = server_service.toggle_service(sample_server_dict["path"], False)

            # Assert
            assert result is True
            assert server_service.service_state[sample_server_dict["path"]] is False
            mock_nginx_service.generate_config.assert_called_once()

    def test_toggle_service_nonexistent_fails(
        self,
        server_service: ServerService,
    ):
        """Test toggling nonexistent service fails."""
        # Act
        result = server_service.toggle_service("/nonexistent", True)

        # Assert
        assert result is False

    def test_toggle_service_persists_state(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that toggling service persists state to disk."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            server_service.toggle_service(sample_server_dict["path"], True)

        # Assert
        state_file = mock_settings.state_file_path
        with open(state_file) as f:
            state = json.load(f)
        assert state[sample_server_dict["path"]] is True


# =============================================================================
# TEST: Reload State From Disk
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestReloadStateFromDisk:
    """Test reloading service state from disk."""

    def test_reload_state_from_disk_detects_changes(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test reload_state_from_disk detects and applies changes."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.service_state[sample_server_dict["path"]] = False

        # Manually update state file
        state_file = mock_settings.state_file_path
        with open(state_file, "w") as f:
            json.dump({sample_server_dict["path"]: True}, f)

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            server_service.reload_state_from_disk()

            # Assert
            assert server_service.service_state[sample_server_dict["path"]] is True
            mock_nginx_service.generate_config.assert_called_once()
            mock_nginx_service.reload_nginx.assert_called_once()

    def test_reload_state_no_changes_skips_nginx(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test reload_state_from_disk skips nginx reload when no changes."""
        # Arrange
        server_service.register_server(sample_server_dict)
        # State is already False by default

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            server_service.reload_state_from_disk()

            # Assert
            mock_nginx_service.generate_config.assert_not_called()
            mock_nginx_service.reload_nginx.assert_not_called()


# =============================================================================
# TEST: Remove Server
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestRemoveServer:
    """Test server removal functionality."""

    def test_remove_server_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test successfully removing a server."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act
        result = server_service.remove_server(sample_server_dict["path"])

        # Assert
        assert result is True
        assert sample_server_dict["path"] not in server_service.registered_servers
        assert sample_server_dict["path"] not in server_service.service_state

    def test_remove_server_deletes_file(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that removing a server deletes its file."""
        # Arrange
        server_service.register_server(sample_server_dict)
        expected_file = mock_settings.servers_dir / "test-server.json"
        assert expected_file.exists()

        # Act
        server_service.remove_server(sample_server_dict["path"])

        # Assert
        assert not expected_file.exists()

    def test_remove_server_updates_state_file(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test that removing a server updates state file."""
        # Arrange
        server_service.register_server(sample_server_dict)

        # Act
        server_service.remove_server(sample_server_dict["path"])

        # Assert
        state_file = mock_settings.state_file_path
        with open(state_file) as f:
            state = json.load(f)
        assert sample_server_dict["path"] not in state

    def test_remove_server_nonexistent_fails(
        self,
        server_service: ServerService,
    ):
        """Test removing nonexistent server fails."""
        # Act
        result = server_service.remove_server("/nonexistent")

        # Assert
        assert result is False

    def test_remove_server_file_already_deleted(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test removing server when file is already deleted."""
        # Arrange
        server_service.register_server(sample_server_dict)
        expected_file = mock_settings.servers_dir / "test-server.json"
        expected_file.unlink()  # Delete file manually

        # Act
        result = server_service.remove_server(sample_server_dict["path"])

        # Assert - should still succeed
        assert result is True
        assert sample_server_dict["path"] not in server_service.registered_servers


# =============================================================================
# TEST: Helper Methods
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestHelperMethods:
    """Test helper methods and utilities."""

    def test_path_to_filename_simple(
        self,
        server_service: ServerService,
    ):
        """Test converting simple path to filename."""
        # Act
        result = server_service._path_to_filename("/test-server")

        # Assert
        assert result == "test-server.json"

    def test_path_to_filename_nested(
        self,
        server_service: ServerService,
    ):
        """Test converting nested path to filename."""
        # Act
        result = server_service._path_to_filename("/api/v1/test-server")

        # Assert
        assert result == "api_v1_test-server.json"

    def test_path_to_filename_with_trailing_slash(
        self,
        server_service: ServerService,
    ):
        """Test converting path with trailing slash."""
        # Act
        result = server_service._path_to_filename("/test-server/")

        # Assert
        assert result == "test-server_.json"

    def test_path_to_filename_already_has_json(
        self,
        server_service: ServerService,
    ):
        """Test that .json extension is not duplicated."""
        # Act
        result = server_service._path_to_filename("/test-server.json")

        # Assert
        assert result == "test-server.json"

    def test_save_server_to_file_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test save_server_to_file creates file with correct content."""
        # Act
        result = server_service.save_server_to_file(sample_server_dict)

        # Assert
        assert result is True
        expected_file = mock_settings.servers_dir / "test-server.json"
        assert expected_file.exists()

        with open(expected_file) as f:
            saved_data = json.load(f)
        assert saved_data["path"] == sample_server_dict["path"]

    def test_save_server_to_file_creates_directory(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        tmp_path: Path,
        mock_settings,
    ):
        """Test save_server_to_file creates directory if missing."""
        # Arrange
        new_servers_dir = tmp_path / "new_servers_dir"
        type(mock_settings).servers_dir = property(lambda self: new_servers_dir)

        # Act
        result = server_service.save_server_to_file(sample_server_dict)

        # Assert
        assert result is True
        assert new_servers_dir.exists()

    def test_save_service_state_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_settings,
    ):
        """Test save_service_state persists state to disk."""
        # Arrange
        server_service.service_state = {
            "/server1": True,
            "/server2": False,
        }

        # Act
        server_service.save_service_state()

        # Assert
        state_file = mock_settings.state_file_path
        assert state_file.exists()

        with open(state_file) as f:
            state = json.load(f)
        assert state["/server1"] is True
        assert state["/server2"] is False

    def test_save_service_state_handles_errors(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test save_service_state handles errors gracefully."""
        # Arrange
        server_service.service_state = {"/server1": True}

        # Make directory read-only
        mock_settings.servers_dir.chmod(0o444)

        # Act - should not raise exception
        server_service.save_service_state()

        # Cleanup
        mock_settings.servers_dir.chmod(0o755)


# =============================================================================
# TEST: Edge Cases and Error Handling
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling."""

    def test_load_servers_with_subdirectories(
        self,
        server_service: ServerService,
        mock_settings,
        tmp_path: Path,
    ):
        """Test loading servers from nested subdirectories."""
        # Arrange
        servers_dir = tmp_path / "servers"
        subdir = servers_dir / "category" / "subcategory"
        subdir.mkdir(parents=True, exist_ok=True)

        server = {"path": "/nested-server", "server_name": "nested"}
        with open(subdir / "nested.json", "w") as f:
            json.dump(server, f)

        type(mock_settings).servers_dir = property(lambda self: servers_dir)

        # Act
        server_service.load_servers_and_state()

        # Assert
        assert "/nested-server" in server_service.registered_servers

    def test_concurrent_state_modifications(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_settings,
    ):
        """Test handling concurrent state modifications."""
        # Arrange
        server_service.register_server(sample_server_dict)
        server_service.register_server(sample_server_dict_2)

        # Act - toggle multiple services
        result1 = server_service.toggle_service(sample_server_dict["path"], True)
        result2 = server_service.toggle_service(sample_server_dict_2["path"], True)

        # Assert
        assert result1 is True
        assert result2 is True
        assert server_service.service_state[sample_server_dict["path"]] is True
        assert server_service.service_state[sample_server_dict_2["path"]] is True

    def test_handle_unicode_in_server_data(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test handling unicode characters in server data."""
        # Arrange
        unicode_server = {
            "path": "/unicode-server",
            "server_name": "测试服务器",
            "description": "A server with unicode: 日本語, Español, العربية",
        }

        # Act
        result = server_service.register_server(unicode_server)

        # Assert
        assert result is True
        loaded = server_service.get_server_info("/unicode-server")
        assert loaded["server_name"] == "测试服务器"

    def test_empty_path_handling(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test handling empty or root path."""
        # Arrange
        root_server = {
            "path": "/",
            "server_name": "root-server",
            "description": "Root server",
        }

        # Act
        result = server_service.register_server(root_server)

        # Assert
        assert result is True
        assert "/" in server_service.registered_servers

    def test_long_path_handling(
        self,
        server_service: ServerService,
        mock_settings,
    ):
        """Test handling very long paths."""
        # Arrange
        long_path = "/" + "/".join(["segment"] * 20)
        long_path_server = {
            "path": long_path,
            "server_name": "long-path-server",
            "description": "Server with long path",
        }

        # Act
        result = server_service.register_server(long_path_server)

        # Assert
        assert result is True
        assert long_path in server_service.registered_servers
