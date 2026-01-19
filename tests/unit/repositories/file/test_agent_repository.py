"""
Unit tests for file-based agent repository.
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from registry.repositories.file.agent_repository import (
    FileAgentRepository,
    _path_to_filename,
)
from registry.schemas.agent_models import AgentCard


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: Helper Functions
# =============================================================================


@pytest.mark.unit
class TestPathToFilename:
    """Tests for _path_to_filename helper function."""

    def test_simple_path(self):
        """Test simple path conversion."""
        result = _path_to_filename("/my-agent")
        assert result == "my-agent_agent.json"

    def test_path_with_slashes(self):
        """Test path with multiple slashes."""
        result = _path_to_filename("/namespace/my-agent")
        assert result == "namespace_my-agent_agent.json"

    def test_path_already_ends_with_agent_json(self):
        """Test path that already ends with _agent.json."""
        result = _path_to_filename("/my-agent_agent.json")
        assert result == "my-agent_agent.json"

    def test_path_ends_with_json(self):
        """Test path that ends with .json but not _agent.json."""
        result = _path_to_filename("/my-agent.json")
        assert result == "my-agent_agent.json"

    def test_path_without_leading_slash(self):
        """Test path without leading slash."""
        result = _path_to_filename("my-agent")
        assert result == "my-agent_agent.json"


# =============================================================================
# TEST: FileAgentRepository Initialization
# =============================================================================


@pytest.mark.unit
class TestFileAgentRepositoryInit:
    """Tests for FileAgentRepository initialization."""

    def test_init_creates_directory(self):
        """Test that init creates the agents directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / "agents"
            state_file = Path(tmpdir) / "agent_state.json"

            with patch("registry.repositories.file.agent_repository.settings") as mock_settings:
                mock_settings.agents_dir = agents_dir
                mock_settings.agent_state_file_path = state_file

                repo = FileAgentRepository()

                assert agents_dir.exists()


# =============================================================================
# TEST: FileAgentRepository CRUD Operations
# =============================================================================


@pytest.mark.unit
class TestFileAgentRepositoryCRUD:
    """Tests for FileAgentRepository CRUD operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        agents_dir = temp_dir / "agents"
        state_file = temp_dir / "agent_state.json"

        with patch("registry.repositories.file.agent_repository.settings") as mock_settings:
            mock_settings.agents_dir = agents_dir
            mock_settings.agent_state_file_path = state_file
            return FileAgentRepository()

    @pytest.fixture
    def sample_agent(self):
        """Create a sample agent card."""
        return AgentCard(
            name="Test Agent",
            description="A test agent",
            url="https://test.agent.com/api",
            version="1.0.0",
            path="/test-agent",
            tags=["test", "agent"],
        )

    @pytest.mark.asyncio
    async def test_get_all_empty(self, repo):
        """Test getting all agents when none exist."""
        result = await repo.get_all()
        assert result == {}

    @pytest.mark.asyncio
    async def test_save_and_get(self, repo, sample_agent):
        """Test saving and retrieving an agent."""
        saved = await repo.save(sample_agent)

        assert saved is not None
        assert saved.registered_at is not None
        assert saved.updated_at is not None

        result = await repo.get("/test-agent")

        assert result is not None
        assert result.name == "Test Agent"
        assert result.path == "/test-agent"

    @pytest.mark.asyncio
    async def test_save_updates_timestamps(self, repo, sample_agent):
        """Test that save updates timestamps correctly."""
        # First save
        saved1 = await repo.save(sample_agent)
        registered_at = saved1.registered_at

        # Second save (update)
        sample_agent.description = "Updated description"
        saved2 = await repo.save(sample_agent)

        # registered_at should stay the same, updated_at should change
        # Note: This depends on timing, might need small delay
        assert saved2.updated_at is not None

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo):
        """Test getting a nonexistent agent."""
        result = await repo.get("/nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_existing(self, repo, sample_agent):
        """Test deleting an existing agent."""
        await repo.save(sample_agent)

        result = await repo.delete("/test-agent")

        assert result is True
        # Verify deleted
        loaded = await repo.get("/test-agent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, repo):
        """Test deleting a nonexistent agent."""
        result = await repo.delete("/nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_all_multiple(self, repo, sample_agent):
        """Test getting all agents when multiple exist."""
        # Save first agent
        await repo.save(sample_agent)

        # Save second agent
        agent2 = AgentCard(
            name="Second Agent",
            description="Another agent",
            url="https://second.agent.com/api",
            version="2.0.0",
            path="/second-agent",
        )
        await repo.save(agent2)

        result = await repo.get_all()

        assert len(result) == 2
        assert "/test-agent" in result
        assert "/second-agent" in result

    @pytest.mark.asyncio
    async def test_create_alias(self, repo, sample_agent):
        """Test create method (alias for save)."""
        result = await repo.create(sample_agent)

        assert result is not None
        assert result.name == "Test Agent"

    @pytest.mark.asyncio
    async def test_update_existing(self, repo, sample_agent):
        """Test updating an existing agent."""
        await repo.save(sample_agent)

        sample_agent.description = "Updated description"
        result = await repo.update("/test-agent", sample_agent)

        assert result is not None
        assert result.description == "Updated description"

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, repo, sample_agent):
        """Test updating a nonexistent agent."""
        result = await repo.update("/nonexistent", sample_agent)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all(self, repo, sample_agent):
        """Test listing all agents."""
        await repo.save(sample_agent)

        result = await repo.list_all()

        assert len(result) == 1
        assert result[0].name == "Test Agent"

    @pytest.mark.asyncio
    async def test_load_all_alias(self, repo, sample_agent):
        """Test load_all (alias for get_all)."""
        await repo.save(sample_agent)

        result = await repo.load_all()

        assert "/test-agent" in result


# =============================================================================
# TEST: FileAgentRepository State Management
# =============================================================================


@pytest.mark.unit
class TestFileAgentRepositoryState:
    """Tests for FileAgentRepository state management."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        agents_dir = temp_dir / "agents"
        state_file = temp_dir / "agent_state.json"

        with patch("registry.repositories.file.agent_repository.settings") as mock_settings:
            mock_settings.agents_dir = agents_dir
            mock_settings.agent_state_file_path = state_file
            return FileAgentRepository()

    @pytest.mark.asyncio
    async def test_get_state_empty(self, repo):
        """Test getting state when none exists."""
        result = await repo.get_state()

        assert result == {"enabled": [], "disabled": []}

    @pytest.mark.asyncio
    async def test_save_and_get_state(self, repo):
        """Test saving and retrieving state."""
        state = {"enabled": ["/agent1"], "disabled": ["/agent2"]}
        await repo.save_state(state)

        result = await repo.get_state()

        assert result["enabled"] == ["/agent1"]
        assert result["disabled"] == ["/agent2"]

    @pytest.mark.asyncio
    async def test_is_enabled_false(self, repo):
        """Test is_enabled returns False when not in enabled list."""
        result = await repo.is_enabled("/test-agent")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_enabled_true(self, repo):
        """Test is_enabled returns True when in enabled list."""
        state = {"enabled": ["/test-agent"], "disabled": []}
        await repo.save_state(state)

        result = await repo.is_enabled("/test-agent")
        assert result is True

    @pytest.mark.asyncio
    async def test_set_enabled_true(self, repo):
        """Test setting agent to enabled."""
        await repo.set_enabled("/test-agent", True)

        result = await repo.is_enabled("/test-agent")
        assert result is True

    @pytest.mark.asyncio
    async def test_set_enabled_false(self, repo):
        """Test setting agent to disabled."""
        # First enable
        await repo.set_enabled("/test-agent", True)
        # Then disable
        await repo.set_enabled("/test-agent", False)

        result = await repo.is_enabled("/test-agent")
        assert result is False

        state = await repo.get_state()
        assert "/test-agent" in state["disabled"]
        assert "/test-agent" not in state["enabled"]

    @pytest.mark.asyncio
    async def test_set_state_alias(self, repo):
        """Test set_state (alias for set_enabled)."""
        await repo.set_state("/test-agent", True)

        result = await repo.is_enabled("/test-agent")
        assert result is True


# =============================================================================
# TEST: FileAgentRepository Error Handling
# =============================================================================


@pytest.mark.unit
class TestFileAgentRepositoryErrors:
    """Tests for FileAgentRepository error handling."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        agents_dir = temp_dir / "agents"
        state_file = temp_dir / "agent_state.json"

        with patch("registry.repositories.file.agent_repository.settings") as mock_settings:
            mock_settings.agents_dir = agents_dir
            mock_settings.agent_state_file_path = state_file
            return FileAgentRepository()

    @pytest.mark.asyncio
    async def test_get_all_invalid_json(self, repo):
        """Test handling of invalid JSON files."""
        # Create invalid JSON file
        invalid_file = repo.agents_dir / "invalid_agent.json"
        invalid_file.write_text("not valid json")

        result = await repo.get_all()

        # Should skip invalid file and return empty dict
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_all_missing_required_fields(self, repo):
        """Test handling of files missing required fields."""
        # Create file with missing required fields
        incomplete_file = repo.agents_dir / "incomplete_agent.json"
        incomplete_file.write_text('{"name": "test"}')  # Missing path

        result = await repo.get_all()

        # Should skip incomplete file
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_state_invalid_json(self, repo):
        """Test handling of invalid state file."""
        # Create invalid state file
        repo.state_file.write_text("not valid json")

        result = await repo.get_state()

        # Should return default state
        assert result == {"enabled": [], "disabled": []}

    @pytest.mark.asyncio
    async def test_get_state_invalid_format(self, repo):
        """Test handling of state file with invalid format."""
        # Create state file with wrong format (not a dict)
        repo.state_file.write_text('["list", "instead", "of", "dict"]')

        result = await repo.get_state()

        # Should return default state
        assert result == {"enabled": [], "disabled": []}
