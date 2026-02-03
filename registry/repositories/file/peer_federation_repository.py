"""File-based repository for peer federation configuration storage.

DEPRECATED: This implementation is kept for backward compatibility only.
New deployments should use storage_backend=documentdb or storage_backend=mongodb-ce.

Storage structure:
- {peers_dir}/{peer_id}.json: Peer registry configurations
- {peers_dir}/../peer_sync_state.json: Sync status for all peers
"""

import json
import logging
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...core.config import settings
from ...schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
)
from ...utils.federation_encryption import (
    decrypt_token_in_peer_dict,
    encrypt_token_in_peer_dict,
)
from ..interfaces import PeerFederationRepositoryBase

logger = logging.getLogger(__name__)


def _validate_peer_id(
    peer_id: str,
) -> None:
    """
    Validate peer_id to prevent path traversal and invalid characters.

    Args:
        peer_id: Peer identifier to validate

    Raises:
        ValueError: If peer_id contains invalid characters or path traversal
    """
    if not peer_id:
        raise ValueError("peer_id cannot be empty")

    # Check for path traversal attempts
    if ".." in peer_id or "/" in peer_id or "\\" in peer_id:
        raise ValueError(f"Invalid peer_id: path traversal detected in '{peer_id}'")

    # Check for invalid filename characters
    invalid_chars = ["<", ">", ":", '"', "|", "?", "*", "\0"]
    for char in invalid_chars:
        if char in peer_id:
            raise ValueError(f"Invalid peer_id: contains invalid character '{char}'")

    # Check for reserved names
    if peer_id.lower() in ["con", "prn", "aux", "nul"]:
        raise ValueError(f"Invalid peer_id: '{peer_id}' is a reserved name")


def _get_safe_file_path(
    peer_id: str,
    peers_dir: Path,
) -> Path:
    """
    Get safe file path for a peer config, with path traversal protection.

    Args:
        peer_id: Peer identifier
        peers_dir: Directory for peer storage

    Returns:
        Safe file path within peers_dir

    Raises:
        ValueError: If path traversal is detected
    """
    _validate_peer_id(peer_id)

    filename = f"{peer_id}.json"
    file_path = peers_dir / filename

    # Resolve to absolute path and verify it's within peers_dir
    resolved_path = file_path.resolve()
    resolved_peers_dir = peers_dir.resolve()

    if not resolved_path.is_relative_to(resolved_peers_dir):
        raise ValueError(f"Invalid peer_id: path traversal detected for '{peer_id}'")

    return file_path


class FilePeerFederationRepository(PeerFederationRepositoryBase):
    """File-based implementation of peer federation repository.

    DEPRECATED: Use DocumentDBPeerFederationRepository for new deployments.
    """

    def __init__(
        self,
        peers_dir: Path | None = None,
        sync_state_file: Path | None = None,
    ):
        """
        Initialize file-based peer federation repository.

        Args:
            peers_dir: Directory for peer config files (default: from settings)
            sync_state_file: Path to sync state file (default: from settings)
        """
        warnings.warn(
            "FilePeerFederationRepository is deprecated. "
            "Use storage_backend=documentdb or storage_backend=mongodb-ce instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        self._peers_dir = peers_dir or settings.peers_dir
        self._sync_state_file = sync_state_file or settings.peer_sync_state_file_path

        # Ensure directories exist
        self._peers_dir.mkdir(parents=True, exist_ok=True)
        self._sync_state_file.parent.mkdir(parents=True, exist_ok=True)

        # In-memory caches
        self._peers_cache: dict[str, PeerRegistryConfig] = {}
        self._sync_status_cache: dict[str, PeerSyncStatus] = {}

        logger.info(
            f"Initialized File PeerFederationRepository with "
            f"peers_dir={self._peers_dir}, sync_state_file={self._sync_state_file} "
            "(DEPRECATED)"
        )

    def _load_peer_from_file(
        self,
        file_path: Path,
    ) -> PeerRegistryConfig | None:
        """Load peer config from JSON file."""
        try:
            with open(file_path) as f:
                peer_data = json.load(f)

            if not isinstance(peer_data, dict):
                logger.warning(f"Invalid peer data format in {file_path}")
                return None

            if "peer_id" not in peer_data:
                logger.warning(f"Missing peer_id in {file_path}")
                return None

            # Decrypt federation token if present
            decrypt_token_in_peer_dict(peer_data)

            peer_config = PeerRegistryConfig(**peer_data)
            return peer_config

        except FileNotFoundError:
            logger.error(f"Peer file not found: {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse JSON from {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading {file_path}: {e}", exc_info=True)
            return None

    def _save_peer_to_file(
        self,
        peer_config: PeerRegistryConfig,
    ) -> bool:
        """Save peer config to JSON file."""
        try:
            file_path = _get_safe_file_path(peer_config.peer_id, self._peers_dir)

            peer_dict = peer_config.model_dump(mode="json")

            # Encrypt federation token before storage
            encrypt_token_in_peer_dict(peer_dict)

            with open(file_path, "w") as f:
                json.dump(peer_dict, f, indent=2)

            logger.debug(f"Saved peer config to {file_path}")
            return True

        except ValueError as e:
            logger.error(f"Invalid peer_id: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to save peer '{peer_config.peer_id}' to disk: {e}", exc_info=True)
            return False

    def _load_sync_state_file(self) -> dict[str, PeerSyncStatus]:
        """Load sync state from file."""
        try:
            if not self._sync_state_file.exists():
                logger.info(f"No sync state file found at {self._sync_state_file}")
                return {}

            with open(self._sync_state_file) as f:
                state_data = json.load(f)

            if not isinstance(state_data, dict):
                logger.warning(f"Invalid state format in {self._sync_state_file}")
                return {}

            sync_status_map = {}
            for peer_id, status_dict in state_data.items():
                try:
                    sync_status = PeerSyncStatus(**status_dict)
                    sync_status_map[peer_id] = sync_status
                except Exception as e:
                    logger.error(f"Failed to load sync status for peer '{peer_id}': {e}")

            return sync_status_map

        except json.JSONDecodeError as e:
            logger.error(f"Could not parse JSON from {self._sync_state_file}: {e}")
            return {}
        except Exception as e:
            logger.error(
                f"Failed to read sync state file {self._sync_state_file}: {e}", exc_info=True
            )
            return {}

    def _save_sync_state_file(self) -> None:
        """Persist sync state to file."""
        try:
            state_data = {
                peer_id: status.model_dump(mode="json")
                for peer_id, status in self._sync_status_cache.items()
            }

            with open(self._sync_state_file, "w") as f:
                json.dump(state_data, f, indent=2)

            logger.debug(f"Persisted sync state to {self._sync_state_file}")

        except Exception as e:
            logger.error(
                f"Failed to persist sync state to {self._sync_state_file}: {e}", exc_info=True
            )

    async def get_peer(
        self,
        peer_id: str,
    ) -> PeerRegistryConfig | None:
        """Get peer configuration by ID."""
        return self._peers_cache.get(peer_id)

    async def list_peers(
        self,
        enabled: bool | None = None,
    ) -> list[PeerRegistryConfig]:
        """List all peer configurations with optional filtering."""
        peers = list(self._peers_cache.values())

        if enabled is None:
            return peers

        return [peer for peer in peers if peer.enabled == enabled]

    async def create_peer(
        self,
        config: PeerRegistryConfig,
    ) -> PeerRegistryConfig:
        """Create a new peer configuration."""
        peer_id = config.peer_id

        # Validate peer_id
        _validate_peer_id(peer_id)

        # Check if peer already exists
        if peer_id in self._peers_cache:
            raise ValueError(f"Peer ID '{peer_id}' already exists")

        # Set timestamps
        now = datetime.now(UTC)
        config.created_at = now
        config.updated_at = now

        # Save to file
        if not self._save_peer_to_file(config):
            raise ValueError(f"Failed to save peer '{config.name}' to disk")

        # Update cache
        self._peers_cache[peer_id] = config

        # Initialize sync status
        self._sync_status_cache[peer_id] = PeerSyncStatus(peer_id=peer_id)
        self._save_sync_state_file()

        logger.info(f"Created peer: {peer_id} ({config.name})")
        return config

    async def update_peer(
        self,
        peer_id: str,
        updates: dict[str, Any],
    ) -> PeerRegistryConfig:
        """Update an existing peer configuration."""
        if peer_id not in self._peers_cache:
            raise ValueError(f"Peer not found: {peer_id}")

        existing_peer = self._peers_cache[peer_id]

        # Merge updates with existing data
        peer_dict = existing_peer.model_dump()
        peer_dict.update(updates)

        # Ensure peer_id is consistent
        peer_dict["peer_id"] = peer_id

        # Update timestamp
        peer_dict["updated_at"] = datetime.now(UTC)

        # Validate updated peer
        try:
            updated_peer = PeerRegistryConfig(**peer_dict)
        except Exception as e:
            raise ValueError(f"Invalid peer update: {e}")

        # Save to file
        if not self._save_peer_to_file(updated_peer):
            raise ValueError("Failed to save updated peer to disk")

        # Update cache
        self._peers_cache[peer_id] = updated_peer

        logger.info(f"Updated peer: {peer_id}")
        return updated_peer

    async def delete_peer(
        self,
        peer_id: str,
    ) -> bool:
        """Delete a peer configuration and its sync status."""
        if peer_id not in self._peers_cache:
            raise ValueError(f"Peer not found: {peer_id}")

        try:
            file_path = _get_safe_file_path(peer_id, self._peers_dir)

            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Removed peer file: {file_path}")

            # Remove from caches
            peer_name = self._peers_cache[peer_id].name
            del self._peers_cache[peer_id]

            if peer_id in self._sync_status_cache:
                del self._sync_status_cache[peer_id]

            # Persist updated sync state
            self._save_sync_state_file()

            logger.info(f"Deleted peer: {peer_id} ({peer_name})")
            return True

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete peer '{peer_id}': {e}", exc_info=True)
            raise ValueError(f"Failed to delete peer: {e}")

    async def get_sync_status(
        self,
        peer_id: str,
    ) -> PeerSyncStatus | None:
        """Get sync status for a peer."""
        return self._sync_status_cache.get(peer_id)

    async def update_sync_status(
        self,
        peer_id: str,
        status: PeerSyncStatus,
    ) -> PeerSyncStatus:
        """Update sync status for a peer."""
        self._sync_status_cache[peer_id] = status
        self._save_sync_state_file()

        logger.debug(f"Updated sync status for peer: {peer_id}")
        return status

    async def list_sync_statuses(self) -> list[PeerSyncStatus]:
        """List all peer sync statuses."""
        return list(self._sync_status_cache.values())

    async def load_all(self) -> None:
        """Load/reload all peers and sync states from storage."""
        logger.info(f"Loading peers from {self._peers_dir}...")

        # Clear caches
        self._peers_cache = {}
        self._sync_status_cache = {}

        # Load peer configs from files
        peer_files = list(self._peers_dir.glob("*.json"))

        # Exclude sync state file if it's in the same directory
        peer_files = [f for f in peer_files if f.name != self._sync_state_file.name]

        logger.info(f"Found {len(peer_files)} peer config files")

        for peer_file in peer_files:
            peer_config = self._load_peer_from_file(peer_file)
            if peer_config:
                self._peers_cache[peer_config.peer_id] = peer_config

        logger.info(f"Loaded {len(self._peers_cache)} peer configs")

        # Load sync state
        self._sync_status_cache = self._load_sync_state_file()

        # Initialize sync status for any peers without one
        for peer_id in self._peers_cache.keys():
            if peer_id not in self._sync_status_cache:
                self._sync_status_cache[peer_id] = PeerSyncStatus(peer_id=peer_id)

        logger.info(
            f"Peer federation loaded: {len(self._peers_cache)} peers, "
            f"{len(self._sync_status_cache)} sync statuses"
        )
