"""
Unit tests for registry.repositories.file.peer_federation_repository module.

Tests the file-based peer federation repository implementation.
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from registry.repositories.file.peer_federation_repository import (
    FilePeerFederationRepository,
    _validate_peer_id,
    _get_safe_file_path,
)
from registry.schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
)


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def peers_dir(temp_dir):
    """Create peers directory."""
    peers = temp_dir / "peers"
    peers.mkdir(parents=True, exist_ok=True)
    return peers


@pytest.fixture
def sync_state_file(temp_dir):
    """Create sync state file path."""
    return temp_dir / "sync_state.json"


@pytest.fixture
def repository(peers_dir, sync_state_file):
    """Create repository instance."""
    return FilePeerFederationRepository(
        peers_dir=peers_dir,
        sync_state_file=sync_state_file
    )


@pytest.fixture
def sample_peer_config():
    """Create sample peer configuration."""
    return PeerRegistryConfig(
        peer_id="test-peer",
        name="Test Peer",
        endpoint="https://test-peer.example.com",
        enabled=True,
        sync_mode="all",
    )


@pytest.fixture
def sample_sync_status():
    """Create sample sync status."""
    return PeerSyncStatus(
        peer_id="test-peer",
        is_healthy=True,
        last_successful_sync="2024-01-01T00:00:00Z",
        total_servers_synced=10,
        total_agents_synced=5,
        current_generation=1,
    )


# =============================================================================
# TEST: _validate_peer_id
# =============================================================================


@pytest.mark.unit
class TestValidatePeerId:
    """Tests for the _validate_peer_id function."""

    def test_valid_peer_id(self):
        """Test valid peer IDs pass validation."""
        # Should not raise
        _validate_peer_id("valid-peer-id")
        _validate_peer_id("peer123")
        _validate_peer_id("test_peer")

    def test_empty_peer_id(self):
        """Test empty peer ID raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_peer_id("")

    def test_path_traversal_double_dot(self):
        """Test path traversal with .. is rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            _validate_peer_id("../etc/passwd")

    def test_path_traversal_forward_slash(self):
        """Test path traversal with / is rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            _validate_peer_id("path/to/peer")

    def test_path_traversal_backslash(self):
        """Test path traversal with \\ is rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            _validate_peer_id("path\\to\\peer")

    def test_invalid_char_less_than(self):
        """Test invalid character < is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer<test")

    def test_invalid_char_greater_than(self):
        """Test invalid character > is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer>test")

    def test_invalid_char_colon(self):
        """Test invalid character : is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer:test")

    def test_invalid_char_pipe(self):
        """Test invalid character | is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer|test")

    def test_reserved_name_con(self):
        """Test reserved name 'con' is rejected."""
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("con")

    def test_reserved_name_prn(self):
        """Test reserved name 'prn' is rejected."""
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("PRN")

    def test_reserved_name_aux(self):
        """Test reserved name 'aux' is rejected."""
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("AUX")

    def test_reserved_name_nul(self):
        """Test reserved name 'nul' is rejected."""
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("nul")


# =============================================================================
# TEST: _get_safe_file_path
# =============================================================================


@pytest.mark.unit
class TestGetSafeFilePath:
    """Tests for the _get_safe_file_path function."""

    def test_valid_peer_id(self, peers_dir):
        """Test valid peer ID returns correct path."""
        result = _get_safe_file_path("test-peer", peers_dir)

        assert result == peers_dir / "test-peer.json"

    def test_invalid_peer_id(self, peers_dir):
        """Test invalid peer ID raises ValueError."""
        with pytest.raises(ValueError):
            _get_safe_file_path("../test", peers_dir)


# =============================================================================
# TEST: FilePeerFederationRepository.__init__
# =============================================================================


@pytest.mark.unit
class TestFilePeerFederationRepositoryInit:
    """Tests for repository initialization."""

    def test_init_creates_directory(self, temp_dir, sync_state_file):
        """Test that initialization creates the peers directory."""
        peers_dir = temp_dir / "new_peers_dir"
        assert not peers_dir.exists()

        repo = FilePeerFederationRepository(
            peers_dir=peers_dir,
            sync_state_file=sync_state_file
        )

        assert peers_dir.exists()

    def test_init_with_defaults(self, temp_dir):
        """Test initialization with default settings."""
        mock_settings = MagicMock()
        mock_settings.peers_dir = temp_dir / "peers"
        mock_settings.peer_sync_state_file_path = temp_dir / "sync.json"

        with patch("registry.repositories.file.peer_federation_repository.settings", mock_settings):
            repo = FilePeerFederationRepository()

            assert repo._peers_dir == mock_settings.peers_dir
            assert repo._sync_state_file == mock_settings.peer_sync_state_file_path


# =============================================================================
# TEST: get_peer
# =============================================================================


@pytest.mark.unit
class TestGetPeer:
    """Tests for the get_peer method."""

    @pytest.mark.asyncio
    async def test_get_existing_peer(self, repository, peers_dir, sample_peer_config):
        """Test getting an existing peer."""
        # Write peer config to file
        file_path = peers_dir / "test-peer.json"
        with open(file_path, "w") as f:
            json.dump(sample_peer_config.model_dump(mode="json"), f)

        result = await repository.get_peer("test-peer")

        assert result is not None
        assert result.peer_id == "test-peer"
        assert result.name == "Test Peer"

    @pytest.mark.asyncio
    async def test_get_nonexistent_peer(self, repository):
        """Test getting a nonexistent peer returns None."""
        result = await repository.get_peer("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_peer_invalid_id(self, repository):
        """Test getting peer with invalid ID returns None."""
        result = await repository.get_peer("../invalid")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_peer_invalid_json(self, repository, peers_dir):
        """Test getting peer with invalid JSON returns None."""
        file_path = peers_dir / "bad-json.json"
        with open(file_path, "w") as f:
            f.write("invalid json {{{")

        result = await repository.get_peer("bad-json")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_peer_adds_missing_peer_id(self, repository, peers_dir):
        """Test that get_peer adds missing peer_id from filename."""
        file_path = peers_dir / "no-id-peer.json"
        data = {
            "name": "No ID Peer",
            "endpoint": "https://example.com",
            "enabled": True,
            
            
        }
        with open(file_path, "w") as f:
            json.dump(data, f)

        result = await repository.get_peer("no-id-peer")

        assert result is not None
        assert result.peer_id == "no-id-peer"


# =============================================================================
# TEST: list_peers
# =============================================================================


@pytest.mark.unit
class TestListPeers:
    """Tests for the list_peers method."""

    @pytest.mark.asyncio
    async def test_list_empty(self, repository):
        """Test listing peers when directory is empty."""
        result = await repository.list_peers()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_multiple_peers(self, repository, peers_dir):
        """Test listing multiple peers."""
        # Create two peer files
        for i in range(2):
            file_path = peers_dir / f"peer-{i}.json"
            data = {
                "peer_id": f"peer-{i}",
                "name": f"Peer {i}",
                "endpoint": f"https://peer{i}.example.com",
                "enabled": True,
                
                
            }
            with open(file_path, "w") as f:
                json.dump(data, f)

        result = await repository.list_peers()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_filter_enabled(self, repository, peers_dir):
        """Test listing peers filtered by enabled status."""
        # Create enabled peer
        enabled_file = peers_dir / "enabled.json"
        with open(enabled_file, "w") as f:
            json.dump({
                "peer_id": "enabled",
                "name": "Enabled",
                "endpoint": "https://enabled.example.com",
                "enabled": True,
                
                
            }, f)

        # Create disabled peer
        disabled_file = peers_dir / "disabled.json"
        with open(disabled_file, "w") as f:
            json.dump({
                "peer_id": "disabled",
                "name": "Disabled",
                "endpoint": "https://disabled.example.com",
                "enabled": False,
                
                
            }, f)

        enabled_result = await repository.list_peers(enabled=True)
        assert len(enabled_result) == 1
        assert enabled_result[0].peer_id == "enabled"

        disabled_result = await repository.list_peers(enabled=False)
        assert len(disabled_result) == 1
        assert disabled_result[0].peer_id == "disabled"

    @pytest.mark.asyncio
    async def test_list_skips_sync_state_file(self, repository, peers_dir, sync_state_file):
        """Test that list_peers skips sync state file."""
        # Create peer file
        peer_file = peers_dir / "peer.json"
        with open(peer_file, "w") as f:
            json.dump({
                "peer_id": "peer",
                "name": "Peer",
                "endpoint": "https://peer.example.com",
                "enabled": True,
                
                
            }, f)

        result = await repository.list_peers()

        # Should only have the peer file, not sync state
        assert len(result) == 1
        assert result[0].peer_id == "peer"

    @pytest.mark.asyncio
    async def test_list_skips_invalid_files(self, repository, peers_dir):
        """Test that list_peers skips invalid JSON files."""
        # Create valid peer
        valid_file = peers_dir / "valid.json"
        with open(valid_file, "w") as f:
            json.dump({
                "peer_id": "valid",
                "name": "Valid",
                "endpoint": "https://valid.example.com",
                "enabled": True,
                
                
            }, f)

        # Create invalid file
        invalid_file = peers_dir / "invalid.json"
        with open(invalid_file, "w") as f:
            f.write("invalid json")

        result = await repository.list_peers()

        assert len(result) == 1
        assert result[0].peer_id == "valid"


# =============================================================================
# TEST: save_peer
# =============================================================================


@pytest.mark.unit
class TestSavePeer:
    """Tests for the save_peer method."""

    @pytest.mark.asyncio
    async def test_save_new_peer(self, repository, peers_dir, sample_peer_config):
        """Test saving a new peer."""
        result = await repository.save_peer(sample_peer_config)

        assert result.peer_id == "test-peer"

        # Verify file was created
        file_path = peers_dir / "test-peer.json"
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, repository, peers_dir, sample_peer_config):
        """Test updating an existing peer."""
        # Save initial
        await repository.save_peer(sample_peer_config)

        # Update
        updated = PeerRegistryConfig(
            peer_id="test-peer",
            name="Updated Peer",
            endpoint="https://updated.example.com",
            enabled=False,
            sync_mode="all",
        )

        result = await repository.save_peer(updated)

        assert result.name == "Updated Peer"

        # Verify file was updated
        file_path = peers_dir / "test-peer.json"
        with open(file_path, "r") as f:
            data = json.load(f)
        assert data["name"] == "Updated Peer"
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_save_invalid_peer_id(self, repository):
        """Test saving peer with invalid ID raises error."""
        # Skip validation in the schema by using model_construct
        invalid_peer = PeerRegistryConfig.model_construct(
            peer_id="../invalid",
            name="Invalid",
            endpoint="https://invalid.example.com",
            enabled=True,
            sync_mode="all",
        )

        with pytest.raises(ValueError):
            await repository.save_peer(invalid_peer)


# =============================================================================
# TEST: delete_peer
# =============================================================================


@pytest.mark.unit
class TestDeletePeer:
    """Tests for the delete_peer method."""

    @pytest.mark.asyncio
    async def test_delete_existing_peer(self, repository, peers_dir, sample_peer_config):
        """Test deleting an existing peer."""
        # Save first
        await repository.save_peer(sample_peer_config)

        file_path = peers_dir / "test-peer.json"
        assert file_path.exists()

        result = await repository.delete_peer("test-peer")

        assert result is True
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_peer(self, repository):
        """Test deleting a nonexistent peer returns False."""
        result = await repository.delete_peer("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_invalid_peer_id(self, repository):
        """Test deleting peer with invalid ID returns False."""
        result = await repository.delete_peer("../invalid")

        assert result is False


# =============================================================================
# TEST: get_sync_state
# =============================================================================


@pytest.mark.unit
class TestGetSyncState:
    """Tests for the get_sync_state method."""

    @pytest.mark.asyncio
    async def test_get_existing_sync_state(self, repository, sync_state_file, sample_sync_status):
        """Test getting existing sync state."""
        # Write sync state file
        states = {
            "test-peer": sample_sync_status.model_dump(mode="json")
        }
        with open(sync_state_file, "w") as f:
            json.dump(states, f)

        result = await repository.get_sync_state("test-peer")

        assert result is not None
        assert result.peer_id == "test-peer"
        assert result.is_healthy is True

    @pytest.mark.asyncio
    async def test_get_nonexistent_sync_state(self, repository, sync_state_file):
        """Test getting nonexistent sync state returns None."""
        # Write sync state file without target peer
        with open(sync_state_file, "w") as f:
            json.dump({}, f)

        result = await repository.get_sync_state("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_sync_state_no_file(self, repository):
        """Test getting sync state when file doesn't exist."""
        result = await repository.get_sync_state("test-peer")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_sync_state_invalid_json(self, repository, sync_state_file):
        """Test getting sync state with invalid JSON returns None."""
        with open(sync_state_file, "w") as f:
            f.write("invalid json")

        result = await repository.get_sync_state("test-peer")

        assert result is None


# =============================================================================
# TEST: save_sync_state
# =============================================================================


@pytest.mark.unit
class TestSaveSyncState:
    """Tests for the save_sync_state method."""

    @pytest.mark.asyncio
    async def test_save_new_sync_state(self, repository, sync_state_file, sample_sync_status):
        """Test saving new sync state."""
        result = await repository.save_sync_state("test-peer", sample_sync_status)

        assert result is True
        assert sync_state_file.exists()

        with open(sync_state_file, "r") as f:
            data = json.load(f)
        assert "test-peer" in data

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, repository, sync_state_file, sample_sync_status):
        """Test updating existing sync state."""
        # Save initial
        await repository.save_sync_state("test-peer", sample_sync_status)

        # Update
        updated_status = PeerSyncStatus(
            peer_id="test-peer",
            is_healthy=False,
            last_sync_attempt="2024-01-02T00:00:00Z",
            total_servers_synced=0,
            total_agents_synced=0,
            consecutive_failures=1,
        )

        result = await repository.save_sync_state("test-peer", updated_status)

        assert result is True

        with open(sync_state_file, "r") as f:
            data = json.load(f)
        assert data["test-peer"]["is_healthy"] is False


# =============================================================================
# TEST: delete_sync_state
# =============================================================================


@pytest.mark.unit
class TestDeleteSyncState:
    """Tests for the delete_sync_state method."""

    @pytest.mark.asyncio
    async def test_delete_existing_sync_state(self, repository, sync_state_file, sample_sync_status):
        """Test deleting existing sync state."""
        # Save first
        await repository.save_sync_state("test-peer", sample_sync_status)

        result = await repository.delete_sync_state("test-peer")

        assert result is True

        with open(sync_state_file, "r") as f:
            data = json.load(f)
        assert "test-peer" not in data

    @pytest.mark.asyncio
    async def test_delete_nonexistent_sync_state(self, repository, sync_state_file):
        """Test deleting nonexistent sync state returns False."""
        # Write empty sync state
        with open(sync_state_file, "w") as f:
            json.dump({}, f)

        result = await repository.delete_sync_state("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_sync_state_no_file(self, repository):
        """Test deleting sync state when file doesn't exist."""
        result = await repository.delete_sync_state("test-peer")

        assert result is False


# =============================================================================
# TEST: list_all_sync_states
# =============================================================================


@pytest.mark.unit
class TestListAllSyncStates:
    """Tests for the list_all_sync_states method."""

    @pytest.mark.asyncio
    async def test_list_empty(self, repository):
        """Test listing sync states when file doesn't exist."""
        result = await repository.list_all_sync_states()

        assert result == {}

    @pytest.mark.asyncio
    async def test_list_multiple_states(self, repository, sync_state_file):
        """Test listing multiple sync states."""
        states = {
            "peer-1": {
                "status": "success",
                "last_sync_at": "2024-01-01T00:00:00Z",
                "servers_synced": 5,
                "agents_synced": 3
            },
            "peer-2": {
                "status": "failed",
                "last_sync_at": "2024-01-02T00:00:00Z",
                "servers_synced": 0,
                "agents_synced": 0
            }
        }
        with open(sync_state_file, "w") as f:
            json.dump(states, f)

        result = await repository.list_all_sync_states()

        assert len(result) == 2
        assert "peer-1" in result
        assert "peer-2" in result

    @pytest.mark.asyncio
    async def test_list_skips_invalid_states(self, repository, sync_state_file):
        """Test that list_all_sync_states skips invalid state entries."""
        states = {
            "valid-peer": {
                "status": "success",
                "last_sync_at": "2024-01-01T00:00:00Z",
                "servers_synced": 5,
                "agents_synced": 3
            },
            "invalid-peer": "not a dict"  # Invalid format
        }
        with open(sync_state_file, "w") as f:
            json.dump(states, f)

        result = await repository.list_all_sync_states()

        assert len(result) == 1
        assert "valid-peer" in result

    @pytest.mark.asyncio
    async def test_list_invalid_json(self, repository, sync_state_file):
        """Test listing sync states with invalid JSON returns empty dict."""
        with open(sync_state_file, "w") as f:
            f.write("invalid json")

        result = await repository.list_all_sync_states()

        assert result == {}


# =============================================================================
# TEST: load_all
# =============================================================================


@pytest.mark.unit
class TestLoadAll:
    """Tests for the load_all method."""

    @pytest.mark.asyncio
    async def test_load_all_creates_directory(self, temp_dir, sync_state_file):
        """Test that load_all creates the peers directory if needed."""
        peers_dir = temp_dir / "new_peers"

        repo = FilePeerFederationRepository(
            peers_dir=peers_dir,
            sync_state_file=sync_state_file
        )

        await repo.load_all()

        assert peers_dir.exists()

    @pytest.mark.asyncio
    async def test_load_all_counts_files(self, repository, peers_dir):
        """Test that load_all correctly counts peer files."""
        # Create some peer files
        for i in range(3):
            file_path = peers_dir / f"peer-{i}.json"
            with open(file_path, "w") as f:
                json.dump({
                    "peer_id": f"peer-{i}",
                    "name": f"Peer {i}",
                    "endpoint": f"https://peer{i}.example.com",
                    "enabled": True,
                    
                    
                }, f)

        # Should not raise
        await repository.load_all()

    @pytest.mark.asyncio
    async def test_load_all_with_sync_states(self, repository, sync_state_file):
        """Test load_all loads sync states if file exists."""
        states = {
            "peer-1": {
                "status": "success",
                "last_sync_at": "2024-01-01T00:00:00Z",
                "servers_synced": 5,
                "agents_synced": 3
            }
        }
        with open(sync_state_file, "w") as f:
            json.dump(states, f)

        # Should not raise
        await repository.load_all()
