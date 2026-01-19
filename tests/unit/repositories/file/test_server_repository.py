"""
Unit tests for file-based server repository.
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from registry.repositories.file.server_repository import FileServerRepository


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: FileServerRepository Initialization
# =============================================================================


@pytest.mark.unit
class TestFileServerRepositoryInit:
    """Tests for FileServerRepository initialization."""

    def test_init_creates_empty_dicts(self):
        """Test that init creates empty dictionaries."""
        repo = FileServerRepository()

        assert repo._servers == {}
        assert repo._state == {}


# =============================================================================
# TEST: FileServerRepository Path to Filename
# =============================================================================


@pytest.mark.unit
class TestPathToFilename:
    """Tests for _path_to_filename method."""

    def test_simple_path(self):
        """Test simple path conversion."""
        repo = FileServerRepository()
        result = repo._path_to_filename("/my-server")
        assert result == "my-server.json"

    def test_path_with_slashes(self):
        """Test path with multiple slashes."""
        repo = FileServerRepository()
        result = repo._path_to_filename("/namespace/my-server")
        assert result == "namespace_my-server.json"

    def test_path_already_ends_with_json(self):
        """Test path that already ends with .json."""
        repo = FileServerRepository()
        result = repo._path_to_filename("/my-server.json")
        assert result == "my-server.json"

    def test_path_without_leading_slash(self):
        """Test path without leading slash."""
        repo = FileServerRepository()
        result = repo._path_to_filename("my-server")
        assert result == "my-server.json"


# =============================================================================
# TEST: FileServerRepository Load All
# =============================================================================


@pytest.mark.unit
class TestFileServerRepositoryLoadAll:
    """Tests for FileServerRepository load_all method."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo_with_dir(self, temp_dir):
        """Create a repository with a temporary directory."""
        repo = FileServerRepository()
        servers_dir = temp_dir / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)
        state_file = temp_dir / "state.json"

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file
            yield repo, servers_dir, state_file

    @pytest.mark.asyncio
    async def test_load_all_empty_directory(self, repo_with_dir):
        """Test loading when directory is empty."""
        repo, servers_dir, state_file = repo_with_dir

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            await repo.load_all()

        assert repo._servers == {}

    @pytest.mark.asyncio
    async def test_load_all_with_valid_servers(self, repo_with_dir):
        """Test loading valid server files."""
        repo, servers_dir, state_file = repo_with_dir

        # Create valid server file
        server_data = {
            "path": "/test-server",
            "server_name": "Test Server",
            "description": "A test server"
        }
        server_file = servers_dir / "test-server.json"
        with open(server_file, "w") as f:
            json.dump(server_data, f)

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            await repo.load_all()

        assert "/test-server" in repo._servers
        assert repo._servers["/test-server"]["server_name"] == "Test Server"

    @pytest.mark.asyncio
    async def test_load_all_with_state_file(self, repo_with_dir):
        """Test loading with existing state file."""
        repo, servers_dir, state_file = repo_with_dir

        # Create server file
        server_data = {
            "path": "/test-server",
            "server_name": "Test Server"
        }
        server_file = servers_dir / "test-server.json"
        with open(server_file, "w") as f:
            json.dump(server_data, f)

        # Create state file
        state_data = {"/test-server": True}
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            await repo.load_all()

        assert repo._state["/test-server"] is True

    @pytest.mark.asyncio
    async def test_load_all_skips_invalid_json(self, repo_with_dir):
        """Test that invalid JSON files are skipped."""
        repo, servers_dir, state_file = repo_with_dir

        # Create invalid JSON file
        invalid_file = servers_dir / "invalid.json"
        invalid_file.write_text("not valid json")

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            await repo.load_all()

        assert repo._servers == {}

    @pytest.mark.asyncio
    async def test_load_all_skips_state_file(self, repo_with_dir):
        """Test that state file is not loaded as a server."""
        repo, servers_dir, state_file = repo_with_dir

        # Create state file in servers directory
        state_data = {"some": "state"}
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            await repo.load_all()

        assert repo._servers == {}


# =============================================================================
# TEST: FileServerRepository CRUD Operations
# =============================================================================


@pytest.mark.unit
class TestFileServerRepositoryCRUD:
    """Tests for FileServerRepository CRUD operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileServerRepository()
        servers_dir = temp_dir / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)
        state_file = temp_dir / "state.json"
        repo._servers_dir = servers_dir
        repo._state_file = state_file
        return repo

    @pytest.fixture
    def sample_server(self):
        """Create a sample server info."""
        return {
            "path": "/test-server",
            "server_name": "Test Server",
            "description": "A test server",
            "tags": ["test"],
        }

    @pytest.mark.asyncio
    async def test_get_existing(self, temp_dir):
        """Test getting an existing server."""
        repo = FileServerRepository()
        repo._servers = {
            "/test-server": {"path": "/test-server", "server_name": "Test"}
        }

        result = await repo.get("/test-server")

        assert result is not None
        assert result["server_name"] == "Test"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        """Test getting a nonexistent server."""
        repo = FileServerRepository()
        repo._servers = {}

        result = await repo.get("/nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_trailing_slash(self):
        """Test getting server with trailing slash handling."""
        repo = FileServerRepository()
        repo._servers = {
            "/test-server": {"path": "/test-server", "server_name": "Test"}
        }

        result = await repo.get("/test-server/")

        assert result is not None
        assert result["server_name"] == "Test"

    @pytest.mark.asyncio
    async def test_get_without_trailing_slash(self):
        """Test getting server without trailing slash when stored with slash."""
        repo = FileServerRepository()
        repo._servers = {
            "/test-server/": {"path": "/test-server/", "server_name": "Test"}
        }

        result = await repo.get("/test-server")

        assert result is not None
        assert result["server_name"] == "Test"

    @pytest.mark.asyncio
    async def test_list_all(self):
        """Test listing all servers."""
        repo = FileServerRepository()
        repo._servers = {
            "/server1": {"path": "/server1", "server_name": "Server 1"},
            "/server2": {"path": "/server2", "server_name": "Server 2"},
        }

        result = await repo.list_all()

        assert len(result) == 2
        assert "/server1" in result
        assert "/server2" in result

    @pytest.mark.asyncio
    async def test_create_success(self, temp_dir):
        """Test creating a new server."""
        repo = FileServerRepository()
        servers_dir = temp_dir / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)
        state_file = temp_dir / "state.json"

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            server_info = {
                "path": "/new-server",
                "server_name": "New Server",
                "description": "A new server",
            }

            result = await repo.create(server_info)

        assert result is True
        assert "/new-server" in repo._servers
        assert repo._state["/new-server"] is False

    @pytest.mark.asyncio
    async def test_create_duplicate(self, temp_dir):
        """Test creating a duplicate server fails."""
        repo = FileServerRepository()
        repo._servers = {"/existing": {"path": "/existing", "server_name": "Existing"}}

        server_info = {"path": "/existing", "server_name": "Duplicate"}

        result = await repo.create(server_info)

        assert result is False

    @pytest.mark.asyncio
    async def test_update_success(self, temp_dir):
        """Test updating an existing server."""
        repo = FileServerRepository()
        servers_dir = temp_dir / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)

        repo._servers = {"/test-server": {"path": "/test-server", "server_name": "Old Name"}}

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir

            server_info = {"server_name": "New Name", "description": "Updated"}

            result = await repo.update("/test-server", server_info)

        assert result is True
        assert repo._servers["/test-server"]["server_name"] == "New Name"

    @pytest.mark.asyncio
    async def test_update_nonexistent(self):
        """Test updating a nonexistent server fails."""
        repo = FileServerRepository()
        repo._servers = {}

        server_info = {"server_name": "New Server"}

        result = await repo.update("/nonexistent", server_info)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_success(self, temp_dir):
        """Test deleting an existing server."""
        repo = FileServerRepository()
        servers_dir = temp_dir / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)
        state_file = temp_dir / "state.json"

        # Create server file
        server_file = servers_dir / "test-server.json"
        server_file.write_text('{"path": "/test-server", "server_name": "Test"}')

        repo._servers = {"/test-server": {"path": "/test-server", "server_name": "Test"}}
        repo._state = {"/test-server": True}

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            result = await repo.delete("/test-server")

        assert result is True
        assert "/test-server" not in repo._servers
        assert "/test-server" not in repo._state

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        """Test deleting a nonexistent server fails."""
        repo = FileServerRepository()
        repo._servers = {}

        result = await repo.delete("/nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, temp_dir):
        """Test deleting when file doesn't exist on disk."""
        repo = FileServerRepository()
        servers_dir = temp_dir / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)
        state_file = temp_dir / "state.json"

        # Server in memory but file doesn't exist
        repo._servers = {"/test-server": {"path": "/test-server", "server_name": "Test"}}
        repo._state = {"/test-server": True}

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            result = await repo.delete("/test-server")

        # Should still succeed (remove from memory)
        assert result is True


# =============================================================================
# TEST: FileServerRepository State Operations
# =============================================================================


@pytest.mark.unit
class TestFileServerRepositoryState:
    """Tests for FileServerRepository state operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_get_state_existing(self):
        """Test getting state for existing server."""
        repo = FileServerRepository()
        repo._state = {"/test-server": True}

        result = await repo.get_state("/test-server")

        assert result is True

    @pytest.mark.asyncio
    async def test_get_state_nonexistent(self):
        """Test getting state for nonexistent server."""
        repo = FileServerRepository()
        repo._state = {}

        result = await repo.get_state("/nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_state_trailing_slash(self):
        """Test getting state with trailing slash handling."""
        repo = FileServerRepository()
        repo._state = {"/test-server": True}

        result = await repo.get_state("/test-server/")

        assert result is True

    @pytest.mark.asyncio
    async def test_set_state_success(self, temp_dir):
        """Test setting server state."""
        repo = FileServerRepository()
        repo._servers = {"/test-server": {"path": "/test-server", "server_name": "Test"}}
        repo._state = {}
        state_file = temp_dir / "state.json"

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.state_file_path = state_file

            result = await repo.set_state("/test-server", True)

        assert result is True
        assert repo._state["/test-server"] is True

    @pytest.mark.asyncio
    async def test_set_state_nonexistent_server(self):
        """Test setting state for nonexistent server fails."""
        repo = FileServerRepository()
        repo._servers = {}

        result = await repo.set_state("/nonexistent", True)

        assert result is False


# =============================================================================
# TEST: FileServerRepository Load State Edge Cases
# =============================================================================


@pytest.mark.unit
class TestFileServerRepositoryLoadState:
    """Tests for FileServerRepository _load_state method edge cases."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.mark.asyncio
    async def test_load_state_invalid_format(self, temp_dir):
        """Test loading state with invalid format (not a dict)."""
        repo = FileServerRepository()
        servers_dir = temp_dir / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)
        state_file = temp_dir / "state.json"

        # Create state file with invalid format
        state_file.write_text('["list", "not", "dict"]')

        repo._servers = {"/test": {"path": "/test", "server_name": "Test"}}

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            await repo._load_state()

        # State should be initialized but server state should be None/False
        assert repo._state.get("/test") is None or repo._state.get("/test") is False

    @pytest.mark.asyncio
    async def test_load_state_error_handling(self, temp_dir):
        """Test load state error handling."""
        repo = FileServerRepository()
        servers_dir = temp_dir / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)
        state_file = temp_dir / "state.json"

        # Create invalid JSON
        state_file.write_text("not valid json")

        repo._servers = {"/test": {"path": "/test", "server_name": "Test"}}

        with patch("registry.repositories.file.server_repository.settings") as mock_settings:
            mock_settings.servers_dir = servers_dir
            mock_settings.state_file_path = state_file

            # Should not raise
            await repo._load_state()

        # State should default to empty
        assert repo._state.get("/test") is None or repo._state.get("/test") is False
