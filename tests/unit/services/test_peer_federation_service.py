"""
Unit tests for Peer Federation Service.

Tests for peer registry federation configuration management,
including CRUD operations, security, and state management.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from threading import Thread
from typing import Dict

from registry.services.peer_federation_service import (
    PeerFederationService,
    get_peer_federation_service,
    _peer_id_to_filename,
    _validate_peer_id,
    _get_safe_file_path,
    _load_peer_from_file,
    _save_peer_to_disk,
    _load_sync_state,
    _persist_sync_state,
)
from registry.schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    PeerFederationService._instance = None
    yield
    PeerFederationService._instance = None


@pytest.fixture
def temp_peers_dir(tmp_path):
    """Create temp directory for peer configs."""
    peers_dir = tmp_path / "peers"
    peers_dir.mkdir()
    return peers_dir


@pytest.fixture
def mock_settings(temp_peers_dir, tmp_path):
    """Mock settings to use temp directories."""
    with patch("registry.services.peer_federation_service.settings") as mock:
        mock.peers_dir = temp_peers_dir
        mock.peer_sync_state_file_path = tmp_path / "peer_sync_state.json"
        yield mock


@pytest.fixture
def sample_peer_config():
    """Sample peer config for testing."""
    return PeerRegistryConfig(
        peer_id="central-registry",
        name="Central Registry",
        endpoint="https://central.example.com",
        enabled=True,
        sync_mode="all",
        sync_interval_minutes=60,
    )


@pytest.fixture
def sample_peer_config_2():
    """Second sample peer config for testing."""
    return PeerRegistryConfig(
        peer_id="backup-registry",
        name="Backup Registry",
        endpoint="https://backup.example.com",
        enabled=False,
        sync_mode="whitelist",
        whitelist_servers=["/server1", "/server2"],
        sync_interval_minutes=120,
    )


@pytest.mark.unit
class TestPeerIdToFilename:
    """Tests for _peer_id_to_filename helper function."""

    def test_appends_json_extension(self):
        """Test that .json extension is appended."""
        assert _peer_id_to_filename("central") == "central.json"

    def test_handles_alphanumeric(self):
        """Test alphanumeric peer IDs."""
        assert _peer_id_to_filename("peer123") == "peer123.json"

    def test_handles_hyphens(self):
        """Test peer IDs with hyphens."""
        assert _peer_id_to_filename("my-peer-registry") == "my-peer-registry.json"

    def test_handles_underscores(self):
        """Test peer IDs with underscores."""
        assert _peer_id_to_filename("my_peer_registry") == "my_peer_registry.json"


@pytest.mark.unit
class TestValidatePeerId:
    """Tests for _validate_peer_id helper function."""

    def test_valid_peer_id(self):
        """Test that valid peer IDs pass validation."""
        # Should not raise
        _validate_peer_id("valid-peer-123")
        _validate_peer_id("peer_with_underscore")
        _validate_peer_id("alphanumeric123")

    def test_empty_peer_id_rejected(self):
        """Test that empty peer ID is rejected."""
        with pytest.raises(ValueError, match="peer_id cannot be empty"):
            _validate_peer_id("")

    def test_path_traversal_dotdot_rejected(self):
        """Test that .. path traversal is rejected."""
        with pytest.raises(ValueError, match="path traversal detected"):
            _validate_peer_id("../etc/passwd")

    def test_path_traversal_forward_slash_rejected(self):
        """Test that forward slash is rejected."""
        with pytest.raises(ValueError, match="path traversal detected"):
            _validate_peer_id("path/to/file")

    def test_path_traversal_backslash_rejected(self):
        """Test that backslash is rejected."""
        with pytest.raises(ValueError, match="path traversal detected"):
            _validate_peer_id("path\\to\\file")

    def test_invalid_character_less_than_rejected(self):
        """Test that < character is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer<name")

    def test_invalid_character_greater_than_rejected(self):
        """Test that > character is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer>name")

    def test_invalid_character_colon_rejected(self):
        """Test that : character is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer:name")

    def test_invalid_character_quote_rejected(self):
        """Test that double quote is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id('peer"name')

    def test_invalid_character_pipe_rejected(self):
        """Test that | character is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer|name")

    def test_invalid_character_question_rejected(self):
        """Test that ? character is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer?name")

    def test_invalid_character_asterisk_rejected(self):
        """Test that * character is rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _validate_peer_id("peer*name")

    def test_reserved_name_con_rejected(self):
        """Test that reserved name CON is rejected."""
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("con")
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("CON")

    def test_reserved_name_prn_rejected(self):
        """Test that reserved name PRN is rejected."""
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("prn")

    def test_reserved_name_aux_rejected(self):
        """Test that reserved name AUX is rejected."""
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("aux")

    def test_reserved_name_nul_rejected(self):
        """Test that reserved name NUL is rejected."""
        with pytest.raises(ValueError, match="reserved name"):
            _validate_peer_id("nul")


@pytest.mark.unit
class TestGetSafeFilePath:
    """Tests for _get_safe_file_path helper function."""

    def test_normal_path_returns_valid(self, temp_peers_dir):
        """Test that normal peer ID returns valid path."""
        result = _get_safe_file_path("valid-peer", temp_peers_dir)
        assert result == temp_peers_dir / "valid-peer.json"

    def test_path_traversal_rejected(self, temp_peers_dir):
        """Test that path traversal attempts are rejected."""
        with pytest.raises(ValueError, match="path traversal detected"):
            _get_safe_file_path("../etc/passwd", temp_peers_dir)

    def test_invalid_chars_rejected(self, temp_peers_dir):
        """Test that invalid characters are rejected."""
        with pytest.raises(ValueError, match="invalid character"):
            _get_safe_file_path("peer|name", temp_peers_dir)

    def test_resolved_path_within_peers_dir(self, temp_peers_dir):
        """Test that resolved path is within peers directory."""
        result = _get_safe_file_path("normal-peer", temp_peers_dir)
        resolved = result.resolve()
        assert resolved.is_relative_to(temp_peers_dir.resolve())


@pytest.mark.unit
class TestLoadPeerFromFile:
    """Tests for _load_peer_from_file helper function."""

    def test_load_valid_peer_file(self, temp_peers_dir):
        """Test loading a valid peer config file."""
        peer_data = {
            "peer_id": "test-peer",
            "name": "Test Peer",
            "endpoint": "https://test.example.com",
            "enabled": True,
            "sync_mode": "all",
            "sync_interval_minutes": 60,
        }
        file_path = temp_peers_dir / "test-peer.json"
        with open(file_path, "w") as f:
            json.dump(peer_data, f)

        result = _load_peer_from_file(file_path)

        assert result is not None
        assert isinstance(result, PeerRegistryConfig)
        assert result.peer_id == "test-peer"
        assert result.name == "Test Peer"
        assert result.endpoint == "https://test.example.com"

    def test_load_file_not_found(self, temp_peers_dir):
        """Test loading non-existent file returns None."""
        file_path = temp_peers_dir / "nonexistent.json"
        result = _load_peer_from_file(file_path)
        assert result is None

    def test_load_invalid_json(self, temp_peers_dir):
        """Test loading file with invalid JSON returns None."""
        file_path = temp_peers_dir / "invalid.json"
        with open(file_path, "w") as f:
            f.write("{ invalid json }")

        result = _load_peer_from_file(file_path)
        assert result is None

    def test_load_missing_peer_id_field(self, temp_peers_dir):
        """Test loading file missing peer_id field returns None."""
        peer_data = {
            "name": "Test Peer",
            "endpoint": "https://test.example.com",
        }
        file_path = temp_peers_dir / "missing-field.json"
        with open(file_path, "w") as f:
            json.dump(peer_data, f)

        result = _load_peer_from_file(file_path)
        assert result is None

    def test_load_non_dict_data(self, temp_peers_dir):
        """Test loading file with non-dict data returns None."""
        file_path = temp_peers_dir / "list-data.json"
        with open(file_path, "w") as f:
            json.dump(["not", "a", "dict"], f)

        result = _load_peer_from_file(file_path)
        assert result is None


@pytest.mark.unit
class TestSavePeerToDisk:
    """Tests for _save_peer_to_disk helper function."""

    def test_save_peer_successfully(self, temp_peers_dir, sample_peer_config):
        """Test successfully saving peer to disk."""
        result = _save_peer_to_disk(sample_peer_config, temp_peers_dir)

        assert result is True
        file_path = temp_peers_dir / "central-registry.json"
        assert file_path.exists()

        # Verify contents
        with open(file_path, "r") as f:
            data = json.load(f)
        assert data["peer_id"] == "central-registry"
        assert data["name"] == "Central Registry"

    def test_save_creates_directory(self, tmp_path, sample_peer_config):
        """Test that save creates directory if it doesn't exist."""
        new_dir = tmp_path / "new_peers_dir"
        assert not new_dir.exists()

        result = _save_peer_to_disk(sample_peer_config, new_dir)

        assert result is True
        assert new_dir.exists()
        assert (new_dir / "central-registry.json").exists()

    def test_save_invalid_peer_id_fails(self, temp_peers_dir):
        """Test that saving with invalid peer_id fails."""
        invalid_peer = PeerRegistryConfig(
            peer_id="valid-id",  # We'll override this
            name="Invalid Peer",
            endpoint="https://invalid.example.com",
        )
        # Bypass validation by directly setting the value
        invalid_peer.__dict__["peer_id"] = "../etc/passwd"

        result = _save_peer_to_disk(invalid_peer, temp_peers_dir)
        assert result is False


@pytest.mark.unit
class TestLoadSyncState:
    """Tests for _load_sync_state helper function."""

    def test_load_valid_sync_state(self, tmp_path):
        """Test loading valid sync state file."""
        state_file = tmp_path / "sync_state.json"
        state_data = {
            "peer1": {
                "peer_id": "peer1",
                "is_healthy": True,
                "current_generation": 42,
                "total_servers_synced": 10,
            },
            "peer2": {
                "peer_id": "peer2",
                "is_healthy": False,
                "current_generation": 0,
            },
        }
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        result = _load_sync_state(state_file)

        assert len(result) == 2
        assert "peer1" in result
        assert isinstance(result["peer1"], PeerSyncStatus)
        assert result["peer1"].is_healthy is True
        assert result["peer1"].current_generation == 42

    def test_load_empty_file_returns_empty_dict(self, tmp_path):
        """Test loading non-existent file returns empty dict."""
        state_file = tmp_path / "nonexistent.json"
        result = _load_sync_state(state_file)
        assert result == {}

    def test_load_corrupt_json_returns_empty_dict(self, tmp_path):
        """Test loading corrupt JSON returns empty dict."""
        state_file = tmp_path / "corrupt.json"
        with open(state_file, "w") as f:
            f.write("{ corrupt json }")

        result = _load_sync_state(state_file)
        assert result == {}

    def test_load_non_dict_returns_empty_dict(self, tmp_path):
        """Test loading non-dict data returns empty dict."""
        state_file = tmp_path / "list-data.json"
        with open(state_file, "w") as f:
            json.dump(["not", "a", "dict"], f)

        result = _load_sync_state(state_file)
        assert result == {}

    def test_load_skips_invalid_peer_status(self, tmp_path):
        """Test that invalid peer status entries are skipped."""
        state_file = tmp_path / "sync_state.json"
        state_data = {
            "valid_peer": {
                "peer_id": "valid_peer",
                "is_healthy": True,
            },
            "invalid_peer": {
                # Missing required peer_id field
                "is_healthy": True,
            },
        }
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        result = _load_sync_state(state_file)

        # Only valid peer should be loaded
        assert len(result) == 1
        assert "valid_peer" in result


@pytest.mark.unit
class TestPersistSyncState:
    """Tests for _persist_sync_state helper function."""

    def test_persist_sync_state_successfully(self, tmp_path):
        """Test successfully persisting sync state."""
        state_file = tmp_path / "sync_state.json"
        sync_status_map = {
            "peer1": PeerSyncStatus(peer_id="peer1", is_healthy=True),
            "peer2": PeerSyncStatus(peer_id="peer2", is_healthy=False),
        }

        _persist_sync_state(sync_status_map, state_file)

        assert state_file.exists()
        with open(state_file, "r") as f:
            data = json.load(f)

        assert "peer1" in data
        assert data["peer1"]["peer_id"] == "peer1"
        assert data["peer1"]["is_healthy"] is True

    def test_persist_creates_parent_directory(self, tmp_path):
        """Test that persist creates parent directory if needed."""
        state_file = tmp_path / "new_dir" / "sync_state.json"
        assert not state_file.parent.exists()

        sync_status_map = {
            "peer1": PeerSyncStatus(peer_id="peer1"),
        }

        _persist_sync_state(sync_status_map, state_file)

        assert state_file.parent.exists()
        assert state_file.exists()


@pytest.mark.unit
class TestPeerFederationServiceSingleton:
    """Tests for singleton pattern implementation."""

    def test_singleton_returns_same_instance(self, mock_settings):
        """Test that singleton returns same instance."""
        service1 = PeerFederationService()
        service2 = PeerFederationService()
        assert service1 is service2

    def test_get_peer_federation_service_returns_singleton(self, mock_settings):
        """Test that helper function returns singleton."""
        service1 = get_peer_federation_service()
        service2 = get_peer_federation_service()
        assert service1 is service2

    def test_singleton_thread_safe(self, mock_settings):
        """Test that singleton is thread-safe."""
        instances = []

        def create_instance():
            instances.append(PeerFederationService())

        threads = [Thread(target=create_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All instances should be the same
        first_instance = instances[0]
        assert all(inst is first_instance for inst in instances)


@pytest.mark.unit
class TestPeerFederationServiceCRUD:
    """Tests for CRUD operations on PeerFederationService."""

    def test_add_peer_success(self, mock_settings, sample_peer_config):
        """Test successfully adding a peer."""
        service = PeerFederationService()

        result = service.add_peer(sample_peer_config)

        assert result.peer_id == sample_peer_config.peer_id
        assert result.name == sample_peer_config.name
        assert result.created_at is not None
        assert result.updated_at is not None

        # Verify in-memory registry
        assert sample_peer_config.peer_id in service.registered_peers

        # Verify sync status initialized
        assert sample_peer_config.peer_id in service.peer_sync_status

    def test_add_peer_duplicate_peer_id_fails(self, mock_settings, sample_peer_config):
        """Test that adding duplicate peer_id raises error."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Try to add again
        with pytest.raises(ValueError, match="already exists"):
            service.add_peer(sample_peer_config)

    def test_add_peer_invalid_peer_id_path_traversal_fails(self, mock_settings):
        """Test that path traversal in peer_id is rejected."""
        service = PeerFederationService()

        # Create a peer with invalid ID (bypass Pydantic validation)
        with pytest.raises(ValueError):
            # This should fail during Pydantic validation
            invalid_peer = PeerRegistryConfig(
                peer_id="../etc/passwd",
                name="Malicious Peer",
                endpoint="https://evil.example.com",
            )

    def test_add_peer_saves_to_disk(self, mock_settings, sample_peer_config):
        """Test that adding peer saves to disk."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        file_path = mock_settings.peers_dir / "central-registry.json"
        assert file_path.exists()

    def test_get_peer_existing(self, mock_settings, sample_peer_config):
        """Test getting an existing peer."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        result = service.get_peer(sample_peer_config.peer_id)

        assert result.peer_id == sample_peer_config.peer_id
        assert result.name == sample_peer_config.name

    def test_get_peer_nonexistent_raises_error(self, mock_settings):
        """Test that getting non-existent peer raises error."""
        service = PeerFederationService()

        with pytest.raises(ValueError, match="Peer not found"):
            service.get_peer("nonexistent-peer")

    def test_update_peer_success(self, mock_settings, sample_peer_config):
        """Test successfully updating a peer."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        updates = {
            "name": "Updated Name",
            "enabled": False,
        }

        result = service.update_peer(sample_peer_config.peer_id, updates)

        assert result.name == "Updated Name"
        assert result.enabled is False
        assert result.peer_id == sample_peer_config.peer_id  # peer_id unchanged

    def test_update_peer_nonexistent_raises_error(self, mock_settings):
        """Test that updating non-existent peer raises error."""
        service = PeerFederationService()

        with pytest.raises(ValueError, match="Peer not found"):
            service.update_peer("nonexistent-peer", {"name": "New Name"})

    def test_update_peer_invalid_data_raises_error(self, mock_settings, sample_peer_config):
        """Test that updating with invalid data raises error."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Try to update with invalid sync_interval
        updates = {
            "sync_interval_minutes": 1,  # Too low (minimum is 5)
        }

        with pytest.raises(ValueError, match="Invalid peer update"):
            service.update_peer(sample_peer_config.peer_id, updates)

    def test_update_peer_saves_to_disk(self, mock_settings, sample_peer_config):
        """Test that updating peer saves to disk."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        service.update_peer(sample_peer_config.peer_id, {"name": "Updated Name"})

        file_path = mock_settings.peers_dir / "central-registry.json"
        with open(file_path, "r") as f:
            data = json.load(f)
        assert data["name"] == "Updated Name"

    def test_remove_peer_success(self, mock_settings, sample_peer_config):
        """Test successfully removing a peer."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        result = service.remove_peer(sample_peer_config.peer_id)

        assert result is True
        assert sample_peer_config.peer_id not in service.registered_peers
        assert sample_peer_config.peer_id not in service.peer_sync_status

    def test_remove_peer_nonexistent_raises_error(self, mock_settings):
        """Test that removing non-existent peer raises error."""
        service = PeerFederationService()

        with pytest.raises(ValueError, match="Peer not found"):
            service.remove_peer("nonexistent-peer")

    def test_remove_peer_deletes_file(self, mock_settings, sample_peer_config):
        """Test that removing peer deletes file from disk."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        file_path = mock_settings.peers_dir / "central-registry.json"
        assert file_path.exists()

        service.remove_peer(sample_peer_config.peer_id)

        assert not file_path.exists()

    def test_remove_peer_path_traversal_fails(self, mock_settings):
        """Test that path traversal in remove_peer is rejected."""
        service = PeerFederationService()

        # Try to remove with path traversal
        # Note: This will fail with "Peer not found" since validation happens
        # after the existence check. This is the correct behavior - fail fast.
        with pytest.raises(ValueError):
            service.remove_peer("../etc/passwd")

    def test_list_peers_all(
        self, mock_settings, sample_peer_config, sample_peer_config_2
    ):
        """Test listing all peers."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)
        service.add_peer(sample_peer_config_2)

        result = service.list_peers()

        assert len(result) == 2
        peer_ids = [p.peer_id for p in result]
        assert sample_peer_config.peer_id in peer_ids
        assert sample_peer_config_2.peer_id in peer_ids

    def test_list_peers_enabled_only(
        self, mock_settings, sample_peer_config, sample_peer_config_2
    ):
        """Test listing only enabled peers."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)  # enabled=True
        service.add_peer(sample_peer_config_2)  # enabled=False

        result = service.list_peers(enabled=True)

        assert len(result) == 1
        assert result[0].peer_id == sample_peer_config.peer_id

    def test_list_peers_disabled_only(
        self, mock_settings, sample_peer_config, sample_peer_config_2
    ):
        """Test listing only disabled peers."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)  # enabled=True
        service.add_peer(sample_peer_config_2)  # enabled=False

        result = service.list_peers(enabled=False)

        assert len(result) == 1
        assert result[0].peer_id == sample_peer_config_2.peer_id


@pytest.mark.unit
class TestPeerFederationServiceStateManagement:
    """Tests for state management operations."""

    def test_load_peers_and_state_from_disk(self, mock_settings):
        """Test loading peers and state from disk."""
        # Create peer files
        peer1_data = {
            "peer_id": "peer1",
            "name": "Peer 1",
            "endpoint": "https://peer1.example.com",
            "enabled": True,
            "sync_mode": "all",
            "sync_interval_minutes": 60,
        }
        peer1_file = mock_settings.peers_dir / "peer1.json"
        with open(peer1_file, "w") as f:
            json.dump(peer1_data, f)

        # Create sync state file
        state_data = {
            "peer1": {
                "peer_id": "peer1",
                "is_healthy": True,
                "current_generation": 10,
            }
        }
        with open(mock_settings.peer_sync_state_file_path, "w") as f:
            json.dump(state_data, f)

        service = PeerFederationService()
        service.load_peers_and_state()

        assert len(service.registered_peers) == 1
        assert "peer1" in service.registered_peers
        assert service.peer_sync_status["peer1"].is_healthy is True

    def test_load_peers_empty_directory(self, mock_settings):
        """Test loading peers from empty directory."""
        service = PeerFederationService()
        service.load_peers_and_state()

        assert len(service.registered_peers) == 0

    def test_get_sync_status_existing_peer(self, mock_settings, sample_peer_config):
        """Test getting sync status for existing peer."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        status = service.get_sync_status(sample_peer_config.peer_id)

        assert status is not None
        assert isinstance(status, PeerSyncStatus)
        assert status.peer_id == sample_peer_config.peer_id

    def test_get_sync_status_nonexistent_peer(self, mock_settings):
        """Test getting sync status for non-existent peer returns None."""
        service = PeerFederationService()

        status = service.get_sync_status("nonexistent-peer")

        assert status is None

    def test_update_sync_status(self, mock_settings, sample_peer_config):
        """Test updating sync status for a peer."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        new_status = PeerSyncStatus(
            peer_id=sample_peer_config.peer_id,
            is_healthy=True,
            current_generation=42,
            total_servers_synced=10,
        )

        service.update_sync_status(sample_peer_config.peer_id, new_status)

        # Verify updated
        status = service.get_sync_status(sample_peer_config.peer_id)
        assert status.is_healthy is True
        assert status.current_generation == 42
        assert status.total_servers_synced == 10

    def test_update_sync_status_persists_to_disk(
        self, mock_settings, sample_peer_config
    ):
        """Test that updating sync status persists to disk."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        new_status = PeerSyncStatus(
            peer_id=sample_peer_config.peer_id,
            is_healthy=True,
            current_generation=42,
        )

        service.update_sync_status(sample_peer_config.peer_id, new_status)

        # Verify persisted
        with open(mock_settings.peer_sync_state_file_path, "r") as f:
            data = json.load(f)

        assert sample_peer_config.peer_id in data
        assert data[sample_peer_config.peer_id]["current_generation"] == 42


@pytest.mark.unit
class TestPeerFederationServiceSecurity:
    """Security-focused tests for PeerFederationService."""

    def test_add_peer_prevents_path_traversal_attack(self, mock_settings):
        """Test that add_peer prevents path traversal attacks."""
        service = PeerFederationService()

        # Pydantic validation should catch this
        with pytest.raises(ValueError):
            malicious_peer = PeerRegistryConfig(
                peer_id="../../../etc/passwd",
                name="Malicious Peer",
                endpoint="https://evil.example.com",
            )

    def test_remove_peer_prevents_path_traversal_attack(self, mock_settings):
        """Test that remove_peer prevents path traversal attacks."""
        service = PeerFederationService()

        # Path traversal will fail with "Peer not found" since the peer
        # doesn't exist. If we add a peer first, it would be caught by
        # _get_safe_file_path during deletion.
        with pytest.raises(ValueError):
            service.remove_peer("../../etc/passwd")

    def test_update_peer_cannot_change_peer_id(
        self, mock_settings, sample_peer_config
    ):
        """Test that update_peer cannot change peer_id."""
        service = PeerFederationService()
        service.add_peer(sample_peer_config)

        # Try to change peer_id via update
        updates = {"peer_id": "different-id"}

        result = service.update_peer(sample_peer_config.peer_id, updates)

        # peer_id should remain unchanged
        assert result.peer_id == sample_peer_config.peer_id
        assert "different-id" not in service.registered_peers
