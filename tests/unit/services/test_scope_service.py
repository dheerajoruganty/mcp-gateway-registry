"""
Unit tests for registry.services.scope_service module.

This module tests the scope service for managing server scopes, groups,
and authorization rules.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from registry.services import scope_service


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_scope_repo():
    """Create a mock scope repository."""
    mock = AsyncMock()
    mock.add_server_scope = AsyncMock()
    mock.remove_server_from_all_scopes = AsyncMock()
    mock.remove_server_scope = AsyncMock()
    mock.add_server_to_ui_scopes = AsyncMock()
    mock.remove_server_from_ui_scopes = AsyncMock()
    mock.group_exists = AsyncMock(return_value=True)
    mock.create_group = AsyncMock()
    mock.delete_group = AsyncMock()
    mock.import_group = AsyncMock(return_value=True)
    mock.get_group = AsyncMock(return_value={"name": "test-group"})
    mock.list_groups = AsyncMock(return_value={"total_count": 1, "groups": {}})
    return mock


@pytest.fixture
def mock_server_service():
    """Create a mock server service."""
    mock = MagicMock()
    mock.get_server_info = AsyncMock(return_value={
        "server_name": "test-server",
        "path": "/test-server",
        "tool_list": [
            {"name": "tool1"},
            {"name": "tool2"},
        ],
    })
    return mock


# =============================================================================
# TEST: _trigger_auth_server_reload
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestTriggerAuthServerReload:
    """Tests for the _trigger_auth_server_reload function."""

    async def test_trigger_reload_missing_password(self):
        """Test reload fails when ADMIN_PASSWORD not set."""
        with patch.dict("os.environ", {}, clear=True):
            result = await scope_service._trigger_auth_server_reload()

        assert result is False

    async def test_trigger_reload_success(self):
        """Test successful auth server reload."""
        with patch.dict("os.environ", {"ADMIN_PASSWORD": "test-pass"}):
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                result = await scope_service._trigger_auth_server_reload()

        assert result is True

    async def test_trigger_reload_http_error(self):
        """Test reload handles HTTP error."""
        with patch.dict("os.environ", {"ADMIN_PASSWORD": "test-pass"}):
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                result = await scope_service._trigger_auth_server_reload()

        assert result is False

    async def test_trigger_reload_exception(self):
        """Test reload handles exception gracefully."""
        with patch.dict("os.environ", {"ADMIN_PASSWORD": "test-pass"}):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=Exception("Connection failed")
                )

                result = await scope_service._trigger_auth_server_reload()

        assert result is False


# =============================================================================
# TEST: update_server_scopes
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateServerScopes:
    """Tests for the update_server_scopes function."""

    async def test_update_server_scopes_success(self, mock_scope_repo):
        """Test successfully updating server scopes."""
        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock):
                result = await scope_service.update_server_scopes(
                    server_path="/test-server",
                    server_name="Test Server",
                    tools=["tool1", "tool2"],
                )

        assert result is True
        assert mock_scope_repo.add_server_scope.call_count == 2

    async def test_update_server_scopes_exception(self, mock_scope_repo):
        """Test update_server_scopes handles exception."""
        mock_scope_repo.add_server_scope.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.update_server_scopes(
                server_path="/test-server",
                server_name="Test Server",
                tools=["tool1"],
            )

        assert result is False


# =============================================================================
# TEST: remove_server_scopes
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveServerScopes:
    """Tests for the remove_server_scopes function."""

    async def test_remove_server_scopes_success(self, mock_scope_repo):
        """Test successfully removing server scopes."""
        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock):
                result = await scope_service.remove_server_scopes("/test-server")

        assert result is True
        mock_scope_repo.remove_server_from_all_scopes.assert_called_once_with(
            server_path="/test-server"
        )

    async def test_remove_server_scopes_exception(self, mock_scope_repo):
        """Test remove_server_scopes handles exception."""
        mock_scope_repo.remove_server_from_all_scopes.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.remove_server_scopes("/test-server")

        assert result is False


# =============================================================================
# TEST: add_server_to_groups
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestAddServerToGroups:
    """Tests for the add_server_to_groups function."""

    async def test_add_server_to_groups_success(self, mock_scope_repo, mock_server_service):
        """Test successfully adding server to groups."""
        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service.server_service", mock_server_service):
                with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock):
                    result = await scope_service.add_server_to_groups(
                        server_path="/test-server",
                        group_names=["group1", "group2"],
                    )

        assert result is True
        assert mock_scope_repo.add_server_scope.call_count == 2
        assert mock_scope_repo.add_server_to_ui_scopes.call_count == 2

    async def test_add_server_to_groups_server_not_found(self, mock_scope_repo, mock_server_service):
        """Test add_server_to_groups when server not found."""
        mock_server_service.get_server_info.return_value = None

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service.server_service", mock_server_service):
                result = await scope_service.add_server_to_groups(
                    server_path="/nonexistent",
                    group_names=["group1"],
                )

        assert result is False

    async def test_add_server_to_groups_group_not_found(self, mock_scope_repo, mock_server_service):
        """Test add_server_to_groups when group does not exist."""
        mock_scope_repo.group_exists.return_value = False

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service.server_service", mock_server_service):
                with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock):
                    result = await scope_service.add_server_to_groups(
                        server_path="/test-server",
                        group_names=["nonexistent-group"],
                    )

        assert result is True
        mock_scope_repo.add_server_scope.assert_not_called()

    async def test_add_server_to_groups_exception(self, mock_scope_repo, mock_server_service):
        """Test add_server_to_groups handles exception."""
        mock_scope_repo.add_server_scope.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service.server_service", mock_server_service):
                result = await scope_service.add_server_to_groups(
                    server_path="/test-server",
                    group_names=["group1"],
                )

        assert result is False


# =============================================================================
# TEST: remove_server_from_groups
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemoveServerFromGroups:
    """Tests for the remove_server_from_groups function."""

    async def test_remove_server_from_groups_success(self, mock_scope_repo, mock_server_service):
        """Test successfully removing server from groups."""
        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service.server_service", mock_server_service):
                with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock):
                    result = await scope_service.remove_server_from_groups(
                        server_path="/test-server",
                        group_names=["group1", "group2"],
                    )

        assert result is True
        assert mock_scope_repo.remove_server_scope.call_count == 2
        assert mock_scope_repo.remove_server_from_ui_scopes.call_count == 2

    async def test_remove_server_from_groups_server_not_found(self, mock_scope_repo, mock_server_service):
        """Test remove when server not found uses path-derived name."""
        mock_server_service.get_server_info.return_value = None

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service.server_service", mock_server_service):
                with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock):
                    result = await scope_service.remove_server_from_groups(
                        server_path="/test-server",
                        group_names=["group1"],
                    )

        assert result is True

    async def test_remove_server_from_groups_exception(self, mock_scope_repo, mock_server_service):
        """Test remove_server_from_groups handles exception."""
        mock_scope_repo.remove_server_scope.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service.server_service", mock_server_service):
                result = await scope_service.remove_server_from_groups(
                    server_path="/test-server",
                    group_names=["group1"],
                )

        assert result is False


# =============================================================================
# TEST: create_group
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateGroup:
    """Tests for the create_group function."""

    async def test_create_group_success(self, mock_scope_repo):
        """Test successfully creating a group."""
        mock_scope_repo.group_exists.return_value = False

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock):
                result = await scope_service.create_group(
                    group_name="new-group",
                    description="A new group",
                )

        assert result is True
        mock_scope_repo.create_group.assert_called_once_with(
            group_name="new-group",
            description="A new group",
        )

    async def test_create_group_already_exists(self, mock_scope_repo):
        """Test create_group when group already exists."""
        mock_scope_repo.group_exists.return_value = True

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.create_group("existing-group")

        assert result is False
        mock_scope_repo.create_group.assert_not_called()

    async def test_create_group_exception(self, mock_scope_repo):
        """Test create_group handles exception."""
        mock_scope_repo.group_exists.return_value = False
        mock_scope_repo.create_group.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.create_group("new-group")

        assert result is False


# =============================================================================
# TEST: delete_group
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeleteGroup:
    """Tests for the delete_group function."""

    async def test_delete_group_success(self, mock_scope_repo):
        """Test successfully deleting a group."""
        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock):
                result = await scope_service.delete_group("test-group")

        assert result is True
        mock_scope_repo.delete_group.assert_called_once_with(
            group_name="test-group",
            remove_from_mappings=True,
        )

    async def test_delete_group_not_found(self, mock_scope_repo):
        """Test delete_group when group does not exist."""
        mock_scope_repo.group_exists.return_value = False

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.delete_group("nonexistent")

        assert result is False
        mock_scope_repo.delete_group.assert_not_called()

    async def test_delete_group_exception(self, mock_scope_repo):
        """Test delete_group handles exception."""
        mock_scope_repo.delete_group.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.delete_group("test-group")

        assert result is False


# =============================================================================
# TEST: import_group
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestImportGroup:
    """Tests for the import_group function."""

    async def test_import_group_success(self, mock_scope_repo):
        """Test successfully importing a group."""
        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.import_group(
                scope_name="test-scope",
                description="Test description",
                server_access=[],
                group_mappings=[],
            )

        assert result is True
        mock_scope_repo.import_group.assert_called_once()

    async def test_import_group_failure(self, mock_scope_repo):
        """Test import_group when repository returns False."""
        mock_scope_repo.import_group.return_value = False

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.import_group(scope_name="test-scope")

        assert result is False

    async def test_import_group_exception(self, mock_scope_repo):
        """Test import_group handles exception."""
        mock_scope_repo.import_group.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.import_group(scope_name="test-scope")

        assert result is False


# =============================================================================
# TEST: get_group
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetGroup:
    """Tests for the get_group function."""

    async def test_get_group_success(self, mock_scope_repo):
        """Test successfully getting a group."""
        mock_scope_repo.get_group.return_value = {
            "name": "test-group",
            "description": "Test group",
        }

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.get_group("test-group")

        assert result is not None
        assert result["name"] == "test-group"

    async def test_get_group_not_found(self, mock_scope_repo):
        """Test get_group when group does not exist."""
        mock_scope_repo.get_group.return_value = None

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.get_group("nonexistent")

        assert result is None

    async def test_get_group_exception(self, mock_scope_repo):
        """Test get_group handles exception."""
        mock_scope_repo.get_group.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.get_group("test-group")

        assert result is None


# =============================================================================
# TEST: list_groups
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestListGroups:
    """Tests for the list_groups function."""

    async def test_list_groups_success(self, mock_scope_repo):
        """Test successfully listing groups."""
        mock_scope_repo.list_groups.return_value = {
            "total_count": 2,
            "groups": {"group1": {}, "group2": {}},
        }

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.list_groups()

        assert result["total_count"] == 2
        assert "group1" in result["groups"]

    async def test_list_groups_empty(self, mock_scope_repo):
        """Test list_groups with no groups."""
        mock_scope_repo.list_groups.return_value = {"total_count": 0, "groups": {}}

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.list_groups()

        assert result["total_count"] == 0

    async def test_list_groups_exception(self, mock_scope_repo):
        """Test list_groups handles exception."""
        mock_scope_repo.list_groups.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.list_groups()

        assert result["total_count"] == 0
        assert "error" in result


# =============================================================================
# TEST: group_exists
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestGroupExists:
    """Tests for the group_exists function."""

    async def test_group_exists_true(self, mock_scope_repo):
        """Test group_exists returns True when group exists."""
        mock_scope_repo.group_exists.return_value = True

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.group_exists("test-group")

        assert result is True

    async def test_group_exists_false(self, mock_scope_repo):
        """Test group_exists returns False when group does not exist."""
        mock_scope_repo.group_exists.return_value = False

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.group_exists("nonexistent")

        assert result is False

    async def test_group_exists_exception(self, mock_scope_repo):
        """Test group_exists handles exception."""
        mock_scope_repo.group_exists.side_effect = Exception("DB error")

        with patch("registry.services.scope_service.get_scope_repository", return_value=mock_scope_repo):
            result = await scope_service.group_exists("test-group")

        assert result is False


# =============================================================================
# TEST: trigger_auth_server_reload (public wrapper)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestTriggerAuthServerReloadPublic:
    """Tests for the public trigger_auth_server_reload function."""

    async def test_trigger_auth_server_reload_public(self):
        """Test public wrapper calls private function."""
        with patch("registry.services.scope_service._trigger_auth_server_reload", new_callable=AsyncMock) as mock:
            mock.return_value = True

            result = await scope_service.trigger_auth_server_reload()

        assert result is True
        mock.assert_called_once()
