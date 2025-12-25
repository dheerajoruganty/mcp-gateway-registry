"""
Service for managing peer registry federation configurations.

This module provides CRUD operations for peer registry connections,
with file-based storage and enable/disable state management.

Based on: registry/services/server_service.py and registry/services/agent_service.py
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from ..core.config import settings
from ..schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
    SyncHistoryEntry,
    SyncResult,
)
from .federation.peer_registry_client import PeerRegistryClient
from .server_service import server_service
from .agent_service import agent_service
from ..schemas.agent_models import AgentCard


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
            logger.info(
                f"No sync state file found at {sync_state_file}, initializing empty state"
            )
            return {}

    except json.JSONDecodeError as e:
        logger.error(f"Could not parse JSON from {sync_state_file}: {e}")
        return {}
    except Exception as e:
        logger.error(
            f"Failed to read sync state file {sync_state_file}: {e}", exc_info=True
        )
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
            f for f in peer_files if f.name != settings.peer_sync_state_file_path.name
        ]

        logger.info(
            f"Found {len(peer_files)} peer config files in {settings.peers_dir}"
        )

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
            logger.info(
                f"Successfully loaded {len(self.registered_peers)} peer configs"
            )

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
                logger.error(
                    f"Peer registration failed: peer_id '{peer_id}' already exists"
                )
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

                logger.info(
                    f"Successfully removed peer '{peer_name}' with peer_id '{peer_id}'"
                )
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
        filtered_peers = [peer for peer in peers if peer.enabled == enabled]

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

    def sync_peer(
        self,
        peer_id: str,
    ) -> SyncResult:
        """
        Sync servers and agents from a single peer.

        Args:
            peer_id: Peer identifier

        Returns:
            SyncResult with sync statistics

        Raises:
            ValueError: If peer not found or disabled
        """
        # Start timing
        start_time = time.time()

        # Generate sync ID
        sync_id = f"sync-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Get peer config
        peer_config = self.get_peer(peer_id)

        # Check if peer is enabled
        if not peer_config.enabled:
            error_msg = f"Peer '{peer_id}' is disabled. Enable it before syncing."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Get current sync status for incremental sync
        sync_status = self.get_sync_status(peer_id)
        if not sync_status:
            # Initialize if not exists
            sync_status = PeerSyncStatus(peer_id=peer_id)

        since_generation = sync_status.current_generation

        logger.info(
            f"Starting sync from peer '{peer_id}' ({peer_config.name}) "
            f"with generation {since_generation}"
        )

        # Mark sync as in progress
        sync_status.sync_in_progress = True
        sync_status.last_sync_attempt = datetime.now(timezone.utc)
        self.update_sync_status(peer_id, sync_status)

        try:
            # Create PeerRegistryClient for this peer
            client = PeerRegistryClient(
                peer_config=peer_config, timeout_seconds=30, retry_attempts=3
            )

            # Fetch servers using client
            servers = client.fetch_servers(since_generation=since_generation)
            if servers is None:
                servers = []

            # Fetch agents using client
            agents = client.fetch_agents(since_generation=since_generation)
            if agents is None:
                agents = []

            logger.info(
                f"Fetched {len(servers)} servers and {len(agents)} agents "
                f"from peer '{peer_id}'"
            )

            # Store fetched items
            servers_stored = self._store_synced_servers(peer_id, servers)
            agents_stored = self._store_synced_agents(peer_id, agents)

            # Calculate duration
            duration_seconds = time.time() - start_time

            # Update sync status with success
            sync_status.sync_in_progress = False
            sync_status.last_successful_sync = datetime.now(timezone.utc)

            # Only increment generation if items were actually synced
            # This ensures incremental sync works correctly
            if servers_stored > 0 or agents_stored > 0 or since_generation == 0:
                sync_status.current_generation += 1

            sync_status.total_servers_synced = servers_stored
            sync_status.total_agents_synced = agents_stored
            sync_status.consecutive_failures = 0
            sync_status.is_healthy = True
            sync_status.last_health_check = datetime.now(timezone.utc)

            # Create history entry
            history_entry = SyncHistoryEntry(
                sync_id=sync_id,
                started_at=sync_status.last_sync_attempt,
                completed_at=datetime.now(timezone.utc),
                success=True,
                servers_synced=servers_stored,
                agents_synced=agents_stored,
                servers_orphaned=0,
                agents_orphaned=0,
                sync_generation=sync_status.current_generation,
                full_sync=(since_generation == 0),
            )
            sync_status.add_history_entry(history_entry)

            # Persist updated status
            self.update_sync_status(peer_id, sync_status)

            logger.info(
                f"Successfully synced peer '{peer_id}': "
                f"{servers_stored} servers, {agents_stored} agents "
                f"in {duration_seconds:.2f} seconds"
            )

            return SyncResult(
                success=True,
                peer_id=peer_id,
                servers_synced=servers_stored,
                agents_synced=agents_stored,
                servers_orphaned=0,
                agents_orphaned=0,
                duration_seconds=duration_seconds,
                new_generation=sync_status.current_generation,
            )

        except Exception as e:
            # Calculate duration even on failure
            duration_seconds = time.time() - start_time

            # Update sync status with failure
            sync_status.sync_in_progress = False
            sync_status.consecutive_failures += 1
            sync_status.is_healthy = False
            sync_status.last_health_check = datetime.now(timezone.utc)

            error_msg = str(e)

            # Create history entry for failure
            history_entry = SyncHistoryEntry(
                sync_id=sync_id,
                started_at=sync_status.last_sync_attempt,
                completed_at=datetime.now(timezone.utc),
                success=False,
                servers_synced=0,
                agents_synced=0,
                servers_orphaned=0,
                agents_orphaned=0,
                error_message=error_msg,
                sync_generation=sync_status.current_generation,
                full_sync=(since_generation == 0),
            )
            sync_status.add_history_entry(history_entry)

            # Persist updated status
            self.update_sync_status(peer_id, sync_status)

            logger.error(f"Failed to sync peer '{peer_id}': {error_msg}", exc_info=True)

            return SyncResult(
                success=False,
                peer_id=peer_id,
                servers_synced=0,
                agents_synced=0,
                servers_orphaned=0,
                agents_orphaned=0,
                error_message=error_msg,
                duration_seconds=duration_seconds,
                new_generation=sync_status.current_generation,
            )

    def sync_all_peers(
        self,
        enabled_only: bool = True,
    ) -> Dict[str, SyncResult]:
        """
        Sync all (or enabled) peers.

        Args:
            enabled_only: If True, only sync enabled peers

        Returns:
            Dictionary mapping peer_id to SyncResult
        """
        peers = self.list_peers(enabled=enabled_only if enabled_only else None)

        logger.info(
            f"Starting sync for {len(peers)} peers "
            f"({'enabled only' if enabled_only else 'all'})"
        )

        results = {}

        for peer in peers:
            peer_id = peer.peer_id

            try:
                logger.info(f"Syncing peer '{peer_id}' ({peer.name})...")
                result = self.sync_peer(peer_id)
                results[peer_id] = result

                if result.success:
                    logger.info(
                        f"Successfully synced '{peer_id}': "
                        f"{result.servers_synced} servers, {result.agents_synced} agents"
                    )
                else:
                    logger.error(f"Failed to sync '{peer_id}': {result.error_message}")

            except Exception as e:
                logger.error(
                    f"Unexpected error syncing peer '{peer_id}': {e}", exc_info=True
                )
                results[peer_id] = SyncResult(
                    success=False,
                    peer_id=peer_id,
                    servers_synced=0,
                    agents_synced=0,
                    servers_orphaned=0,
                    agents_orphaned=0,
                    error_message=str(e),
                    duration_seconds=0.0,
                    new_generation=0,
                )

        # Summary logging
        successful = sum(1 for r in results.values() if r.success)
        failed = len(results) - successful
        total_servers = sum(r.servers_synced for r in results.values())
        total_agents = sum(r.agents_synced for r in results.values())

        logger.info(
            f"Sync completed: {successful} succeeded, {failed} failed. "
            f"Total: {total_servers} servers, {total_agents} agents"
        )

        return results

    def _store_synced_servers(
        self,
        peer_id: str,
        servers: List[Dict[str, Any]],
    ) -> int:
        """
        Store servers fetched from a peer.

        Args:
            peer_id: Source peer identifier
            servers: List of server data dictionaries

        Returns:
            Number of servers stored/updated
        """
        stored_count = 0

        for server in servers:
            try:
                # Extract original path
                original_path = server.get("path", "")

                if not original_path:
                    logger.warning(f"Server missing 'path' field, skipping: {server}")
                    continue

                # Normalize path - ensure it starts with /
                normalized_path = original_path if original_path.startswith('/') else f'/{original_path}'

                # Prefix path with peer_id to avoid collisions
                # e.g., "/my-server" becomes "/peer-central/my-server"
                prefixed_path = f"/{peer_id}{normalized_path}"

                # Add sync_metadata to track origin
                sync_metadata = {
                    "source_peer_id": peer_id,
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                    "is_federated": True,
                    "original_path": original_path,
                }

                # Create a copy to avoid modifying original
                server_data = server.copy()
                server_data["path"] = prefixed_path
                server_data["sync_metadata"] = sync_metadata

                # Check if server already exists and store
                try:
                    existing_server = server_service.registered_servers.get(
                        prefixed_path
                    )
                    if existing_server:
                        # Update existing server - returns bool
                        success = server_service.update_server(prefixed_path, server_data)
                        if success:
                            logger.debug(f"Updated synced server: {prefixed_path}")
                            stored_count += 1
                        else:
                            logger.error(f"Failed to update server: {prefixed_path}")
                    else:
                        # Register new server - returns bool
                        success = server_service.register_server(server_data)
                        if success:
                            logger.debug(f"Registered synced server: {prefixed_path}")
                            stored_count += 1
                        else:
                            logger.error(f"Failed to register server: {prefixed_path}")

                except Exception as e:
                    logger.error(
                        f"Failed to store server '{prefixed_path}': {e}", exc_info=True
                    )

            except Exception as e:
                logger.error(
                    f"Failed to process server from peer '{peer_id}': {e}",
                    exc_info=True,
                )

        logger.info(
            f"Stored {stored_count}/{len(servers)} servers from peer '{peer_id}'"
        )
        return stored_count

    def _store_synced_agents(
        self,
        peer_id: str,
        agents: List[Dict[str, Any]],
    ) -> int:
        """
        Store agents fetched from a peer.

        Args:
            peer_id: Source peer identifier
            agents: List of agent data dictionaries

        Returns:
            Number of agents stored/updated
        """
        stored_count = 0

        for agent in agents:
            try:
                # Extract original path
                original_path = agent.get("path", "")

                if not original_path:
                    logger.warning(f"Agent missing 'path' field, skipping: {agent}")
                    continue

                # Normalize path - ensure it starts with /
                normalized_path = original_path if original_path.startswith('/') else f'/{original_path}'

                # Prefix path with peer_id to avoid collisions
                # e.g., "/code-reviewer" becomes "/peer-central/code-reviewer"
                prefixed_path = f"/{peer_id}{normalized_path}"

                # Add sync_metadata to track origin
                sync_metadata = {
                    "source_peer_id": peer_id,
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                    "is_federated": True,
                    "original_path": original_path,
                }

                # Create a copy to avoid modifying original
                agent_data = agent.copy()
                agent_data["path"] = prefixed_path
                agent_data["sync_metadata"] = sync_metadata

                # Check if agent already exists and store
                try:
                    existing_agent = agent_service.registered_agents.get(prefixed_path)

                    if existing_agent:
                        # Update existing agent - returns AgentCard on success
                        updated_agent = agent_service.update_agent(prefixed_path, agent_data)
                        if updated_agent:
                            logger.debug(f"Updated synced agent: {prefixed_path}")
                            stored_count += 1
                        else:
                            logger.error(f"Failed to update agent: {prefixed_path}")
                    else:
                        # Register new agent - create AgentCard instance
                        agent_card = AgentCard(**agent_data)
                        registered_agent = agent_service.register_agent(agent_card)
                        if registered_agent:
                            logger.debug(f"Registered synced agent: {prefixed_path}")
                            stored_count += 1
                        else:
                            logger.error(f"Failed to register agent: {prefixed_path}")

                except ValueError as e:
                    # Validation errors
                    logger.error(
                        f"Validation error storing agent '{prefixed_path}': {e}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to store agent '{prefixed_path}': {e}", exc_info=True
                    )

            except Exception as e:
                logger.error(
                    f"Failed to process agent from peer '{peer_id}': {e}", exc_info=True
                )

        logger.info(f"Stored {stored_count}/{len(agents)} agents from peer '{peer_id}'")
        return stored_count


# Global service instance
def get_peer_federation_service() -> PeerFederationService:
    """
    Get the global peer federation service instance.

    Returns:
        Singleton PeerFederationService instance
    """
    return PeerFederationService()
