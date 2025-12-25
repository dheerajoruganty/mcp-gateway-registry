"""
Service for managing peer registry federation configurations.

This module provides CRUD operations for peer registry connections,
with file-based storage and enable/disable state management.

Based on: registry/services/server_service.py and registry/services/agent_service.py
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
)


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


def _peer_id_to_filename(
    peer_id: str,
) -> str:
    """
    Convert peer ID to safe filename.

    Args:
        peer_id: Peer identifier

    Returns:
        Safe filename with .json extension
    """
    # Always append .json (peer_id should never include extension)
    return f"{peer_id}.json"


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
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '\0']
    for char in invalid_chars:
        if char in peer_id:
            raise ValueError(f"Invalid peer_id: contains invalid character '{char}'")

    # Check for reserved names
    if peer_id.lower() in ['con', 'prn', 'aux', 'nul']:
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

    filename = _peer_id_to_filename(peer_id)
    file_path = peers_dir / filename

    # Resolve to absolute path and verify it's within peers_dir
    resolved_path = file_path.resolve()
    resolved_peers_dir = peers_dir.resolve()

    if not resolved_path.is_relative_to(resolved_peers_dir):
        raise ValueError(f"Invalid peer_id: path traversal detected for '{peer_id}'")

    return file_path


def _load_peer_from_file(
    file_path: Path,
) -> Optional[PeerRegistryConfig]:
    """
    Load peer config from JSON file.

    Args:
        file_path: Path to peer JSON file

    Returns:
        PeerRegistryConfig or None if invalid
    """
    try:
        with open(file_path, "r") as f:
            peer_data = json.load(f)

            if not isinstance(peer_data, dict):
                logger.warning(f"Invalid peer data format in {file_path}")
                return None

            if "peer_id" not in peer_data:
                logger.warning(f"Missing peer_id in {file_path}")
                return None

            # Validate by creating PeerRegistryConfig instance
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


def _save_peer_to_disk(
    peer_config: PeerRegistryConfig,
    peers_dir: Path,
) -> bool:
    """
    Save peer config to individual JSON file.

    Args:
        peer_config: Peer config to save
        peers_dir: Directory for peer storage

    Returns:
        True if successful, False otherwise
    """
    try:
        peers_dir.mkdir(parents=True, exist_ok=True)

        # Use safe path function with validation
        file_path = _get_safe_file_path(peer_config.peer_id, peers_dir)

        # Convert to dict for JSON serialization
        peer_dict = peer_config.model_dump(mode="json")

        with open(file_path, "w") as f:
            json.dump(peer_dict, f, indent=2)

        logger.info(f"Successfully saved peer '{peer_config.name}' to {file_path}")
        return True

    except ValueError as e:
        logger.error(f"Invalid peer_id: {e}")
        return False
    except Exception as e:
        logger.error(
            f"Failed to save peer '{peer_config.name}' to disk: {e}",
            exc_info=True,
        )
        return False


def _load_sync_state(
    sync_state_file: Path,
) -> Dict[str, PeerSyncStatus]:
    """
    Load peer sync status from disk.

    Args:
        sync_state_file: Path to peer_sync_state.json

    Returns:
        Dictionary mapping peer_id to PeerSyncStatus
    """
    logger.info(f"Loading peer sync state from {sync_state_file}...")

    try:
        if sync_state_file.exists():
            with open(sync_state_file, "r") as f:
                state_data = json.load(f)

            if not isinstance(state_data, dict):
                logger.warning(f"Invalid state format in {sync_state_file}")
                return {}

            # Convert to PeerSyncStatus objects
            sync_status_map = {}
            for peer_id, status_dict in state_data.items():
                try:
                    sync_status = PeerSyncStatus(**status_dict)
                    sync_status_map[peer_id] = sync_status
                except Exception as e:
                    logger.error(
                        f"Failed to load sync status for peer '{peer_id}': {e}"
                    )

            logger.info(f"Loaded sync state for {len(sync_status_map)} peers")
            return sync_status_map
        else:
            logger.info(f"No sync state file found at {sync_state_file}, initializing empty state")
            return {}

    except json.JSONDecodeError as e:
        logger.error(f"Could not parse JSON from {sync_state_file}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Failed to read sync state file {sync_state_file}: {e}", exc_info=True)
        return {}


def _persist_sync_state(
    sync_status_map: Dict[str, PeerSyncStatus],
    sync_state_file: Path,
) -> None:
    """
    Persist peer sync status to disk.

    Args:
        sync_status_map: Dictionary of peer_id to PeerSyncStatus
        sync_state_file: Path to peer_sync_state.json
    """
    try:
        sync_state_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict for JSON serialization
        state_data = {
            peer_id: status.model_dump(mode="json")
            for peer_id, status in sync_status_map.items()
        }

        with open(sync_state_file, "w") as f:
            json.dump(state_data, f, indent=2)

        logger.info(f"Persisted peer sync state to {sync_state_file}")

    except Exception as e:
        logger.error(f"ERROR: Failed to persist sync state to {sync_state_file}: {e}")


class PeerFederationService:
    """Service for managing peer registry federation configurations."""

    _instance: Optional["PeerFederationService"] = None
    _lock: Lock = Lock()

    def __new__(cls) -> "PeerFederationService":
        """Singleton pattern with thread-safe double-checked locking."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize peer federation service with empty state."""
        # Singleton: only initialize once
        if self._initialized:
            return

        self.registered_peers: Dict[str, PeerRegistryConfig] = {}
        self.peer_sync_status: Dict[str, PeerSyncStatus] = {}
        self._operation_lock = Lock()  # Thread safety for CRUD operations

        self._initialized = True


    def load_peers_and_state(self) -> None:
        """Load peer configs and persisted sync state from disk."""
        logger.info(f"Loading peer configs from {settings.peers_dir}...")

        # Create peers directory if it doesn't exist
        settings.peers_dir.mkdir(parents=True, exist_ok=True)

        temp_peers = {}
        peer_files = list(settings.peers_dir.glob("*.json"))

        # Exclude sync state file
        peer_files = [
            f for f in peer_files
            if f.name != settings.peer_sync_state_file_path.name
        ]

        logger.info(f"Found {len(peer_files)} peer config files in {settings.peers_dir}")

        for file in peer_files:
            logger.debug(f"Loading peer from {file.relative_to(settings.peers_dir)}")

        if not peer_files:
            logger.warning(
                f"No peer config files found in {settings.peers_dir}. "
                "Initializing empty peer registry."
            )
            self.registered_peers = {}
        else:
            for peer_file in peer_files:
                peer_config = _load_peer_from_file(peer_file)

                if peer_config:
                    peer_id = peer_config.peer_id

                    if peer_id in temp_peers:
                        logger.warning(
                            f"Duplicate peer_id in {peer_file}: {peer_id}. "
                            "Overwriting previous definition."
                        )

                    temp_peers[peer_id] = peer_config

            self.registered_peers = temp_peers
            logger.info(f"Successfully loaded {len(self.registered_peers)} peer configs")

        # Load persisted sync state
        self._load_sync_state()


    def _load_sync_state(self) -> None:
        """Load persisted peer sync state from disk."""
        sync_status_map = _load_sync_state(settings.peer_sync_state_file_path)

        # Initialize sync status for all registered peers
        for peer_id in self.registered_peers.keys():
            if peer_id not in sync_status_map:
                # New peer not in state file - initialize empty status
                sync_status_map[peer_id] = PeerSyncStatus(peer_id=peer_id)

        self.peer_sync_status = sync_status_map
        logger.info(f"Peer sync state initialized for {len(sync_status_map)} peers")


    def _persist_sync_state(self) -> None:
        """Persist peer sync state to disk."""
        _persist_sync_state(self.peer_sync_status, settings.peer_sync_state_file_path)


    def add_peer(
        self,
        config: PeerRegistryConfig,
    ) -> PeerRegistryConfig:
        """
        Add a new peer registry configuration.

        Args:
            config: Peer registry config to add

        Returns:
            Added peer config

        Raises:
            ValueError: If peer_id already exists or is invalid
        """
        peer_id = config.peer_id

        # Validate peer_id (prevents path traversal)
        _validate_peer_id(peer_id)

        with self._operation_lock:
            # Check if peer_id already exists
            if peer_id in self.registered_peers:
                logger.error(f"Peer registration failed: peer_id '{peer_id}' already exists")
                raise ValueError(f"Peer ID '{peer_id}' already exists")

            # Set creation metadata
            if not config.created_at:
                config.created_at = datetime.now(timezone.utc)
            if not config.updated_at:
                config.updated_at = datetime.now(timezone.utc)

            # Save to disk
            if not _save_peer_to_disk(config, settings.peers_dir):
                raise ValueError(f"Failed to save peer '{config.name}' to disk")

            # Add to in-memory registry
            self.registered_peers[peer_id] = config

            # Initialize sync status
            self.peer_sync_status[peer_id] = PeerSyncStatus(peer_id=peer_id)

            # Persist sync state
            self._persist_sync_state()

            logger.info(
                f"New peer registered: '{config.name}' with peer_id '{peer_id}' "
                f"(enabled={config.enabled})"
            )

            return config


    def get_peer(
        self,
        peer_id: str,
    ) -> PeerRegistryConfig:
        """
        Get peer config by peer_id.

        Args:
            peer_id: Peer identifier

        Returns:
            Peer config

        Raises:
            ValueError: If peer not found
        """
        peer_config = self.registered_peers.get(peer_id)

        if not peer_config:
            raise ValueError(f"Peer not found: {peer_id}")

        return peer_config


    def update_peer(
        self,
        peer_id: str,
        updates: Dict[str, Any],
    ) -> PeerRegistryConfig:
        """
        Update an existing peer config.

        Args:
            peer_id: Peer identifier
            updates: Dictionary of fields to update

        Returns:
            Updated peer config

        Raises:
            ValueError: If peer not found or invalid
        """
        with self._operation_lock:
            if peer_id not in self.registered_peers:
                logger.error(f"Cannot update peer '{peer_id}': not found")
                raise ValueError(f"Peer not found: {peer_id}")

            # Get existing peer config
            existing_peer = self.registered_peers[peer_id]

            # Merge updates with existing data
            peer_dict = existing_peer.model_dump()
            peer_dict.update(updates)

            # Ensure peer_id is consistent
            peer_dict["peer_id"] = peer_id

            # Update timestamp
            peer_dict["updated_at"] = datetime.now(timezone.utc)

            # Validate updated peer
            try:
                updated_peer = PeerRegistryConfig(**peer_dict)
            except Exception as e:
                logger.error(f"Failed to validate updated peer: {e}")
                raise ValueError(f"Invalid peer update: {e}")

            # Save to disk
            if not _save_peer_to_disk(updated_peer, settings.peers_dir):
                raise ValueError("Failed to save updated peer to disk")

            # Update in-memory registry
            self.registered_peers[peer_id] = updated_peer

            logger.info(f"Peer '{updated_peer.name}' ({peer_id}) updated")

            return updated_peer


    def remove_peer(
        self,
        peer_id: str,
    ) -> bool:
        """
        Remove a peer from registry.

        Args:
            peer_id: Peer identifier

        Returns:
            True if deleted successfully

        Raises:
            ValueError: If peer not found or path traversal detected
        """
        with self._operation_lock:
            if peer_id not in self.registered_peers:
                logger.error(f"Cannot remove peer '{peer_id}': not found")
                raise ValueError(f"Peer not found: {peer_id}")

            try:
                # Get safe file path with validation (prevents path traversal)
                file_path = _get_safe_file_path(peer_id, settings.peers_dir)

                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Removed peer file: {file_path}")
                else:
                    logger.warning(f"Peer file not found: {file_path}")

                # Remove from in-memory registry
                peer_name = self.registered_peers[peer_id].name
                del self.registered_peers[peer_id]

                # Remove from sync status
                if peer_id in self.peer_sync_status:
                    del self.peer_sync_status[peer_id]

                # Persist updated sync state
                self._persist_sync_state()

                logger.info(f"Successfully removed peer '{peer_name}' with peer_id '{peer_id}'")
                return True

            except ValueError:
                # Re-raise ValueError (including path traversal errors)
                raise
            except Exception as e:
                logger.error(f"Failed to remove peer '{peer_id}': {e}", exc_info=True)
                raise ValueError(f"Failed to remove peer: {e}")


    def list_peers(
        self,
        enabled: Optional[bool] = None,
    ) -> List[PeerRegistryConfig]:
        """
        List all configured peers with optional filtering.

        Args:
            enabled: If True, return only enabled peers.
                    If False, return only disabled peers.
                    If None, return all peers.

        Returns:
            List of peer configs
        """
        peers = list(self.registered_peers.values())

        if enabled is None:
            return peers

        # Filter by enabled status
        filtered_peers = [
            peer for peer in peers
            if peer.enabled == enabled
        ]

        return filtered_peers


    def get_sync_status(
        self,
        peer_id: str,
    ) -> Optional[PeerSyncStatus]:
        """
        Get sync status for a peer.

        Args:
            peer_id: Peer identifier

        Returns:
            PeerSyncStatus or None if not found
        """
        return self.peer_sync_status.get(peer_id)


    def update_sync_status(
        self,
        peer_id: str,
        sync_status: PeerSyncStatus,
    ) -> None:
        """
        Update sync status for a peer.

        Args:
            peer_id: Peer identifier
            sync_status: Updated sync status
        """
        self.peer_sync_status[peer_id] = sync_status
        self._persist_sync_state()

        logger.info(f"Updated sync status for peer '{peer_id}'")


# Global service instance
def get_peer_federation_service() -> PeerFederationService:
    """
    Get the global peer federation service instance.

    Returns:
        Singleton PeerFederationService instance
    """
    return PeerFederationService()
