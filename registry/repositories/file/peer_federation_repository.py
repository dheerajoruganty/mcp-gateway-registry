"""File-based repository for peer federation configuration storage."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ...core.config import settings
from ...schemas.peer_federation_schema import PeerRegistryConfig, PeerSyncStatus
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
    """File-based implementation of peer federation repository."""

    def __init__(
        self,
        peers_dir: Optional[Path] = None,
        sync_state_file: Optional[Path] = None,
    ):
        """
        Initialize file-based peer federation repository.

        Args:
            peers_dir: Directory for peer config files (default: from settings)
            sync_state_file: Path to sync state file (default: from settings)
        """
        if peers_dir is None:
            peers_dir = settings.peers_dir

        if sync_state_file is None:
            sync_state_file = settings.peer_sync_state_file_path

        self._peers_dir = peers_dir
        self._sync_state_file = sync_state_file

        # Ensure directory exists
        self._peers_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Initialized File PeerFederationRepository with directory: {self._peers_dir}, "
            f"sync state file: {self._sync_state_file}"
        )

    async def get_peer(
        self,
        peer_id: str,
    ) -> Optional[PeerRegistryConfig]:
        """Get peer configuration by ID."""
        try:
            file_path = _get_safe_file_path(peer_id, self._peers_dir)

            if not file_path.exists():
                logger.debug(f"Peer config file not found: {file_path}")
                return None

            with open(file_path, "r") as f:
                data = json.load(f)

            # Ensure peer_id is set
            if "peer_id" not in data:
                data["peer_id"] = peer_id

            peer = PeerRegistryConfig(**data)
            logger.debug(f"Retrieved peer config from file: {peer_id}")
            return peer

        except ValueError as e:
            logger.error(f"Invalid peer_id: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse peer config JSON {peer_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to read peer config {peer_id}: {e}", exc_info=True)
            return None

    async def list_peers(
        self,
        enabled: Optional[bool] = None,
    ) -> List[PeerRegistryConfig]:
        """List all peer configurations."""
        try:
            if not self._peers_dir.exists():
                return []

            peers = []
            for file_path in self._peers_dir.glob("*.json"):
                # Skip sync state file if it's in the same directory
                if file_path.name == self._sync_state_file.name:
                    continue

                try:
                    with open(file_path, "r") as f:
                        data = json.load(f)

                    # Ensure peer_id is set
                    if "peer_id" not in data:
                        data["peer_id"] = file_path.stem

                    peer = PeerRegistryConfig(**data)

                    # Filter by enabled status if specified
                    if enabled is not None and peer.enabled != enabled:
                        continue

                    peers.append(peer)

                except Exception as e:
                    logger.error(f"Failed to read peer config file {file_path}: {e}")
                    continue

            logger.info(f"Listed {len(peers)} peer configs from files")
            return peers

        except Exception as e:
            logger.error(f"Failed to list peer configs: {e}", exc_info=True)
            return []

    async def save_peer(
        self,
        peer: PeerRegistryConfig,
    ) -> PeerRegistryConfig:
        """Save or update peer configuration."""
        try:
            peer_id = peer.peer_id
            _validate_peer_id(peer_id)

            file_path = _get_safe_file_path(peer_id, self._peers_dir)

            # Ensure directory exists
            self._peers_dir.mkdir(parents=True, exist_ok=True)

            # Check if exists
            existing = None
            if file_path.exists():
                with open(file_path, "r") as f:
                    existing = json.load(f)

            # Prepare document
            doc = peer.model_dump(mode="json")

            now = datetime.now(timezone.utc).isoformat()
            if existing:
                doc["created_at"] = existing.get("created_at", now)
                doc["updated_at"] = now
            else:
                doc["created_at"] = now
                doc["updated_at"] = now

            # Write to file
            with open(file_path, "w") as f:
                json.dump(doc, f, indent=2)

            logger.info(f"Saved peer config to file: {peer_id} -> {file_path}")
            return peer

        except ValueError as e:
            logger.error(f"Invalid peer_id: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to save peer config {peer.peer_id}: {e}", exc_info=True)
            raise

    async def delete_peer(
        self,
        peer_id: str,
    ) -> bool:
        """Delete peer configuration."""
        try:
            file_path = _get_safe_file_path(peer_id, self._peers_dir)

            if not file_path.exists():
                logger.warning(f"Peer config file not found for deletion: {file_path}")
                return False

            file_path.unlink()
            logger.info(f"Deleted peer config file: {peer_id}")
            return True

        except ValueError as e:
            logger.error(f"Invalid peer_id: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete peer config {peer_id}: {e}", exc_info=True)
            return False

    async def get_sync_state(
        self,
        peer_id: str,
    ) -> Optional[PeerSyncStatus]:
        """Get sync state for a peer."""
        try:
            if not self._sync_state_file.exists():
                logger.debug(f"Sync state file not found: {self._sync_state_file}")
                return None

            with open(self._sync_state_file, "r") as f:
                all_states = json.load(f)

            if peer_id not in all_states:
                logger.debug(f"Sync state not found for peer: {peer_id}")
                return None

            state_data = all_states[peer_id]
            state_data["peer_id"] = peer_id

            state = PeerSyncStatus(**state_data)
            logger.debug(f"Retrieved sync state: {peer_id}")
            return state

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse sync state JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get sync state {peer_id}: {e}", exc_info=True)
            return None

    async def save_sync_state(
        self,
        peer_id: str,
        state: PeerSyncStatus,
    ) -> bool:
        """Save sync state for a peer."""
        try:
            # Ensure parent directory exists
            self._sync_state_file.parent.mkdir(parents=True, exist_ok=True)

            # Load existing states
            all_states = {}
            if self._sync_state_file.exists():
                with open(self._sync_state_file, "r") as f:
                    all_states = json.load(f)

            # Update state for this peer
            state_data = state.model_dump(mode="json")
            state_data.pop("peer_id", None)  # Don't store peer_id in value
            all_states[peer_id] = state_data

            # Write back
            with open(self._sync_state_file, "w") as f:
                json.dump(all_states, f, indent=2)

            logger.debug(f"Saved sync state: {peer_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save sync state {peer_id}: {e}", exc_info=True)
            return False

    async def delete_sync_state(
        self,
        peer_id: str,
    ) -> bool:
        """Delete sync state for a peer."""
        try:
            if not self._sync_state_file.exists():
                logger.debug(f"Sync state file not found: {self._sync_state_file}")
                return False

            with open(self._sync_state_file, "r") as f:
                all_states = json.load(f)

            if peer_id not in all_states:
                logger.debug(f"Sync state not found for deletion: {peer_id}")
                return False

            del all_states[peer_id]

            with open(self._sync_state_file, "w") as f:
                json.dump(all_states, f, indent=2)

            logger.info(f"Deleted sync state: {peer_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete sync state {peer_id}: {e}", exc_info=True)
            return False

    async def list_all_sync_states(self) -> Dict[str, PeerSyncStatus]:
        """List all sync states."""
        try:
            if not self._sync_state_file.exists():
                logger.debug(f"Sync state file not found: {self._sync_state_file}")
                return {}

            with open(self._sync_state_file, "r") as f:
                all_states = json.load(f)

            states = {}
            for peer_id, state_data in all_states.items():
                try:
                    state_data["peer_id"] = peer_id
                    state = PeerSyncStatus(**state_data)
                    states[peer_id] = state
                except Exception as e:
                    logger.error(f"Failed to parse sync state for {peer_id}: {e}")
                    continue

            logger.info(f"Listed {len(states)} sync states from file")
            return states

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse sync state JSON: {e}")
            return {}
        except Exception as e:
            logger.error(f"Failed to list sync states: {e}", exc_info=True)
            return {}

    async def load_all(self) -> None:
        """
        Load/reload all peer configurations and sync states.

        For file-based repository, this validates that files are readable.
        """
        logger.info(f"Loading peer federation data from {self._peers_dir}...")

        # Ensure directory exists
        self._peers_dir.mkdir(parents=True, exist_ok=True)

        # Count files
        peer_files = list(self._peers_dir.glob("*.json"))
        # Exclude sync state file if it's in the peers directory
        peer_files = [f for f in peer_files if f.name != self._sync_state_file.name]

        logger.info(f"Found {len(peer_files)} peer config files in {self._peers_dir}")

        # Load sync states
        if self._sync_state_file.exists():
            states = await self.list_all_sync_states()
            logger.info(f"Loaded {len(states)} sync states from {self._sync_state_file}")
        else:
            logger.info(f"No sync state file found at {self._sync_state_file}")

        logger.info("File peer federation repository loaded")
