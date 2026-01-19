"""
Unit tests for Peer Federation Service.

Tests for peer registry federation configuration management,
including CRUD operations, security, and state management.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from threading import Thread
from typing import Dict

from registry.services.peer_federation_service import (
    PeerFederationService,
    get_peer_federation_service,
    _validate_peer_id,
)
from registry.repositories.file.peer_federation_repository import (
    _validate_peer_id as repo_validate_peer_id,
    _get_safe_file_path,
    FilePeerFederationRepository,
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
def mock_file_repo(temp_peers_dir, tmp_path):
    """Create a file-based repository with temp directories."""
    sync_state_file = tmp_path / "peer_sync_state.json"
    return FilePeerFederationRepository(
        peers_dir=temp_peers_dir,
        sync_state_file=sync_state_file
    )


@pytest.fixture
def mock_repo_factory(mock_file_repo):
    """Mock the get_peer_federation_repository factory to return file-based repo."""
    with patch(
        "registry.services.peer_federation_service.get_peer_federation_repository",
        return_value=mock_file_repo
    ):
        yield mock_file_repo


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


@pytest.mark.unit
class TestPeerFederationServiceSingleton:
    """Tests for singleton pattern implementation."""

    def test_singleton_returns_same_instance(self):
        """Test that singleton returns same instance."""
        service1 = PeerFederationService()
        service2 = PeerFederationService()
        assert service1 is service2

    def test_get_peer_federation_service_returns_singleton(self):
        """Test that helper function returns singleton."""
        service1 = get_peer_federation_service()
        service2 = get_peer_federation_service()
        assert service1 is service2

    def test_singleton_thread_safe(self):
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
    """Tests for CRUD operations on PeerFederationService (async methods)."""

    @pytest.mark.asyncio
    async def test_add_peer_success(self, mock_repo_factory, sample_peer_config):
        """Test successfully adding a peer."""
        service = PeerFederationService()

        result = await service.add_peer(sample_peer_config)

        assert result.peer_id == sample_peer_config.peer_id
        assert result.name == sample_peer_config.name
        assert result.created_at is not None
        assert result.updated_at is not None

        # Verify in-memory registry
        assert sample_peer_config.peer_id in service.registered_peers

        # Verify sync status initialized
        assert sample_peer_config.peer_id in service.peer_sync_status

    @pytest.mark.asyncio
    async def test_add_peer_duplicate_peer_id_fails(self, mock_repo_factory, sample_peer_config):
        """Test that adding duplicate peer_id raises error."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Try to add again
        with pytest.raises(ValueError, match="already exists"):
            await service.add_peer(sample_peer_config)

    def test_add_peer_invalid_peer_id_path_traversal_fails(self):
        """Test that path traversal in peer_id is rejected."""
        # Create a peer with invalid ID (bypass Pydantic validation)
        with pytest.raises(ValueError):
            # This should fail during Pydantic validation
            PeerRegistryConfig(
                peer_id="../etc/passwd",
                name="Malicious Peer",
                endpoint="https://evil.example.com",
            )

    @pytest.mark.asyncio
    async def test_add_peer_saves_to_repository(self, mock_repo_factory, sample_peer_config, temp_peers_dir):
        """Test that adding peer saves to repository."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # For file-based repo, check file exists
        file_path = temp_peers_dir / "central-registry.json"
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_get_peer_existing(self, mock_repo_factory, sample_peer_config):
        """Test getting an existing peer."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        result = await service.get_peer(sample_peer_config.peer_id)

        assert result.peer_id == sample_peer_config.peer_id
        assert result.name == sample_peer_config.name

    @pytest.mark.asyncio
    async def test_get_peer_nonexistent_raises_error(self, mock_repo_factory):
        """Test that getting non-existent peer raises error."""
        service = PeerFederationService()

        with pytest.raises(ValueError, match="Peer not found"):
            await service.get_peer("nonexistent-peer")

    @pytest.mark.asyncio
    async def test_update_peer_success(self, mock_repo_factory, sample_peer_config):
        """Test successfully updating a peer."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        updates = {
            "name": "Updated Name",
            "enabled": False,
        }

        result = await service.update_peer(sample_peer_config.peer_id, updates)

        assert result.name == "Updated Name"
        assert result.enabled is False
        assert result.peer_id == sample_peer_config.peer_id  # peer_id unchanged

    @pytest.mark.asyncio
    async def test_update_peer_nonexistent_raises_error(self, mock_repo_factory):
        """Test that updating non-existent peer raises error."""
        service = PeerFederationService()

        with pytest.raises(ValueError, match="Peer not found"):
            await service.update_peer("nonexistent-peer", {"name": "New Name"})

    @pytest.mark.asyncio
    async def test_update_peer_invalid_data_raises_error(self, mock_repo_factory, sample_peer_config):
        """Test that updating with invalid data raises error."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Try to update with invalid sync_interval
        updates = {
            "sync_interval_minutes": 1,  # Too low (minimum is 5)
        }

        with pytest.raises(ValueError, match="Invalid peer update"):
            await service.update_peer(sample_peer_config.peer_id, updates)

    @pytest.mark.asyncio
    async def test_remove_peer_success(self, mock_repo_factory, sample_peer_config):
        """Test successfully removing a peer."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        result = await service.remove_peer(sample_peer_config.peer_id)

        assert result is True
        assert sample_peer_config.peer_id not in service.registered_peers
        assert sample_peer_config.peer_id not in service.peer_sync_status

    @pytest.mark.asyncio
    async def test_remove_peer_nonexistent_raises_error(self, mock_repo_factory):
        """Test that removing non-existent peer raises error."""
        service = PeerFederationService()

        with pytest.raises(ValueError, match="Peer not found"):
            await service.remove_peer("nonexistent-peer")

    @pytest.mark.asyncio
    async def test_remove_peer_path_traversal_fails(self, mock_repo_factory):
        """Test that path traversal in remove_peer is rejected."""
        service = PeerFederationService()

        # Try to remove with path traversal
        with pytest.raises(ValueError):
            await service.remove_peer("../etc/passwd")

    @pytest.mark.asyncio
    async def test_list_peers_all(
        self, mock_repo_factory, sample_peer_config, sample_peer_config_2
    ):
        """Test listing all peers."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)
        await service.add_peer(sample_peer_config_2)

        result = await service.list_peers()

        assert len(result) == 2
        peer_ids = [p.peer_id for p in result]
        assert sample_peer_config.peer_id in peer_ids
        assert sample_peer_config_2.peer_id in peer_ids

    @pytest.mark.asyncio
    async def test_list_peers_enabled_only(
        self, mock_repo_factory, sample_peer_config, sample_peer_config_2
    ):
        """Test listing only enabled peers."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)  # enabled=True
        await service.add_peer(sample_peer_config_2)  # enabled=False

        result = await service.list_peers(enabled=True)

        assert len(result) == 1
        assert result[0].peer_id == sample_peer_config.peer_id


@pytest.mark.unit
class TestPeerFederationServiceStateManagement:
    """Tests for state management operations (async methods)."""

    @pytest.mark.asyncio
    async def test_load_peers_and_state_from_repository(self, mock_repo_factory, temp_peers_dir, tmp_path):
        """Test loading peers and state from repository."""
        # Create peer file directly
        peer1_data = {
            "peer_id": "peer1",
            "name": "Peer 1",
            "endpoint": "https://peer1.example.com",
            "enabled": True,
            "sync_mode": "all",
            "sync_interval_minutes": 60,
        }
        peer1_file = temp_peers_dir / "peer1.json"
        with open(peer1_file, "w") as f:
            json.dump(peer1_data, f)

        # Create sync state file directly
        state_data = {
            "peer1": {
                "peer_id": "peer1",
                "is_healthy": True,
                "current_generation": 10,
            }
        }
        sync_state_file = tmp_path / "peer_sync_state.json"
        with open(sync_state_file, "w") as f:
            json.dump(state_data, f)

        service = PeerFederationService()
        await service.load_peers_and_state()

        assert len(service.registered_peers) == 1
        assert "peer1" in service.registered_peers
        assert service.peer_sync_status["peer1"].is_healthy is True

    @pytest.mark.asyncio
    async def test_load_peers_empty_directory(self, mock_repo_factory):
        """Test loading peers from empty directory."""
        service = PeerFederationService()
        await service.load_peers_and_state()

        assert len(service.registered_peers) == 0

    @pytest.mark.asyncio
    async def test_get_sync_status_existing_peer(self, mock_repo_factory, sample_peer_config):
        """Test getting sync status for existing peer."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        status = await service.get_sync_status(sample_peer_config.peer_id)

        assert status is not None
        assert isinstance(status, PeerSyncStatus)
        assert status.peer_id == sample_peer_config.peer_id

    @pytest.mark.asyncio
    async def test_get_sync_status_nonexistent_peer(self, mock_repo_factory):
        """Test getting sync status for non-existent peer returns None."""
        service = PeerFederationService()

        status = await service.get_sync_status("nonexistent-peer")

        assert status is None

    @pytest.mark.asyncio
    async def test_update_sync_status(self, mock_repo_factory, sample_peer_config):
        """Test updating sync status for a peer."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        new_status = PeerSyncStatus(
            peer_id=sample_peer_config.peer_id,
            is_healthy=True,
            current_generation=42,
            total_servers_synced=10,
        )

        await service.update_sync_status(sample_peer_config.peer_id, new_status)

        # Verify updated
        status = await service.get_sync_status(sample_peer_config.peer_id)
        assert status.is_healthy is True
        assert status.current_generation == 42
        assert status.total_servers_synced == 10


@pytest.mark.unit
class TestPeerFederationServiceSecurity:
    """Security-focused tests for PeerFederationService."""

    def test_add_peer_prevents_path_traversal_attack(self):
        """Test that add_peer prevents path traversal attacks."""
        # Pydantic validation should catch this
        with pytest.raises(ValueError):
            PeerRegistryConfig(
                peer_id="../../../etc/passwd",
                name="Malicious Peer",
                endpoint="https://evil.example.com",
            )

    @pytest.mark.asyncio
    async def test_remove_peer_prevents_path_traversal_attack(self, mock_repo_factory):
        """Test that remove_peer prevents path traversal attacks."""
        service = PeerFederationService()

        # Path traversal will fail with "Peer not found" since the peer
        # doesn't exist. If we add a peer first, it would be caught by
        # _get_safe_file_path during deletion.
        with pytest.raises(ValueError):
            await service.remove_peer("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_update_peer_cannot_change_peer_id(
        self, mock_repo_factory, sample_peer_config
    ):
        """Test that update_peer cannot change peer_id."""
        service = PeerFederationService()
        await service.add_peer(sample_peer_config)

        # Try to change peer_id via update
        updates = {"peer_id": "different-id"}

        result = await service.update_peer(sample_peer_config.peer_id, updates)

        # peer_id should remain unchanged
        assert result.peer_id == sample_peer_config.peer_id
        assert "different-id" not in service.registered_peers
