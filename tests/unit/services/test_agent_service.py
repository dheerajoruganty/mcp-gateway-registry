"""
Unit tests for registry.services.agent_service module.

This module tests the AgentService class which manages A2A agent registration,
state management, ratings, and file-based storage operations.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from registry.services.agent_service import (
    AgentService,
    _load_agent_from_file,
    _load_state_file,
    _path_to_filename,
    _persist_state_to_disk,
    _save_agent_to_disk,
)
from tests.fixtures.constants import (
    TEST_AGENT_NAME_1,
    TEST_AGENT_NAME_2,
    TEST_AGENT_PATH_1,
    TEST_AGENT_PATH_2,
    TEST_AGENT_URL_1,
    TEST_AGENT_URL_2,
    TEST_USERNAME,
    TRUST_UNVERIFIED,
    VISIBILITY_PUBLIC,
)
from tests.fixtures.factories import AgentCardFactory

logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def agent_service(
    mock_settings,
) -> AgentService:
    """
    Create a fresh AgentService instance with mocked settings.

    Args:
        mock_settings: Mocked settings fixture

    Returns:
        AgentService instance
    """
    service = AgentService()
    return service


@pytest.fixture
def sample_agent_dict() -> dict[str, Any]:
    """
    Create a sample agent dictionary for testing.

    Returns:
        Dictionary with sample agent data
    """
    return {
        "protocol_version": "1.0",
        "name": TEST_AGENT_NAME_1,
        "description": "A test agent for unit tests",
        "url": TEST_AGENT_URL_1,
        "version": "1.0",
        "path": TEST_AGENT_PATH_1,
        "capabilities": {"streaming": False, "tools": True},
        "default_input_modes": ["text/plain"],
        "default_output_modes": ["text/plain"],
        "skills": [
            {
                "id": "skill-1",
                "name": "Data Processing",
                "description": "Process data efficiently",
                "tags": ["data", "processing"],
            }
        ],
        "tags": ["test", "data"],
        "is_enabled": False,
        "num_stars": 0.0,
        "rating_details": [],
        "license": "MIT",
        "visibility": VISIBILITY_PUBLIC,
        "trust_level": TRUST_UNVERIFIED,
    }


@pytest.fixture
def sample_agent_dict_2() -> dict[str, Any]:
    """
    Create a second sample agent dictionary for testing.

    Returns:
        Dictionary with sample agent data
    """
    return {
        "protocol_version": "1.0",
        "name": TEST_AGENT_NAME_2,
        "description": "Another test agent",
        "url": TEST_AGENT_URL_2,
        "version": "2.0",
        "path": TEST_AGENT_PATH_2,
        "capabilities": {"streaming": True},
        "default_input_modes": ["text/plain"],
        "default_output_modes": ["application/json"],
        "skills": [],
        "tags": ["test"],
        "is_enabled": False,
        "num_stars": 4.5,
        "rating_details": [],
        "license": "Apache-2.0",
        "visibility": VISIBILITY_PUBLIC,
        "trust_level": TRUST_UNVERIFIED,
    }


@pytest.fixture
def agent_json_files(
    tmp_path: Path,
    sample_agent_dict: dict[str, Any],
) -> Path:
    """
    Create sample JSON agent files in tmp_path.

    Args:
        tmp_path: Temporary directory path
        sample_agent_dict: Sample agent data

    Returns:
        Path to agents directory with JSON files
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Create a valid agent file
    agent_file = agents_dir / "test_agent_1_agent.json"
    with open(agent_file, "w") as f:
        json.dump(sample_agent_dict, f, indent=2)

    # Create another valid agent file
    agent_2 = {
        "protocol_version": "1.0",
        "name": TEST_AGENT_NAME_2,
        "description": "Another agent",
        "url": TEST_AGENT_URL_2,
        "version": "1.0",
        "path": TEST_AGENT_PATH_2,
        "capabilities": {},
        "default_input_modes": ["text/plain"],
        "default_output_modes": ["text/plain"],
        "skills": [],
        "tags": [],
        "is_enabled": False,
        "num_stars": 0.0,
        "rating_details": [],
    }
    agent_file_2 = agents_dir / "test_agent_2_agent.json"
    with open(agent_file_2, "w") as f:
        json.dump(agent_2, f, indent=2)

    # Create an invalid agent file (missing required fields)
    invalid_file = agents_dir / "invalid_agent.json"
    with open(invalid_file, "w") as f:
        json.dump({"invalid": "data"}, f)

    # Create a malformed JSON file
    malformed_file = agents_dir / "malformed_agent.json"
    with open(malformed_file, "w") as f:
        f.write("{invalid json")

    # Create agent_state.json (should be excluded from loading)
    state_file = agents_dir / "agent_state.json"
    with open(state_file, "w") as f:
        json.dump({"enabled": [], "disabled": []}, f)

    return agents_dir


@pytest.fixture
def agent_state_file(
    tmp_path: Path,
) -> Path:
    """
    Create an agent state file with test data.

    Args:
        tmp_path: Temporary directory path

    Returns:
        Path to agent_state.json
    """
    state_file = tmp_path / "agent_state.json"
    state_data = {
        "enabled": [TEST_AGENT_PATH_1],
        "disabled": [TEST_AGENT_PATH_2],
    }
    with open(state_file, "w") as f:
        json.dump(state_data, f, indent=2)

    return state_file


# =============================================================================
# TEST: Helper Functions - Path to Filename Conversion
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestPathToFilename:
    """Test _path_to_filename helper function."""

    def test_converts_simple_path(self):
        """Test conversion of simple agent path."""
        # Arrange
        path = "/code-reviewer"

        # Act
        result = _path_to_filename(path)

        # Assert
        assert result == "code-reviewer_agent.json"

    def test_converts_nested_path(self):
        """Test conversion of nested agent path."""
        # Arrange
        path = "/agents/data/processor"

        # Act
        result = _path_to_filename(path)

        # Assert
        assert result == "agents_data_processor_agent.json"

    def test_handles_path_with_trailing_slash(self):
        """Test conversion of path with trailing slash."""
        # Arrange
        path = "/agent/"

        # Act
        result = _path_to_filename(path)

        # Assert
        # Trailing slash results in double underscore
        assert result == "agent__agent.json"

    def test_handles_path_already_with_json(self):
        """Test conversion when path already ends with .json."""
        # Arrange
        path = "/agent.json"

        # Act
        result = _path_to_filename(path)

        # Assert
        assert result == "agent_agent.json"

    def test_handles_path_already_with_agent_json(self):
        """Test conversion when path already ends with _agent.json."""
        # Arrange
        path = "/my_agent_agent.json"

        # Act
        result = _path_to_filename(path)

        # Assert
        # Should keep the _agent.json suffix
        assert result == "my_agent_agent.json"


# =============================================================================
# TEST: Helper Functions - Load Agent from File
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestLoadAgentFromFile:
    """Test _load_agent_from_file helper function."""

    def test_loads_valid_agent_file(
        self,
        tmp_path: Path,
        sample_agent_dict: dict[str, Any],
    ):
        """Test loading a valid agent JSON file."""
        # Arrange
        agent_file = tmp_path / "test_agent.json"
        with open(agent_file, "w") as f:
            json.dump(sample_agent_dict, f)

        # Act
        result = _load_agent_from_file(agent_file)

        # Assert
        assert result is not None
        assert result["name"] == TEST_AGENT_NAME_1
        assert result["path"] == TEST_AGENT_PATH_1

    def test_returns_none_for_missing_file(
        self,
        tmp_path: Path,
    ):
        """Test loading a non-existent file returns None."""
        # Arrange
        agent_file = tmp_path / "missing.json"

        # Act
        result = _load_agent_from_file(agent_file)

        # Assert
        assert result is None

    def test_returns_none_for_invalid_json(
        self,
        tmp_path: Path,
    ):
        """Test loading malformed JSON returns None."""
        # Arrange
        agent_file = tmp_path / "invalid.json"
        with open(agent_file, "w") as f:
            f.write("{invalid json")

        # Act
        result = _load_agent_from_file(agent_file)

        # Assert
        assert result is None

    def test_returns_none_for_missing_required_fields(
        self,
        tmp_path: Path,
    ):
        """Test loading file with missing required fields returns None."""
        # Arrange
        agent_file = tmp_path / "incomplete.json"
        with open(agent_file, "w") as f:
            json.dump({"description": "Missing name and path"}, f)

        # Act
        result = _load_agent_from_file(agent_file)

        # Assert
        assert result is None

    def test_returns_none_for_non_dict_data(
        self,
        tmp_path: Path,
    ):
        """Test loading file with non-dict data returns None."""
        # Arrange
        agent_file = tmp_path / "not_dict.json"
        with open(agent_file, "w") as f:
            json.dump(["not", "a", "dict"], f)

        # Act
        result = _load_agent_from_file(agent_file)

        # Assert
        assert result is None


# =============================================================================
# TEST: Helper Functions - Load and Persist State
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestLoadStateFile:
    """Test _load_state_file helper function."""

    def test_loads_valid_state_file(
        self,
        agent_state_file: Path,
    ):
        """Test loading a valid state file."""
        # Act
        result = _load_state_file(agent_state_file)

        # Assert
        assert "enabled" in result
        assert "disabled" in result
        assert TEST_AGENT_PATH_1 in result["enabled"]
        assert TEST_AGENT_PATH_2 in result["disabled"]

    def test_returns_empty_state_for_missing_file(
        self,
        tmp_path: Path,
    ):
        """Test loading missing state file returns empty state."""
        # Arrange
        missing_file = tmp_path / "missing_state.json"

        # Act
        result = _load_state_file(missing_file)

        # Assert
        assert result == {"enabled": [], "disabled": []}

    def test_returns_empty_state_for_invalid_json(
        self,
        tmp_path: Path,
    ):
        """Test loading malformed state file returns empty state."""
        # Arrange
        invalid_file = tmp_path / "invalid_state.json"
        with open(invalid_file, "w") as f:
            f.write("{not valid json")

        # Act
        result = _load_state_file(invalid_file)

        # Assert
        assert result == {"enabled": [], "disabled": []}

    def test_initializes_missing_keys(
        self,
        tmp_path: Path,
    ):
        """Test loading state file with missing keys initializes them."""
        # Arrange
        partial_state = tmp_path / "partial_state.json"
        with open(partial_state, "w") as f:
            json.dump({"enabled": [TEST_AGENT_PATH_1]}, f)

        # Act
        result = _load_state_file(partial_state)

        # Assert
        assert "enabled" in result
        assert "disabled" in result
        assert result["disabled"] == []

    def test_handles_non_dict_state(
        self,
        tmp_path: Path,
    ):
        """Test loading state file with non-dict data returns empty state."""
        # Arrange
        bad_state = tmp_path / "bad_state.json"
        with open(bad_state, "w") as f:
            json.dump(["not", "a", "dict"], f)

        # Act
        result = _load_state_file(bad_state)

        # Assert
        assert result == {"enabled": [], "disabled": []}


@pytest.mark.unit
@pytest.mark.agents
class TestPersistStateToDisk:
    """Test _persist_state_to_disk helper function."""

    def test_persists_state_successfully(
        self,
        tmp_path: Path,
    ):
        """Test persisting state to disk."""
        # Arrange
        state_file = tmp_path / "state.json"
        state_data = {
            "enabled": [TEST_AGENT_PATH_1],
            "disabled": [TEST_AGENT_PATH_2],
        }

        # Act
        _persist_state_to_disk(state_data, state_file)

        # Assert
        assert state_file.exists()
        with open(state_file) as f:
            loaded_state = json.load(f)
        assert loaded_state == state_data

    def test_creates_parent_directory(
        self,
        tmp_path: Path,
    ):
        """Test that persist creates parent directory if missing."""
        # Arrange
        nested_dir = tmp_path / "nested" / "dirs"
        state_file = nested_dir / "state.json"
        state_data = {"enabled": [], "disabled": []}

        # Act
        _persist_state_to_disk(state_data, state_file)

        # Assert
        assert state_file.exists()
        assert nested_dir.exists()


# =============================================================================
# TEST: Helper Functions - Save Agent to Disk
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestSaveAgentToDisk:
    """Test _save_agent_to_disk helper function."""

    def test_saves_agent_successfully(
        self,
        tmp_path: Path,
    ):
        """Test saving agent card to disk."""
        # Arrange
        agents_dir = tmp_path / "agents"
        agent_card = AgentCardFactory(path=TEST_AGENT_PATH_1)

        # Act
        result = _save_agent_to_disk(agent_card, agents_dir)

        # Assert
        assert result is True
        assert agents_dir.exists()

        # Verify file exists
        expected_filename = _path_to_filename(TEST_AGENT_PATH_1)
        agent_file = agents_dir / expected_filename
        assert agent_file.exists()

        # Verify content
        with open(agent_file) as f:
            loaded_data = json.load(f)
        assert loaded_data["name"] == agent_card.name
        assert loaded_data["path"] == agent_card.path

    def test_creates_directory_if_missing(
        self,
        tmp_path: Path,
    ):
        """Test that save creates directory if it doesn't exist."""
        # Arrange
        agents_dir = tmp_path / "nonexistent" / "agents"
        agent_card = AgentCardFactory(path="/test-agent")

        # Act
        result = _save_agent_to_disk(agent_card, agents_dir)

        # Assert
        assert result is True
        assert agents_dir.exists()

    def test_handles_save_error_gracefully(
        self,
        tmp_path: Path,
    ):
        """Test that save handles errors gracefully."""
        # Arrange
        # Create a read-only directory to trigger write error
        agents_dir = tmp_path / "readonly"
        agents_dir.mkdir()
        agent_card = AgentCardFactory(path="/test")

        # Make directory read-only (this works on Unix-like systems)
        try:
            agents_dir.chmod(0o444)

            # Act
            result = _save_agent_to_disk(agent_card, agents_dir)

            # Assert
            assert result is False

        finally:
            # Restore permissions for cleanup
            agents_dir.chmod(0o755)


# =============================================================================
# TEST: AgentService Instantiation
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestAgentServiceInstantiation:
    """Test AgentService initialization and basic properties."""

    def test_init_creates_empty_registries(
        self,
        agent_service: AgentService,
    ):
        """Test that __init__ creates empty registries."""
        # Assert
        assert agent_service.registered_agents == {}
        assert agent_service.agent_state == {"enabled": [], "disabled": []}

    def test_init_does_not_load_agents(
        self,
        agent_service: AgentService,
    ):
        """Test that __init__ does not automatically load agents."""
        # Assert - should be empty until load_agents_and_state is called
        assert len(agent_service.registered_agents) == 0
        assert len(agent_service.agent_state["enabled"]) == 0
        assert len(agent_service.agent_state["disabled"]) == 0


# =============================================================================
# TEST: Loading Agents and State
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestLoadAgentsAndState:
    """Test loading agent cards and state from disk."""

    def test_load_agents_from_empty_directory(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test loading agents when directory is empty."""
        # Act
        agent_service.load_agents_and_state()

        # Assert
        assert agent_service.registered_agents == {}
        assert agent_service.agent_state == {"enabled": [], "disabled": []}

    def test_load_agents_creates_directory_if_missing(
        self,
        agent_service: AgentService,
        tmp_path: Path,
        mock_settings,
    ):
        """Test that load_agents_and_state creates agents dir if missing."""
        # Arrange
        agents_dir = tmp_path / "nonexistent" / "agents"
        type(mock_settings).agents_dir = property(lambda self: agents_dir)

        # Act
        agent_service.load_agents_and_state()

        # Assert
        assert agents_dir.exists()

    def test_load_agents_from_files(
        self,
        agent_service: AgentService,
        agent_json_files: Path,
        mock_settings,
    ):
        """Test loading agents from JSON files."""
        # Arrange
        type(mock_settings).agents_dir = property(lambda self: agent_json_files)
        type(mock_settings).agent_state_file_path = property(
            lambda self: agent_json_files / "agent_state.json"
        )

        # Act
        agent_service.load_agents_and_state()

        # Assert
        # Should load 2 valid agents (test_agent_1 and test_agent_2)
        # Invalid and malformed files should be skipped
        assert len(agent_service.registered_agents) == 2
        assert TEST_AGENT_PATH_1 in agent_service.registered_agents
        assert TEST_AGENT_PATH_2 in agent_service.registered_agents

    def test_load_agents_excludes_state_file(
        self,
        agent_service: AgentService,
        agent_json_files: Path,
        mock_settings,
    ):
        """Test that agent_state.json is not loaded as an agent."""
        # Arrange
        type(mock_settings).agents_dir = property(lambda self: agent_json_files)
        type(mock_settings).agent_state_file_path = property(
            lambda self: agent_json_files / "agent_state.json"
        )

        # Act
        agent_service.load_agents_and_state()

        # Assert
        # Verify state file exists but wasn't loaded as an agent
        state_file = agent_json_files / "agent_state.json"
        assert state_file.exists()
        assert "agent_state" not in str(agent_service.registered_agents)

    def test_load_agents_handles_duplicate_paths(
        self,
        agent_service: AgentService,
        tmp_path: Path,
        mock_settings,
        sample_agent_dict: dict[str, Any],
    ):
        """Test loading agents with duplicate paths overwrites previous."""
        # Arrange
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        # Create two files with same path
        for i in range(2):
            agent_file = agents_dir / f"duplicate_{i}_agent.json"
            with open(agent_file, "w") as f:
                json.dump(sample_agent_dict, f)

        type(mock_settings).agents_dir = property(lambda self: agents_dir)
        type(mock_settings).agent_state_file_path = property(
            lambda self: agents_dir / "agent_state.json"
        )

        # Act
        agent_service.load_agents_and_state()

        # Assert
        # Should have only one agent despite two files
        assert len(agent_service.registered_agents) == 1
        assert TEST_AGENT_PATH_1 in agent_service.registered_agents

    def test_load_agents_initializes_disabled_state_for_new_agents(
        self,
        agent_service: AgentService,
        agent_json_files: Path,
        mock_settings,
    ):
        """Test that new agents are added to disabled list by default."""
        # Arrange
        type(mock_settings).agents_dir = property(lambda self: agent_json_files)
        type(mock_settings).agent_state_file_path = property(
            lambda self: agent_json_files / "agent_state.json"
        )

        # Act
        agent_service.load_agents_and_state()

        # Assert
        # All agents should be in disabled list (since state file was empty)
        assert len(agent_service.agent_state["disabled"]) == 2
        assert TEST_AGENT_PATH_1 in agent_service.agent_state["disabled"]
        assert TEST_AGENT_PATH_2 in agent_service.agent_state["disabled"]


# =============================================================================
# TEST: Register Agent
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestRegisterAgent:
    """Test agent registration."""

    def test_register_new_agent_successfully(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test registering a new agent."""
        # Arrange
        agent_card = AgentCardFactory(path="/new-agent")

        # Act
        result = agent_service.register_agent(agent_card)

        # Assert
        assert result == agent_card
        assert "/new-agent" in agent_service.registered_agents
        assert "/new-agent" in agent_service.agent_state["disabled"]

    def test_register_agent_sets_timestamps(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that registration sets registered_at and updated_at."""
        # Arrange
        agent_card = AgentCardFactory(
            path="/test-agent",
            registered_at=None,
            updated_at=None,
        )

        # Act
        result = agent_service.register_agent(agent_card)

        # Assert
        assert result.registered_at is not None
        assert result.updated_at is not None
        assert isinstance(result.registered_at, datetime)
        assert isinstance(result.updated_at, datetime)

    def test_register_agent_preserves_existing_timestamps(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that registration preserves existing timestamps."""
        # Arrange
        original_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        agent_card = AgentCardFactory(
            path="/test-agent",
            registered_at=original_time,
            updated_at=original_time,
        )

        # Act
        result = agent_service.register_agent(agent_card)

        # Assert
        assert result.registered_at == original_time
        assert result.updated_at == original_time

    def test_register_agent_fails_for_duplicate_path(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that registering duplicate path raises ValueError."""
        # Arrange
        agent_card_1 = AgentCardFactory(path="/duplicate")
        agent_service.register_agent(agent_card_1)

        agent_card_2 = AgentCardFactory(path="/duplicate")

        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            agent_service.register_agent(agent_card_2)

    def test_register_agent_defaults_to_disabled(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that newly registered agents are disabled by default."""
        # Arrange
        agent_card = AgentCardFactory(path="/new-agent")

        # Act
        agent_service.register_agent(agent_card)

        # Assert
        assert "/new-agent" in agent_service.agent_state["disabled"]
        assert "/new-agent" not in agent_service.agent_state["enabled"]


# =============================================================================
# TEST: Get Agent
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestGetAgent:
    """Test retrieving agents."""

    def test_get_existing_agent(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test getting an existing agent."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        result = agent_service.get_agent("/test-agent")

        # Assert
        assert result.path == "/test-agent"
        assert result.name == agent_card.name

    def test_get_agent_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test getting a non-existent agent raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            agent_service.get_agent("/nonexistent")

    def test_get_agent_handles_trailing_slash(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test getting agent with/without trailing slash."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act - try with trailing slash
        result = agent_service.get_agent("/test-agent/")

        # Assert
        assert result.path == "/test-agent"

    def test_get_agent_with_slash_registered_without(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test getting agent registered with slash when querying without."""
        # Arrange
        # Note: AgentCard doesn't allow trailing slash except for root
        # So we manually add to registry to test the lookup logic
        agent_card = AgentCardFactory(path="/test-agent")
        # Manually register with trailing slash to test edge case
        agent_service.registered_agents["/test-agent/"] = agent_card

        # Act
        result = agent_service.get_agent("/test-agent")

        # Assert
        # Should find agent despite slash mismatch
        assert result is not None
        assert result.name == agent_card.name


# =============================================================================
# TEST: List Agents
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestListAgents:
    """Test listing all agents."""

    def test_list_agents_empty(
        self,
        agent_service: AgentService,
    ):
        """Test listing agents when none are registered."""
        # Act
        result = agent_service.list_agents()

        # Assert
        assert result == []

    def test_list_agents_returns_all(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test listing all registered agents."""
        # Arrange
        agent_1 = AgentCardFactory(path="/agent-1")
        agent_2 = AgentCardFactory(path="/agent-2")
        agent_service.register_agent(agent_1)
        agent_service.register_agent(agent_2)

        # Act
        result = agent_service.list_agents()

        # Assert
        assert len(result) == 2
        paths = [a.path for a in result]
        assert "/agent-1" in paths
        assert "/agent-2" in paths

    def test_get_all_agents_alias(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that get_all_agents is an alias for list_agents."""
        # Arrange
        agent = AgentCardFactory(path="/test")
        agent_service.register_agent(agent)

        # Act
        list_result = agent_service.list_agents()
        get_all_result = agent_service.get_all_agents()

        # Assert
        assert list_result == get_all_result


# =============================================================================
# TEST: Update Agent
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestUpdateAgent:
    """Test updating agent information."""

    def test_update_agent_successfully(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test updating an agent's information."""
        # Arrange
        agent_card = AgentCardFactory(
            path="/test-agent",
            description="Original description",
        )
        agent_service.register_agent(agent_card)

        updates = {"description": "Updated description"}

        # Act
        result = agent_service.update_agent("/test-agent", updates)

        # Assert
        assert result.description == "Updated description"
        assert result.path == "/test-agent"  # Path should not change

    def test_update_agent_updates_timestamp(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that update sets updated_at timestamp."""
        # Arrange
        original_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        agent_card = AgentCardFactory(
            path="/test-agent",
            updated_at=original_time,
        )
        agent_service.register_agent(agent_card)

        # Act
        result = agent_service.update_agent("/test-agent", {"description": "New"})

        # Assert
        assert result.updated_at > original_time

    def test_update_agent_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test updating non-existent agent raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            agent_service.update_agent("/nonexistent", {"description": "test"})

    def test_update_agent_preserves_path(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that path cannot be changed via update."""
        # Arrange
        agent_card = AgentCardFactory(path="/original-path")
        agent_service.register_agent(agent_card)

        # Act
        result = agent_service.update_agent(
            "/original-path",
            {"path": "/new-path", "description": "Updated"},
        )

        # Assert
        # Path should remain unchanged
        assert result.path == "/original-path"
        assert "/original-path" in agent_service.registered_agents

    def test_update_agent_with_invalid_data(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test updating with invalid data raises ValueError."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid"):
            # Try to set num_stars to invalid value
            agent_service.update_agent("/test-agent", {"num_stars": 10.0})


# =============================================================================
# TEST: Delete Agent
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestDeleteAgent:
    """Test agent deletion."""

    def test_delete_agent_successfully(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test deleting an agent."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        result = agent_service.delete_agent("/test-agent")

        # Assert
        assert result is True
        assert "/test-agent" not in agent_service.registered_agents

    def test_delete_agent_removes_from_state(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that delete removes agent from state lists."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)
        agent_service.enable_agent("/test-agent")

        # Act
        agent_service.delete_agent("/test-agent")

        # Assert
        assert "/test-agent" not in agent_service.agent_state["enabled"]
        assert "/test-agent" not in agent_service.agent_state["disabled"]

    def test_delete_agent_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test deleting non-existent agent raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            agent_service.delete_agent("/nonexistent")

    def test_delete_agent_removes_file(
        self,
        agent_service: AgentService,
        tmp_path: Path,
        mock_settings,
    ):
        """Test that delete removes agent file from disk."""
        # Arrange
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        type(mock_settings).agents_dir = property(lambda self: agents_dir)

        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Verify file exists
        filename = _path_to_filename("/test-agent")
        agent_file = agents_dir / filename
        assert agent_file.exists()

        # Act
        agent_service.delete_agent("/test-agent")

        # Assert
        assert not agent_file.exists()

    def test_remove_agent_alias(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that remove_agent is an alias for delete_agent."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        result = agent_service.remove_agent("/test-agent")

        # Assert
        assert result is True
        assert "/test-agent" not in agent_service.registered_agents

    def test_remove_agent_returns_false_for_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test that remove_agent returns False for non-existent agent."""
        # Act
        result = agent_service.remove_agent("/nonexistent")

        # Assert
        assert result is False


# =============================================================================
# TEST: Enable/Disable Agent
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestEnableDisableAgent:
    """Test enabling and disabling agents."""

    def test_enable_agent(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test enabling an agent."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        agent_service.enable_agent("/test-agent")

        # Assert
        assert "/test-agent" in agent_service.agent_state["enabled"]
        assert "/test-agent" not in agent_service.agent_state["disabled"]

    def test_enable_already_enabled_agent(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test enabling an already enabled agent (idempotent)."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)
        agent_service.enable_agent("/test-agent")

        # Act - enable again
        agent_service.enable_agent("/test-agent")

        # Assert
        assert "/test-agent" in agent_service.agent_state["enabled"]
        # Should only appear once
        assert agent_service.agent_state["enabled"].count("/test-agent") == 1

    def test_enable_agent_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test enabling non-existent agent raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            agent_service.enable_agent("/nonexistent")

    def test_disable_agent(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test disabling an agent."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)
        agent_service.enable_agent("/test-agent")

        # Act
        agent_service.disable_agent("/test-agent")

        # Assert
        assert "/test-agent" in agent_service.agent_state["disabled"]
        assert "/test-agent" not in agent_service.agent_state["enabled"]

    def test_disable_already_disabled_agent(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test disabling an already disabled agent (idempotent)."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act - disable again (already disabled by default)
        agent_service.disable_agent("/test-agent")

        # Assert
        assert "/test-agent" in agent_service.agent_state["disabled"]
        # Should only appear once
        assert agent_service.agent_state["disabled"].count("/test-agent") == 1

    def test_disable_agent_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test disabling non-existent agent raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            agent_service.disable_agent("/nonexistent")

    def test_toggle_agent_enable(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test toggling agent to enabled state."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        result = agent_service.toggle_agent("/test-agent", enabled=True)

        # Assert
        assert result is True
        assert "/test-agent" in agent_service.agent_state["enabled"]

    def test_toggle_agent_disable(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test toggling agent to disabled state."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)
        agent_service.enable_agent("/test-agent")

        # Act
        result = agent_service.toggle_agent("/test-agent", enabled=False)

        # Assert
        assert result is True
        assert "/test-agent" in agent_service.agent_state["disabled"]

    def test_toggle_agent_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test toggling non-existent agent returns False."""
        # Act
        result = agent_service.toggle_agent("/nonexistent", enabled=True)

        # Assert
        assert result is False


# =============================================================================
# TEST: Agent State Queries
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestAgentStateQueries:
    """Test querying agent state."""

    def test_is_agent_enabled_true(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test checking if agent is enabled."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)
        agent_service.enable_agent("/test-agent")

        # Act
        result = agent_service.is_agent_enabled("/test-agent")

        # Assert
        assert result is True

    def test_is_agent_enabled_false(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test checking if agent is disabled."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        result = agent_service.is_agent_enabled("/test-agent")

        # Assert
        assert result is False

    def test_is_agent_enabled_handles_trailing_slash(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test is_agent_enabled with trailing slash."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)
        agent_service.enable_agent("/test-agent")

        # Act
        result = agent_service.is_agent_enabled("/test-agent/")

        # Assert
        assert result is True

    def test_get_enabled_agents(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test getting list of enabled agents."""
        # Arrange
        agent_1 = AgentCardFactory(path="/agent-1")
        agent_2 = AgentCardFactory(path="/agent-2")
        agent_service.register_agent(agent_1)
        agent_service.register_agent(agent_2)
        agent_service.enable_agent("/agent-1")

        # Act
        result = agent_service.get_enabled_agents()

        # Assert
        assert len(result) == 1
        assert "/agent-1" in result
        assert "/agent-2" not in result

    def test_get_disabled_agents(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test getting list of disabled agents."""
        # Arrange
        agent_1 = AgentCardFactory(path="/agent-1")
        agent_2 = AgentCardFactory(path="/agent-2")
        agent_service.register_agent(agent_1)
        agent_service.register_agent(agent_2)
        agent_service.enable_agent("/agent-1")

        # Act
        result = agent_service.get_disabled_agents()

        # Assert
        assert len(result) == 1
        assert "/agent-2" in result
        assert "/agent-1" not in result


# =============================================================================
# TEST: Agent Ratings
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestAgentRatings:
    """Test agent rating system."""

    def test_update_rating_first_rating(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test adding first rating to an agent."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent", num_stars=0.0)
        agent_service.register_agent(agent_card)

        # Act
        avg_rating = agent_service.update_rating("/test-agent", TEST_USERNAME, 5)

        # Assert
        assert avg_rating == 5.0
        updated_agent = agent_service.get_agent("/test-agent")
        assert updated_agent.num_stars == 5.0
        assert len(updated_agent.rating_details) == 1
        assert updated_agent.rating_details[0]["user"] == TEST_USERNAME
        assert updated_agent.rating_details[0]["rating"] == 5

    def test_update_rating_multiple_users(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test adding ratings from multiple users."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        agent_service.update_rating("/test-agent", "user1", 5)
        agent_service.update_rating("/test-agent", "user2", 3)
        avg_rating = agent_service.update_rating("/test-agent", "user3", 4)

        # Assert
        assert avg_rating == 4.0  # (5 + 3 + 4) / 3
        updated_agent = agent_service.get_agent("/test-agent")
        assert len(updated_agent.rating_details) == 3

    def test_update_rating_same_user_updates(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that same user's rating is updated, not appended."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        agent_service.update_rating("/test-agent", TEST_USERNAME, 5)
        avg_rating = agent_service.update_rating("/test-agent", TEST_USERNAME, 3)

        # Assert
        assert avg_rating == 3.0
        updated_agent = agent_service.get_agent("/test-agent")
        assert len(updated_agent.rating_details) == 1  # Only one entry
        assert updated_agent.rating_details[0]["rating"] == 3  # Updated value

    def test_update_rating_maintains_max_ratings(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that rating_details maintains max 100 entries."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act - add 101 ratings from different users
        for i in range(101):
            agent_service.update_rating("/test-agent", f"user{i}", 5)

        # Assert
        updated_agent = agent_service.get_agent("/test-agent")
        assert len(updated_agent.rating_details) == 100  # Max 100 entries
        # Oldest entry (user0) should be removed
        users = [r["user"] for r in updated_agent.rating_details]
        assert "user0" not in users
        assert "user100" in users

    def test_update_rating_invalid_value_low(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that rating below 1 raises ValueError."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act & Assert
        with pytest.raises(ValueError, match="between 1 and 5"):
            agent_service.update_rating("/test-agent", TEST_USERNAME, 0)

    def test_update_rating_invalid_value_high(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that rating above 5 raises ValueError."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act & Assert
        with pytest.raises(ValueError, match="between 1 and 5"):
            agent_service.update_rating("/test-agent", TEST_USERNAME, 6)

    def test_update_rating_invalid_type(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that non-integer rating raises ValueError."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act & Assert
        with pytest.raises(ValueError, match="must be an integer"):
            agent_service.update_rating("/test-agent", TEST_USERNAME, 4.5)

    def test_update_rating_agent_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test rating non-existent agent raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            agent_service.update_rating("/nonexistent", TEST_USERNAME, 5)


# =============================================================================
# TEST: Get Agent Info (Nullable Variant)
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestGetAgentInfo:
    """Test get_agent_info which returns None instead of raising."""

    def test_get_agent_info_existing(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test get_agent_info returns agent for existing path."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Act
        result = agent_service.get_agent_info("/test-agent")

        # Assert
        assert result is not None
        assert result.path == "/test-agent"

    def test_get_agent_info_not_found(
        self,
        agent_service: AgentService,
    ):
        """Test get_agent_info returns None for non-existent agent."""
        # Act
        result = agent_service.get_agent_info("/nonexistent")

        # Assert
        assert result is None


# =============================================================================
# TEST: Index Agent (FAISS Integration)
# =============================================================================


@pytest.mark.unit
@pytest.mark.agents
class TestIndexAgent:
    """Test agent indexing for FAISS search."""

    @pytest.mark.asyncio
    async def test_index_agent_calls_faiss_service(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that index_agent calls FAISS service."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Mock the faiss_service import that happens inside index_agent
        mock_faiss = MagicMock()
        with patch.dict("sys.modules", {"registry.search.service": Mock(faiss_service=mock_faiss)}):
            # Act
            await agent_service.index_agent(agent_card)

            # Assert
            mock_faiss.add_or_update_entity.assert_called_once()
            call_kwargs = mock_faiss.add_or_update_entity.call_args.kwargs
            assert call_kwargs["entity_path"] == "/test-agent"
            assert call_kwargs["entity_type"] == "a2a_agent"
            assert "entity_info" in call_kwargs

    @pytest.mark.asyncio
    async def test_index_agent_handles_error(
        self,
        agent_service: AgentService,
        mock_settings,
    ):
        """Test that index_agent handles FAISS errors gracefully."""
        # Arrange
        agent_card = AgentCardFactory(path="/test-agent")
        agent_service.register_agent(agent_card)

        # Mock FAISS service to raise error
        mock_faiss = MagicMock()
        mock_faiss.add_or_update_entity.side_effect = Exception("FAISS error")

        with patch.dict("sys.modules", {"registry.search.service": Mock(faiss_service=mock_faiss)}):
            # Act - should not raise
            await agent_service.index_agent(agent_card)

            # Assert - agent should still be in registry
            assert "/test-agent" in agent_service.registered_agents
