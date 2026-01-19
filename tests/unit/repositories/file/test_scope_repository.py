"""
Unit tests for file-based scope repository.
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from registry.repositories.file.scope_repository import FileScopeRepository


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: FileScopeRepository Initialization
# =============================================================================


@pytest.mark.unit
class TestFileScopeRepositoryInit:
    """Tests for FileScopeRepository initialization."""

    def test_init_creates_empty_scopes(self):
        """Test that init creates empty scopes dict."""
        repo = FileScopeRepository()

        assert repo._scopes_data == {}


# =============================================================================
# TEST: FileScopeRepository Load All
# =============================================================================


@pytest.mark.unit
class TestFileScopeRepositoryLoadAll:
    """Tests for FileScopeRepository load_all method."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileScopeRepository()
        repo._scopes_file = temp_dir / "scopes.yml"
        repo._alt_scopes_file = temp_dir / "alt_scopes.yml"
        return repo

    @pytest.mark.asyncio
    async def test_load_all_no_file(self, repo):
        """Test loading when no file exists."""
        await repo.load_all()

        assert repo._scopes_data == {}

    @pytest.mark.asyncio
    async def test_load_all_from_primary_file(self, repo):
        """Test loading from primary scopes file."""
        scopes_data = {
            "test-scope": [
                {"server": "test-server", "methods": ["GET"]}
            ]
        }
        with open(repo._scopes_file, "w") as f:
            yaml.dump(scopes_data, f)

        await repo.load_all()

        assert "test-scope" in repo._scopes_data

    @pytest.mark.asyncio
    async def test_load_all_from_alt_file(self, repo):
        """Test loading from alternative scopes file."""
        # Create alt file (not primary)
        scopes_data = {
            "alt-scope": [
                {"server": "alt-server", "methods": ["POST"]}
            ]
        }
        with open(repo._alt_scopes_file, "w") as f:
            yaml.dump(scopes_data, f)

        await repo.load_all()

        assert "alt-scope" in repo._scopes_data

    @pytest.mark.asyncio
    async def test_load_all_primary_takes_precedence(self, repo):
        """Test that primary file takes precedence over alt file."""
        # Create both files
        primary_data = {"primary-scope": []}
        with open(repo._scopes_file, "w") as f:
            yaml.dump(primary_data, f)

        alt_data = {"alt-scope": []}
        with open(repo._alt_scopes_file, "w") as f:
            yaml.dump(alt_data, f)

        await repo.load_all()

        assert "primary-scope" in repo._scopes_data
        assert "alt-scope" not in repo._scopes_data

    @pytest.mark.asyncio
    async def test_load_all_invalid_yaml(self, repo):
        """Test loading invalid YAML."""
        repo._scopes_file.write_text("invalid: yaml: content: [")

        await repo.load_all()

        assert repo._scopes_data == {}


# =============================================================================
# TEST: FileScopeRepository Get Methods
# =============================================================================


@pytest.mark.unit
class TestFileScopeRepositoryGetMethods:
    """Tests for FileScopeRepository getter methods."""

    @pytest.fixture
    def repo(self):
        """Create a repository for testing."""
        repo = FileScopeRepository()
        repo._scopes_data = {
            "test-scope": [
                {"server": "server1", "methods": ["GET"]},
                {"server": "server2", "methods": ["POST"]}
            ],
            "group_mappings": {
                "admin": ["test-scope", "other-scope"],
                "user": ["test-scope"]
            },
            "UI-Scopes": {
                "admin": {"list_service": ["server1", "server2"]},
                "user": {"list_service": ["server1"]}
            }
        }
        return repo

    @pytest.mark.asyncio
    async def test_get_ui_scopes_existing(self, repo):
        """Test getting UI scopes for existing group."""
        result = await repo.get_ui_scopes("admin")

        assert "list_service" in result
        assert len(result["list_service"]) == 2

    @pytest.mark.asyncio
    async def test_get_ui_scopes_nonexistent(self, repo):
        """Test getting UI scopes for nonexistent group."""
        result = await repo.get_ui_scopes("nonexistent")

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_group_mappings_existing(self, repo):
        """Test getting group mappings for existing group."""
        result = await repo.get_group_mappings("admin")

        assert "test-scope" in result
        assert "other-scope" in result

    @pytest.mark.asyncio
    async def test_get_group_mappings_nonexistent(self, repo):
        """Test getting group mappings for nonexistent group."""
        result = await repo.get_group_mappings("nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_server_scopes_existing(self, repo):
        """Test getting server scopes for existing scope."""
        result = await repo.get_server_scopes("test-scope")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_server_scopes_nonexistent(self, repo):
        """Test getting server scopes for nonexistent scope."""
        result = await repo.get_server_scopes("nonexistent")

        assert result == []


# =============================================================================
# TEST: FileScopeRepository Server Scope Operations
# =============================================================================


@pytest.mark.unit
class TestFileScopeRepositoryServerScopes:
    """Tests for FileScopeRepository server scope operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileScopeRepository()
        repo._scopes_file = temp_dir / "scopes.yml"
        repo._scopes_data = {
            "test-scope": [
                {"server": "existing-server", "methods": ["GET"]}
            ]
        }
        # Create initial file
        with open(repo._scopes_file, "w") as f:
            yaml.dump(repo._scopes_data, f)
        return repo

    @pytest.mark.asyncio
    async def test_add_server_scope_new(self, repo):
        """Test adding a new server to scope."""
        result = await repo.add_server_scope(
            "/new-server",
            "test-scope",
            ["GET", "POST"],
            ["tool1"]
        )

        assert result is True
        assert len(repo._scopes_data["test-scope"]) == 2

    @pytest.mark.asyncio
    async def test_add_server_scope_update_existing(self, repo):
        """Test updating existing server in scope."""
        result = await repo.add_server_scope(
            "/existing-server",
            "test-scope",
            ["GET", "POST", "DELETE"],
            None
        )

        assert result is True
        # Should still be 1 entry
        assert len(repo._scopes_data["test-scope"]) == 1
        # Methods should be updated
        assert "DELETE" in repo._scopes_data["test-scope"][0]["methods"]

    @pytest.mark.asyncio
    async def test_add_server_scope_nonexistent_scope(self, repo):
        """Test adding server to nonexistent scope."""
        result = await repo.add_server_scope(
            "/new-server",
            "nonexistent-scope",
            ["GET"],
            None
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_add_server_scope_invalid_scope_type(self, repo):
        """Test adding server to scope that's not a list."""
        repo._scopes_data["invalid-scope"] = "not a list"

        result = await repo.add_server_scope(
            "/new-server",
            "invalid-scope",
            ["GET"],
            None
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_server_scope_success(self, repo):
        """Test removing server from scope."""
        result = await repo.remove_server_scope("/existing-server", "test-scope")

        assert result is True
        assert len(repo._scopes_data["test-scope"]) == 0

    @pytest.mark.asyncio
    async def test_remove_server_scope_not_found(self, repo):
        """Test removing server that doesn't exist in scope."""
        result = await repo.remove_server_scope("/nonexistent", "test-scope")

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_server_scope_nonexistent_scope(self, repo):
        """Test removing server from nonexistent scope."""
        result = await repo.remove_server_scope("/server", "nonexistent")

        assert result is False


# =============================================================================
# TEST: FileScopeRepository Group Operations
# =============================================================================


@pytest.mark.unit
class TestFileScopeRepositoryGroupOps:
    """Tests for FileScopeRepository group operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileScopeRepository()
        repo._scopes_file = temp_dir / "scopes.yml"
        repo._scopes_data = {
            "existing-group": [],
            "group_mappings": {},
            "UI-Scopes": {}
        }
        with open(repo._scopes_file, "w") as f:
            yaml.dump(repo._scopes_data, f)
        return repo

    @pytest.mark.asyncio
    async def test_create_group_success(self, repo):
        """Test creating a new group."""
        result = await repo.create_group("new-group", "Test description")

        assert result is True
        assert "new-group" in repo._scopes_data
        assert "new-group" in repo._scopes_data["group_mappings"]
        assert "new-group" in repo._scopes_data["UI-Scopes"]

    @pytest.mark.asyncio
    async def test_create_group_already_exists(self, repo):
        """Test creating group that already exists."""
        result = await repo.create_group("existing-group")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_group_success(self, repo):
        """Test deleting a group."""
        result = await repo.delete_group("existing-group")

        assert result is True
        assert "existing-group" not in repo._scopes_data

    @pytest.mark.asyncio
    async def test_delete_group_not_found(self, repo):
        """Test deleting nonexistent group."""
        result = await repo.delete_group("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_group_removes_from_mappings(self, repo):
        """Test that deleting group removes it from mappings."""
        repo._scopes_data["group_mappings"]["admin"] = ["existing-group"]

        result = await repo.delete_group("existing-group", remove_from_mappings=True)

        assert result is True
        assert "existing-group" not in repo._scopes_data["group_mappings"]["admin"]

    @pytest.mark.asyncio
    async def test_group_exists_true(self, repo):
        """Test group_exists returns True for existing group."""
        result = await repo.group_exists("existing-group")

        assert result is True

    @pytest.mark.asyncio
    async def test_group_exists_false(self, repo):
        """Test group_exists returns False for nonexistent group."""
        result = await repo.group_exists("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_group_success(self, repo):
        """Test getting group details."""
        result = await repo.get_group("existing-group")

        assert result is not None
        assert result["scope_name"] == "existing-group"

    @pytest.mark.asyncio
    async def test_get_group_not_found(self, repo):
        """Test getting nonexistent group."""
        result = await repo.get_group("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_groups(self, repo):
        """Test listing all groups."""
        result = await repo.list_groups()

        assert result["total_count"] == 1
        assert "existing-group" in result["groups"]

    @pytest.mark.asyncio
    async def test_import_group_success(self, repo):
        """Test importing a complete group definition."""
        result = await repo.import_group(
            "imported-group",
            description="Imported group",
            server_access=[{"server": "test", "methods": ["GET"]}],
            group_mappings=["imported-group", "other"],
            ui_permissions={"list_service": ["test"]}
        )

        assert result is True
        assert "imported-group" in repo._scopes_data
        assert len(repo._scopes_data["imported-group"]) == 1


# =============================================================================
# TEST: FileScopeRepository UI Scopes Operations
# =============================================================================


@pytest.mark.unit
class TestFileScopeRepositoryUIScopes:
    """Tests for FileScopeRepository UI scopes operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileScopeRepository()
        repo._scopes_file = temp_dir / "scopes.yml"
        repo._scopes_data = {
            "UI-Scopes": {
                "test-group": {"list_service": ["server1"]}
            }
        }
        with open(repo._scopes_file, "w") as f:
            yaml.dump(repo._scopes_data, f)
        return repo

    @pytest.mark.asyncio
    async def test_add_server_to_ui_scopes_new(self, repo):
        """Test adding new server to UI scopes."""
        result = await repo.add_server_to_ui_scopes("test-group", "server2")

        assert result is True
        assert "server2" in repo._scopes_data["UI-Scopes"]["test-group"]["list_service"]

    @pytest.mark.asyncio
    async def test_add_server_to_ui_scopes_already_exists(self, repo):
        """Test adding server that already exists."""
        result = await repo.add_server_to_ui_scopes("test-group", "server1")

        assert result is True
        # Count should still be 1
        assert repo._scopes_data["UI-Scopes"]["test-group"]["list_service"].count("server1") == 1

    @pytest.mark.asyncio
    async def test_add_server_to_ui_scopes_new_group(self, repo):
        """Test adding server to new group in UI scopes."""
        result = await repo.add_server_to_ui_scopes("new-group", "server1")

        assert result is True
        assert "new-group" in repo._scopes_data["UI-Scopes"]

    @pytest.mark.asyncio
    async def test_remove_server_from_ui_scopes_success(self, repo):
        """Test removing server from UI scopes."""
        result = await repo.remove_server_from_ui_scopes("test-group", "server1")

        assert result is True
        assert "server1" not in repo._scopes_data["UI-Scopes"]["test-group"]["list_service"]

    @pytest.mark.asyncio
    async def test_remove_server_from_ui_scopes_not_found(self, repo):
        """Test removing server not in UI scopes."""
        result = await repo.remove_server_from_ui_scopes("test-group", "nonexistent")

        assert result is False


# =============================================================================
# TEST: FileScopeRepository Group Mappings Operations
# =============================================================================


@pytest.mark.unit
class TestFileScopeRepositoryGroupMappings:
    """Tests for FileScopeRepository group mappings operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileScopeRepository()
        repo._scopes_file = temp_dir / "scopes.yml"
        repo._scopes_data = {
            "group_mappings": {
                "test-group": ["scope1"]
            }
        }
        with open(repo._scopes_file, "w") as f:
            yaml.dump(repo._scopes_data, f)
        return repo

    @pytest.mark.asyncio
    async def test_add_group_mapping_new(self, repo):
        """Test adding new group mapping."""
        result = await repo.add_group_mapping("test-group", "scope2")

        assert result is True
        assert "scope2" in repo._scopes_data["group_mappings"]["test-group"]

    @pytest.mark.asyncio
    async def test_add_group_mapping_already_exists(self, repo):
        """Test adding mapping that already exists."""
        result = await repo.add_group_mapping("test-group", "scope1")

        assert result is True
        # Should still be 1
        assert repo._scopes_data["group_mappings"]["test-group"].count("scope1") == 1

    @pytest.mark.asyncio
    async def test_add_group_mapping_new_group(self, repo):
        """Test adding mapping to new group."""
        result = await repo.add_group_mapping("new-group", "scope1")

        assert result is True
        assert "new-group" in repo._scopes_data["group_mappings"]

    @pytest.mark.asyncio
    async def test_remove_group_mapping_success(self, repo):
        """Test removing group mapping."""
        result = await repo.remove_group_mapping("test-group", "scope1")

        assert result is True
        assert "scope1" not in repo._scopes_data["group_mappings"]["test-group"]

    @pytest.mark.asyncio
    async def test_remove_group_mapping_not_found(self, repo):
        """Test removing mapping that doesn't exist."""
        result = await repo.remove_group_mapping("test-group", "nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_all_group_mappings(self, repo):
        """Test getting all group mappings."""
        result = await repo.get_all_group_mappings()

        assert "test-group" in result
        assert "scope1" in result["test-group"]


# =============================================================================
# TEST: FileScopeRepository Bulk Operations
# =============================================================================


@pytest.mark.unit
class TestFileScopeRepositoryBulkOps:
    """Tests for FileScopeRepository bulk operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileScopeRepository()
        repo._scopes_file = temp_dir / "scopes.yml"
        repo._scopes_data = {
            "scope1": [],
            "scope2": [],
            "mcp-servers-unrestricted/read": [
                {"server": "test-server", "methods": ["GET"]}
            ]
        }
        with open(repo._scopes_file, "w") as f:
            yaml.dump(repo._scopes_data, f)
        return repo

    @pytest.mark.asyncio
    async def test_add_server_to_multiple_scopes(self, repo):
        """Test adding server to multiple scopes."""
        result = await repo.add_server_to_multiple_scopes(
            "/new-server",
            ["scope1", "scope2"],
            ["GET", "POST"],
            ["tool1"]
        )

        assert result is True
        assert len(repo._scopes_data["scope1"]) == 1
        assert len(repo._scopes_data["scope2"]) == 1

    @pytest.mark.asyncio
    async def test_add_server_to_multiple_scopes_partial_failure(self, repo):
        """Test adding server with some invalid scopes."""
        result = await repo.add_server_to_multiple_scopes(
            "/new-server",
            ["scope1", "nonexistent"],
            ["GET"],
            []
        )

        assert result is False
        # scope1 should still have been added
        assert len(repo._scopes_data["scope1"]) == 1

    @pytest.mark.asyncio
    async def test_remove_server_from_all_scopes(self, repo):
        """Test removing server from all standard scopes."""
        result = await repo.remove_server_from_all_scopes("/test-server")

        assert result is True
        assert len(repo._scopes_data["mcp-servers-unrestricted/read"]) == 0

    @pytest.mark.asyncio
    async def test_remove_server_from_all_scopes_not_found(self, repo):
        """Test removing server not in any scopes."""
        result = await repo.remove_server_from_all_scopes("/nonexistent")

        assert result is False
