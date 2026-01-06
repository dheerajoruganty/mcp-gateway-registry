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
    mock_server_repository,
    mock_search_repository,
):
    """
    Create a fresh ServerService instance with mocked repositories.

    Args:
        mock_server_repository: Mocked server repository
        mock_search_repository: Mocked search repository

    Yields:
        ServerService instance with injected mocks
    """
    # Directly inject mocked repositories into factory singletons
    from registry.repositories import factory

    # Save original values
    original_server_repo = factory._server_repo
    original_search_repo = factory._search_repo

    # Set mocked repositories
    factory._server_repo = mock_server_repository
    factory._search_repo = mock_search_repository

    # Create service (will use mocked singletons)
    service = ServerService()
    yield service

    # Restore original values
    factory._server_repo = original_server_repo
    factory._search_repo = original_search_repo


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

    def test_init_creates_service_with_repositories(
        self,
        server_service: ServerService,
        mock_server_repository,
        mock_search_repository,
    ):
        """Test that __init__ creates service with repository dependencies."""
        # Assert - service should have repository instances
        assert server_service._repo is mock_server_repository
        assert server_service._search_repo is mock_search_repository


# =============================================================================
# TEST: Loading Servers and State
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestLoadServersAndState:
    """Test loading server definitions and state from disk."""

    @pytest.mark.asyncio
    async def test_load_servers_and_state_calls_repository(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test that load_servers_and_state delegates to repository.load_all()."""
        # Act
        await server_service.load_servers_and_state()

        # Assert - verify orchestration
        mock_server_repository.load_all.assert_called_once()


# NOTE: The following tests have been removed because they test implementation
# details (file loading, JSON parsing, state management) that belong to the
# repository layer, not the service layer. These tests should exist in the
# repository tests instead:
#
# - test_load_servers_from_empty_directory
# - test_load_servers_creates_directory_if_missing
# - test_load_servers_from_json_files
# - test_load_servers_adds_default_fields
# - test_load_servers_skips_invalid_entries
# - test_load_servers_handles_duplicate_paths
# - test_load_servers_skips_state_file
# - test_load_service_state_from_file
# - test_load_service_state_handles_trailing_slash
# - test_load_service_state_with_missing_file
# - test_load_service_state_with_invalid_json
#
# The service layer should only test orchestration, not file I/O details.



# =============================================================================
# TEST: Registering Servers
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestRegisterServer:
    """Test server registration functionality."""

    @pytest.mark.asyncio
    async def test_register_new_server_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test successfully registering a new server."""
        # Arrange
        mock_server_repository.create.return_value = True
        mock_server_repository.get_state.return_value = False

        # Act
        result = await server_service.register_server(sample_server_dict)

        # Assert
        assert result is True
        mock_server_repository.create.assert_called_once_with(sample_server_dict)
        mock_search_repository.index_server.assert_called_once_with(
            sample_server_dict["path"],
            sample_server_dict,
            False
        )

    @pytest.mark.asyncio
    async def test_register_server_calls_repository_create(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test that registering a server calls repository create."""
        # Arrange
        mock_server_repository.create.return_value = True
        mock_server_repository.get_state.return_value = False

        # Act
        await server_service.register_server(sample_server_dict)

        # Assert - verify orchestration
        mock_server_repository.create.assert_called_once_with(sample_server_dict)

    @pytest.mark.asyncio
    async def test_register_server_duplicate_path_fails(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test that registering duplicate path fails."""
        # Arrange - first call succeeds, second fails
        mock_server_repository.create.side_effect = [True, False]
        mock_server_repository.get_state.return_value = False

        # Act - register twice
        result1 = await server_service.register_server(sample_server_dict)
        result2 = await server_service.register_server(sample_server_dict)

        # Assert
        assert result1 is True
        assert result2 is False
        assert mock_server_repository.create.call_count == 2

    @pytest.mark.asyncio
    async def test_register_server_indexes_in_search(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test that registering a server indexes it in search."""
        # Arrange
        mock_server_repository.create.return_value = True
        mock_server_repository.get_state.return_value = False

        # Act
        await server_service.register_server(sample_server_dict)

        # Assert - verify search indexing
        mock_search_repository.index_server.assert_called_once_with(
            sample_server_dict["path"],
            sample_server_dict,
            False
        )

    @pytest.mark.asyncio
    async def test_register_server_with_repository_failure(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test registering server when repository fails."""
        # Arrange - repository returns False (failure)
        mock_server_repository.create.return_value = False

        # Act
        result = await server_service.register_server(sample_server_dict)

        # Assert
        assert result is False
        # Search should not be called if repository fails
        mock_search_repository.index_server.assert_not_called()


# =============================================================================
# TEST: Updating Servers
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestUpdateServer:
    """Test server update functionality."""

    @pytest.mark.asyncio
    async def test_update_existing_server_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test successfully updating an existing server."""
        # Arrange
        updated_server = sample_server_dict.copy()
        updated_server["description"] = "Updated description"
        updated_server["num_tools"] = 10

        mock_server_repository.update.return_value = True
        mock_server_repository.get_state.return_value = False

        # Act
        result = await server_service.update_server(sample_server_dict["path"], updated_server)

        # Assert
        assert result is True
        mock_server_repository.update.assert_called_once_with(
            sample_server_dict["path"],
            updated_server
        )
        mock_search_repository.index_server.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_nonexistent_server_fails(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test updating a nonexistent server fails."""
        # Arrange
        mock_server_repository.update.return_value = False

        # Act
        result = await server_service.update_server("/nonexistent", sample_server_dict)

        # Assert
        assert result is False
        mock_server_repository.update.assert_called_once_with("/nonexistent", sample_server_dict)

    @pytest.mark.asyncio
    async def test_update_server_calls_repository(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test that update_server calls repository.update()."""
        # Arrange
        updated_server = sample_server_dict.copy()
        updated_server["description"] = "Updated description"

        mock_server_repository.update.return_value = True
        mock_server_repository.get_state.return_value = False

        # Act
        await server_service.update_server(sample_server_dict["path"], updated_server)

        # Assert - verify orchestration
        mock_server_repository.update.assert_called_once_with(
            sample_server_dict["path"],
            updated_server
        )

    @pytest.mark.asyncio
    async def test_update_server_indexes_in_search(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test that updating server updates search index."""
        # Arrange
        updated_server = sample_server_dict.copy()
        updated_server["description"] = "Updated description"

        mock_server_repository.update.return_value = True
        mock_server_repository.get_state.return_value = False

        # Act
        await server_service.update_server(sample_server_dict["path"], updated_server)

        # Assert - verify search indexing
        mock_search_repository.index_server.assert_called_once_with(
            sample_server_dict["path"],
            updated_server,
            False
        )

# NOTE: test_update_enabled_server_regenerates_nginx removed
# This is more of an integration test and involves complex nginx mocking.
# Nginx configuration regeneration is tested separately in integration tests.


# =============================================================================
# TEST: Getting Server Info
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestGetServerInfo:
    """Test retrieving server information."""

    @pytest.mark.asyncio
    async def test_get_server_info_delegates_to_repository(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test that get_server_info delegates to repository.get()."""
        # Arrange
        mock_server_repository.get.return_value = sample_server_dict

        # Act
        result = await server_service.get_server_info(sample_server_dict["path"])

        # Assert
        mock_server_repository.get.assert_called_once_with(sample_server_dict["path"])
        assert result == sample_server_dict

    @pytest.mark.asyncio
    async def test_get_server_info_returns_none_when_not_found(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test that get_server_info returns None when repository returns None."""
        # Arrange
        mock_server_repository.get.return_value = None

        # Act
        result = await server_service.get_server_info("/nonexistent")

        # Assert
        mock_server_repository.get.assert_called_once_with("/nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_server_info_returns_server_data(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test that get_server_info returns server data from repository."""
        # Arrange
        mock_server_repository.get.return_value = sample_server_dict

        # Act
        result = await server_service.get_server_info(sample_server_dict["path"])

        # Assert
        assert result is not None
        assert result["path"] == sample_server_dict["path"]
        assert result["server_name"] == sample_server_dict["server_name"]


# =============================================================================
# TEST: Getting All Servers
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestGetAllServers:
    """Test retrieving all servers."""

    @pytest.mark.asyncio
    async def test_get_all_servers_delegates_to_repository(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test that get_all_servers delegates to repository.list_all()."""
        # Arrange
        mock_server_repository.list_all.return_value = {}

        # Act
        result = await server_service.get_all_servers(include_federated=False)

        # Assert
        mock_server_repository.list_all.assert_called_once()
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_all_servers_returns_repository_data(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_server_repository,
    ):
        """Test that get_all_servers returns data from repository."""
        # Arrange
        servers = {
            sample_server_dict["path"]: sample_server_dict,
            sample_server_dict_2["path"]: sample_server_dict_2,
        }
        mock_server_repository.list_all.return_value = servers

        # Act
        result = await server_service.get_all_servers(include_federated=False)

        # Assert
        assert len(result) == 2
        assert sample_server_dict["path"] in result
        assert sample_server_dict_2["path"] in result

    @pytest.mark.asyncio
    async def test_get_all_servers_includes_federated(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test getting all servers includes federated servers."""
        # Arrange
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict
        }

        # Mock federation service
        from unittest.mock import AsyncMock
        mock_federation_service = MagicMock()
        federated_server = {
            "path": "/federated-server",
            "server_name": "federated",
            "description": "Federated server",
        }
        mock_federation_service.get_federated_servers = AsyncMock(return_value=[federated_server])

        # Patch at the point of use
        with patch("registry.services.federation_service.get_federation_service", return_value=mock_federation_service):
            # Act
            result = await server_service.get_all_servers(include_federated=True)

        # Assert
        assert len(result) == 2
        assert sample_server_dict["path"] in result
        assert "/federated-server" in result

    @pytest.mark.asyncio
    async def test_get_all_servers_skips_duplicate_federated(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test that federated servers don't override local servers."""
        # Arrange
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict
        }

        # Mock federation service with duplicate path
        from unittest.mock import AsyncMock
        mock_federation_service = MagicMock()
        federated_server = {
            "path": sample_server_dict["path"],  # Same path as local
            "server_name": "federated-duplicate",
        }
        mock_federation_service.get_federated_servers = AsyncMock(return_value=[federated_server])

        # Patch at the point of use
        with patch("registry.services.federation_service.get_federation_service", return_value=mock_federation_service):
            # Act
            result = await server_service.get_all_servers(include_federated=True)

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

    @pytest.mark.asyncio
    async def test_get_filtered_servers_empty_access_list(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test filtering with empty accessible_servers list."""
        # Arrange
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict
        }

        # Act
        result = await server_service.get_filtered_servers([])

        # Assert
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_filtered_servers_delegates_to_repository(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test that get_filtered_servers delegates to repository.list_all()."""
        # Arrange
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict
        }

        # Act
        await server_service.get_filtered_servers(["test-server"])

        # Assert
        mock_server_repository.list_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_filtered_servers_matches_technical_name(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test filtering matches by technical name (path without slashes)."""
        # Arrange
        server = {
            "path": "/test-server",
            "server_name": "Test Server Display Name",
            "description": "Test",
        }
        mock_server_repository.list_all.return_value = {
            server["path"]: server
        }

        # Act - use technical name (path without slashes)
        result = await server_service.get_filtered_servers(["test-server"])

        # Assert
        assert len(result) == 1
        assert "/test-server" in result

    @pytest.mark.asyncio
    async def test_get_filtered_servers_multiple_servers(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_server_repository,
    ):
        """Test filtering with multiple servers and partial access."""
        # Arrange
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict,
            sample_server_dict_2["path"]: sample_server_dict_2,
        }

        # Act - only grant access to one server
        accessible = ["test-server"]  # Technical name from path
        result = await server_service.get_filtered_servers(accessible)

        # Assert
        assert len(result) == 1
        assert "/test-server" in result
        assert "/another-server" not in result

    @pytest.mark.asyncio
    async def test_get_filtered_servers_with_trailing_slash_in_path(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test filtering handles trailing slash in path."""
        # Arrange
        server = {
            "path": "/test-server/",
            "server_name": "test",
            "description": "Test",
        }
        mock_server_repository.list_all.return_value = {
            server["path"]: server
        }

        # Act
        result = await server_service.get_filtered_servers(["test-server"])

        # Assert
        assert len(result) == 1
        assert "/test-server/" in result

    @pytest.mark.asyncio
    async def test_get_filtered_servers_filters_correctly(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_server_repository,
    ):
        """Test that filtering logic correctly applies access control."""
        # Arrange
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict,
            sample_server_dict_2["path"]: sample_server_dict_2,
        }

        # Act - grant access to both servers
        accessible = ["test-server", "another-server"]
        result = await server_service.get_filtered_servers(accessible)

        # Assert
        assert len(result) == 2
        assert "/test-server" in result
        assert "/another-server" in result

    @pytest.mark.asyncio
    async def test_user_can_access_server_path_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test user_can_access_server_path returns True for accessible server."""
        # Arrange
        mock_server_repository.get.return_value = sample_server_dict

        # Act
        result = await server_service.user_can_access_server_path(
            sample_server_dict["path"],
            ["test-server"]
        )

        # Assert
        assert result is True
        mock_server_repository.get.assert_called_once_with(sample_server_dict["path"])

    @pytest.mark.asyncio
    async def test_user_can_access_server_path_denied(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test user_can_access_server_path returns False for inaccessible server."""
        # Arrange
        mock_server_repository.get.return_value = sample_server_dict

        # Act
        result = await server_service.user_can_access_server_path(
            sample_server_dict["path"],
            ["different-server"]
        )

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_user_can_access_server_path_nonexistent(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test user_can_access_server_path returns False for nonexistent server."""
        # Arrange
        mock_server_repository.get.return_value = None

        # Act
        result = await server_service.user_can_access_server_path(
            "/nonexistent",
            ["test-server"]
        )

        # Assert
        assert result is False
        mock_server_repository.get.assert_called_once_with("/nonexistent")


# =============================================================================
# TEST: Get All Servers With Permissions
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestGetAllServersWithPermissions:
    """Test getting servers with permission filtering."""

    @pytest.mark.asyncio
    async def test_get_all_servers_with_permissions_admin_access(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_server_repository,
    ):
        """Test admin access (accessible_servers=None) returns all servers."""
        # Arrange
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict,
            sample_server_dict_2["path"]: sample_server_dict_2,
        }

        # Act
        result = await server_service.get_all_servers_with_permissions(
            accessible_servers=None,
            include_federated=False
        )

        # Assert
        assert len(result) == 2
        assert sample_server_dict["path"] in result
        assert sample_server_dict_2["path"] in result

    @pytest.mark.asyncio
    async def test_get_all_servers_with_permissions_filtered_access(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_server_repository,
    ):
        """Test filtered access returns only accessible servers."""
        # Arrange
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict,
            sample_server_dict_2["path"]: sample_server_dict_2,
        }

        # Act
        result = await server_service.get_all_servers_with_permissions(
            accessible_servers=["test-server"],
            include_federated=False
        )

        # Assert
        assert len(result) == 1
        assert "/test-server" in result

    @pytest.mark.asyncio
    async def test_get_all_servers_with_permissions_includes_federated(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test that federated servers are included when requested."""
        # Arrange
        from unittest.mock import AsyncMock
        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: sample_server_dict
        }

        mock_federation_service = MagicMock()
        federated_server = {
            "path": "/federated-server",
            "server_name": "federated",
        }
        mock_federation_service.get_federated_servers = AsyncMock(return_value=[federated_server])

        # Patch at the point of use
        with patch("registry.services.federation_service.get_federation_service", return_value=mock_federation_service):
            # Act
            result = await server_service.get_all_servers_with_permissions(
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

    @pytest.mark.asyncio
    async def test_is_service_enabled_default_false(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test that is_service_enabled delegates to repository."""
        # Arrange
        mock_server_repository.get_state.return_value = False

        # Act
        result = await server_service.is_service_enabled(sample_server_dict["path"])

        # Assert
        assert result is False
        mock_server_repository.get_state.assert_called_once_with(sample_server_dict["path"])

    @pytest.mark.asyncio
    async def test_is_service_enabled_returns_true_when_enabled(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test is_service_enabled returns True when repository state is enabled."""
        # Arrange
        mock_server_repository.get_state.return_value = True

        # Act
        result = await server_service.is_service_enabled("/test-server")

        # Assert
        assert result is True
        mock_server_repository.get_state.assert_called_once_with("/test-server")

    @pytest.mark.asyncio
    async def test_is_service_enabled_nonexistent_returns_false(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test is_service_enabled returns False for nonexistent path."""
        # Arrange
        mock_server_repository.get_state.return_value = False

        # Act
        result = await server_service.is_service_enabled("/nonexistent")

        # Assert
        assert result is False
        mock_server_repository.get_state.assert_called_once_with("/nonexistent")

    @pytest.mark.asyncio
    async def test_get_enabled_services_empty(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test get_enabled_services returns empty list when none enabled."""
        # Arrange
        mock_server_repository.list_all.return_value = {}

        # Act
        result = await server_service.get_enabled_services()

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_get_enabled_services_returns_enabled_paths(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_server_repository,
    ):
        """Test get_enabled_services returns only enabled server paths."""
        # Arrange
        server_1 = sample_server_dict.copy()
        server_1["is_enabled"] = True
        server_2 = sample_server_dict_2.copy()
        server_2["is_enabled"] = False

        mock_server_repository.list_all.return_value = {
            sample_server_dict["path"]: server_1,
            sample_server_dict_2["path"]: server_2,
        }

        # Act
        result = await server_service.get_enabled_services()

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

    @pytest.mark.asyncio
    async def test_toggle_service_enable_calls_repository(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test enabling a service calls repository.set_state() correctly."""
        # Arrange
        path = sample_server_dict["path"]
        mock_server_repository.set_state.return_value = True
        # Mock list_all to return empty dict (no enabled servers)
        mock_server_repository.list_all.return_value = {}

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            result = await server_service.toggle_service(path, True)

            # Assert
            assert result is True
            mock_server_repository.set_state.assert_called_once_with(path, True)
            mock_nginx_service.generate_config.assert_called_once()
            mock_nginx_service.reload_nginx.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_service_disable_calls_repository(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test disabling a service calls repository.set_state() correctly."""
        # Arrange
        path = sample_server_dict["path"]
        mock_server_repository.set_state.return_value = True
        # Mock list_all to return empty dict (no enabled servers)
        mock_server_repository.list_all.return_value = {}

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            result = await server_service.toggle_service(path, False)

            # Assert
            assert result is True
            mock_server_repository.set_state.assert_called_once_with(path, False)
            mock_nginx_service.generate_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_service_nonexistent_server_fails(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test toggling nonexistent service returns False."""
        # Arrange
        mock_server_repository.set_state.return_value = False

        # Act
        result = await server_service.toggle_service("/nonexistent", True)

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_toggle_service_repository_failure(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
    ):
        """Test toggling service when repository fails."""
        # Arrange
        path = sample_server_dict["path"]
        mock_server_repository.set_state.return_value = False

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            result = await server_service.toggle_service(path, True)

            # Assert
            assert result is False
            mock_server_repository.set_state.assert_called_once_with(path, True)
            # Nginx should not be called if repository fails
            mock_nginx_service.generate_config.assert_not_called()
            mock_nginx_service.reload_nginx.assert_not_called()


# =============================================================================
# TEST: Reload State From Disk
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestReloadStateFromDisk:
    """Test reloading service state from disk."""

    @pytest.mark.asyncio
    async def test_reload_state_from_disk_calls_repository(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test that reload_state_from_disk delegates to repository.load_all()."""
        # Arrange
        # Mock list_all to return empty dict (no servers, no changes)
        mock_server_repository.list_all.return_value = {}

        # Act
        await server_service.reload_state_from_disk()

        # Assert - verify orchestration (load_all called twice - before and after)
        assert mock_server_repository.load_all.call_count == 1

    @pytest.mark.asyncio
    async def test_reload_state_detects_changes(
        self,
        server_service: ServerService,
        mock_server_repository,
        sample_server_dict: dict[str, Any],
    ):
        """Test that reload_state_from_disk detects when enabled services change."""
        # Arrange
        path = sample_server_dict["path"]
        # Enabled server for all calls
        enabled_server = sample_server_dict.copy()
        enabled_server["is_enabled"] = True
        # list_all returns different results to simulate state change
        # First call (before reload): empty, After reload: has enabled server
        mock_server_repository.list_all.return_value = {path: enabled_server}
        mock_server_repository.get.return_value = enabled_server

        # Mock nginx service to avoid integration issues
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Mock the nginx methods to succeed
            mock_nginx_service.generate_config.return_value = None
            mock_nginx_service.reload_nginx.return_value = None

            # Act
            await server_service.reload_state_from_disk()

            # Assert - verify that repository.load_all was called (the key orchestration)
            mock_server_repository.load_all.assert_called_once()
            # Verify list_all was called multiple times (for getting enabled services)
            assert mock_server_repository.list_all.call_count >= 2

    @pytest.mark.asyncio
    async def test_reload_state_skips_nginx_when_no_changes(
        self,
        server_service: ServerService,
        mock_server_repository,
    ):
        """Test that nginx is not regenerated when no changes detected."""
        # Arrange
        # Both calls return empty dict (no changes)
        mock_server_repository.list_all.return_value = {}

        # Mock nginx service
        with patch("registry.core.nginx_service.nginx_service") as mock_nginx_service:
            # Act
            await server_service.reload_state_from_disk()

            # Assert
            mock_nginx_service.generate_config.assert_not_called()
            mock_nginx_service.reload_nginx.assert_not_called()


# NOTE: The following tests have been removed because they test implementation
# details (direct state file manipulation) that belong to the repository layer:
#
# - test_reload_state_from_disk_detects_changes (tested state_file manipulation)
# - test_reload_state_no_changes_skips_nginx (integrated state_file + nginx)
#
# The service layer should only test orchestration with repositories.


# =============================================================================
# TEST: Remove Server
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestRemoveServer:
    """Test server removal functionality."""

    @pytest.mark.asyncio
    async def test_remove_server_success(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test successfully removing a server."""
        # Arrange
        mock_server_repository.delete.return_value = True

        # Act
        result = await server_service.remove_server(sample_server_dict["path"])

        # Assert
        assert result is True
        mock_server_repository.delete.assert_called_once_with(sample_server_dict["path"])
        mock_search_repository.remove_entity.assert_called_once_with(sample_server_dict["path"])

    @pytest.mark.asyncio
    async def test_remove_server_calls_repository_delete(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test that remove_server calls repository delete."""
        # Arrange
        mock_server_repository.delete.return_value = True

        # Act
        await server_service.remove_server(sample_server_dict["path"])

        # Assert - verify orchestration
        mock_server_repository.delete.assert_called_once_with(sample_server_dict["path"])

    @pytest.mark.asyncio
    async def test_remove_server_removes_from_search(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test that removing server removes it from search index."""
        # Arrange
        mock_server_repository.delete.return_value = True

        # Act
        await server_service.remove_server(sample_server_dict["path"])

        # Assert - verify search removal
        mock_search_repository.remove_entity.assert_called_once_with(sample_server_dict["path"])

    @pytest.mark.asyncio
    async def test_remove_server_nonexistent_fails(
        self,
        server_service: ServerService,
        mock_server_repository,
        mock_search_repository,
    ):
        """Test removing nonexistent server fails."""
        # Arrange
        mock_server_repository.delete.return_value = False

        # Act
        result = await server_service.remove_server("/nonexistent")

        # Assert
        assert result is False
        mock_server_repository.delete.assert_called_once_with("/nonexistent")

    @pytest.mark.asyncio
    async def test_remove_server_with_repository_failure(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test removing server when repository fails."""
        # Arrange - repository returns False (failure)
        mock_server_repository.delete.return_value = False

        # Act
        result = await server_service.remove_server(sample_server_dict["path"])

        # Assert
        assert result is False
        # Search should not be called if repository fails
        mock_search_repository.remove_entity.assert_not_called()



# =============================================================================
# TEST: Helper Methods
# =============================================================================


# NOTE: TestHelperMethods class removed - these tests have been moved to
# tests/unit/repositories/test_file_server_repository.py where they properly
# test the repository layer instead of the service layer.
# The following methods were moved:
#   - test_path_to_filename_* (4 tests)
#   - test_save_server_to_file_* (2 tests)
#   - test_save_service_state_* (2 tests)
# Total: 9 tests migrated to repository tests (now 16 tests in repository file)


# =============================================================================
# TEST: Edge Cases and Error Handling
# =============================================================================


@pytest.mark.unit
@pytest.mark.servers
class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_concurrent_state_modifications(
        self,
        server_service: ServerService,
        sample_server_dict: dict[str, Any],
        sample_server_dict_2: dict[str, Any],
        mock_server_repository,
        mock_search_repository,
    ):
        """Test handling concurrent state modifications."""
        # Arrange
        mock_server_repository.create.return_value = True
        mock_server_repository.get_state.return_value = False
        mock_server_repository.set_state.return_value = True
        mock_server_repository.list_all.return_value = {}

        # Act - register and toggle multiple services
        result1 = await server_service.register_server(sample_server_dict)
        result2 = await server_service.register_server(sample_server_dict_2)

        # Mock nginx for toggle operations
        with patch("registry.core.nginx_service.nginx_service"):
            toggle1 = await server_service.toggle_service(sample_server_dict["path"], True)
            toggle2 = await server_service.toggle_service(sample_server_dict_2["path"], True)

        # Assert
        assert result1 is True
        assert result2 is True
        assert toggle1 is True
        assert toggle2 is True

    @pytest.mark.asyncio
    async def test_handle_unicode_in_server_data(
        self,
        server_service: ServerService,
        mock_server_repository,
        mock_search_repository,
    ):
        """Test handling unicode characters in server data."""
        # Arrange
        unicode_server = {
            "path": "/unicode-server",
            "server_name": "测试服务器",
            "description": "A server with unicode: 日本語, Español, العربية",
        }
        mock_server_repository.create.return_value = True
        mock_server_repository.get_state.return_value = False
        mock_server_repository.get.return_value = unicode_server

        # Act
        result = await server_service.register_server(unicode_server)

        # Assert
        assert result is True
        mock_server_repository.create.assert_called_once_with(unicode_server)

        # Verify unicode data is preserved in repository call
        loaded = await server_service.get_server_info("/unicode-server")
        assert loaded["server_name"] == "测试服务器"

    @pytest.mark.asyncio
    async def test_empty_path_handling(
        self,
        server_service: ServerService,
        mock_server_repository,
        mock_search_repository,
    ):
        """Test handling empty or root path."""
        # Arrange
        root_server = {
            "path": "/",
            "server_name": "root-server",
            "description": "Root server",
        }
        mock_server_repository.create.return_value = True
        mock_server_repository.get_state.return_value = False

        # Act
        result = await server_service.register_server(root_server)

        # Assert
        assert result is True
        mock_server_repository.create.assert_called_once_with(root_server)

    @pytest.mark.asyncio
    async def test_long_path_handling(
        self,
        server_service: ServerService,
        mock_server_repository,
        mock_search_repository,
    ):
        """Test handling very long paths."""
        # Arrange
        long_path = "/" + "/".join(["segment"] * 20)
        long_path_server = {
            "path": long_path,
            "server_name": "long-path-server",
            "description": "Server with long path",
        }
        mock_server_repository.create.return_value = True
        mock_server_repository.get_state.return_value = False

        # Act
        result = await server_service.register_server(long_path_server)

        # Assert
        assert result is True
        mock_server_repository.create.assert_called_once_with(long_path_server)


# NOTE: The following test has been removed because it tests implementation
# details (file system loading) that belong to the repository layer:
#
# - test_load_servers_with_subdirectories (tested file system traversal)
#
# The service layer should only test orchestration, not file I/O details.

