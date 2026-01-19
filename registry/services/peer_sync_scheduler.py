"""
Scheduler for automatic peer registry synchronization.

This module provides background scheduling for periodic sync operations
with configurable intervals per peer. Supports graceful shutdown and
dynamic peer configuration changes.

Based on: Implementation plan Sub-Feature 6
"""

import asyncio
import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Optional, Set

from ..schemas.peer_federation_schema import (
    MIN_SYNC_INTERVAL_MINUTES,
    PeerRegistryConfig,
)
from .peer_federation_service import get_peer_federation_service


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


# Constants
DEFAULT_CHECK_INTERVAL_SECONDS: int = 30  # How often to check if peers need syncing
SYNC_BUFFER_SECONDS: int = 60  # Buffer before considering a sync overdue


def _should_sync_peer(
    peer_config: PeerRegistryConfig,
    last_synced_at: Optional[datetime],
) -> bool:
    """
    Determine if a peer should be synced based on its interval.

    Args:
        peer_config: Peer configuration with sync_interval_minutes
        last_synced_at: When the peer was last synced (None if never)

    Returns:
        True if peer should be synced now
    """
    if not peer_config.enabled:
        return False

    # If never synced, sync now
    if last_synced_at is None:
        logger.debug(f"Peer '{peer_config.peer_id}' has never been synced, scheduling")
        return True

    # Calculate time since last sync
    now = datetime.now(timezone.utc)

    # Ensure last_synced_at is timezone-aware
    if last_synced_at.tzinfo is None:
        last_synced_at = last_synced_at.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - last_synced_at).total_seconds()
    # Handle clock skew - elapsed time should never be negative
    elapsed_seconds = max(0.0, elapsed_seconds)
    interval_seconds = peer_config.sync_interval_minutes * 60

    # Check if enough time has passed
    if elapsed_seconds >= interval_seconds:
        logger.debug(
            f"Peer '{peer_config.peer_id}' is due for sync "
            f"(elapsed={elapsed_seconds:.0f}s, interval={interval_seconds}s)"
        )
        return True

    return False


def _get_next_sync_seconds(
    peer_config: PeerRegistryConfig,
    last_synced_at: Optional[datetime],
) -> float:
    """
    Calculate seconds until next scheduled sync for a peer.

    Args:
        peer_config: Peer configuration
        last_synced_at: When the peer was last synced

    Returns:
        Seconds until next sync (0 if overdue or never synced)
    """
    if last_synced_at is None:
        return 0.0

    now = datetime.now(timezone.utc)

    # Ensure last_synced_at is timezone-aware
    if last_synced_at.tzinfo is None:
        last_synced_at = last_synced_at.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - last_synced_at).total_seconds()
    # Handle clock skew - elapsed time should never be negative
    elapsed_seconds = max(0.0, elapsed_seconds)
    interval_seconds = peer_config.sync_interval_minutes * 60
    remaining = interval_seconds - elapsed_seconds

    return max(0.0, remaining)


class PeerSyncScheduler:
    """
    Background scheduler for periodic peer synchronization.

    Implements singleton pattern for application-wide scheduling.
    Supports dynamic peer additions/removals and graceful shutdown.
    """

    _instance: Optional["PeerSyncScheduler"] = None
    _lock: Lock = Lock()

    def __new__(cls) -> "PeerSyncScheduler":
        """Singleton pattern with thread-safe double-checked locking."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize scheduler with empty state."""
        if self._initialized:
            return

        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._syncing_peers: Set[str] = set()  # Track peers currently syncing
        self._sync_lock: Lock = Lock()  # Protect syncing_peers set
        self._check_interval: int = DEFAULT_CHECK_INTERVAL_SECONDS

        self._initialized = True
        logger.info("PeerSyncScheduler initialized")

    @property
    def is_running(self) -> bool:
        """Check if scheduler is currently running."""
        return self._running

    @property
    def syncing_peers(self) -> Set[str]:
        """Get set of peer IDs currently being synced."""
        with self._sync_lock:
            return self._syncing_peers.copy()

    def _is_peer_syncing(
        self,
        peer_id: str,
    ) -> bool:
        """
        Check if a peer is currently being synced.

        Args:
            peer_id: Peer identifier

        Returns:
            True if sync is in progress for this peer
        """
        with self._sync_lock:
            return peer_id in self._syncing_peers

    def _mark_peer_syncing(
        self,
        peer_id: str,
        syncing: bool,
    ) -> None:
        """
        Mark a peer as syncing or not syncing.

        Args:
            peer_id: Peer identifier
            syncing: True to mark as syncing, False to mark as complete
        """
        with self._sync_lock:
            if syncing:
                self._syncing_peers.add(peer_id)
                logger.debug(f"Marked peer '{peer_id}' as syncing")
            else:
                self._syncing_peers.discard(peer_id)
                logger.debug(f"Marked peer '{peer_id}' as sync complete")

    async def _sync_peer_safe(
        self,
        peer_id: str,
    ) -> None:
        """
        Safely sync a peer with error handling and duplicate prevention.

        Args:
            peer_id: Peer identifier to sync
        """
        # Check if already syncing (SC10: prevent duplicate syncs)
        if self._is_peer_syncing(peer_id):
            logger.debug(
                f"Skipping sync for peer '{peer_id}': already in progress"
            )
            return

        self._mark_peer_syncing(peer_id, True)

        try:
            service = get_peer_federation_service()

            # Re-check if peer is still enabled (could have changed)
            try:
                peer_config = service.get_peer(peer_id)
                if not peer_config.enabled:
                    logger.debug(
                        f"Skipping sync for peer '{peer_id}': disabled"
                    )
                    return
            except ValueError:
                # Peer was removed
                logger.debug(f"Peer '{peer_id}' no longer exists, skipping sync")
                return

            logger.info(f"Scheduled sync starting for peer '{peer_id}'")

            # sync_peer is now async, so we can await it directly
            result = await service.sync_peer(peer_id)

            if result.success:
                logger.info(
                    f"Scheduled sync completed for peer '{peer_id}': "
                    f"{result.servers_synced} servers, {result.agents_synced} agents"
                )
            else:
                logger.warning(
                    f"Scheduled sync failed for peer '{peer_id}': "
                    f"{result.error_message}"
                )

        except Exception as e:
            # SC4: Failed sync doesn't stop scheduler
            logger.error(
                f"Error during scheduled sync for peer '{peer_id}': {e}",
                exc_info=True,
            )
        finally:
            self._mark_peer_syncing(peer_id, False)

    async def _scheduler_loop(self) -> None:
        """
        Main scheduler loop that checks and triggers peer syncs.

        Runs continuously until stopped, checking peer sync schedules
        at regular intervals.
        """
        logger.info(
            f"Scheduler loop started (check interval: {self._check_interval}s)"
        )

        while self._running:
            try:
                await self._check_and_sync_peers()
            except Exception as e:
                # SC4: Errors don't crash scheduler
                logger.error(
                    f"Error in scheduler loop: {e}",
                    exc_info=True,
                )

            # Wait before next check
            try:
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                logger.info("Scheduler sleep cancelled, stopping")
                break

        logger.info("Scheduler loop stopped")

    async def _check_and_sync_peers(self) -> None:
        """
        Check all peers and trigger sync for those that are due.

        Handles dynamic peer additions/removals by always fetching
        current peer list from service.
        """
        service = get_peer_federation_service()

        # Get only enabled peers (SC3: respects enabled=false)
        enabled_peers = service.list_peers(enabled=True)

        if not enabled_peers:
            logger.debug("No enabled peers to sync")
            return

        # Check each peer
        sync_tasks = []
        for peer_config in enabled_peers:
            peer_id = peer_config.peer_id

            # Get last sync time from status
            sync_status = service.get_sync_status(peer_id)
            last_synced_at = None
            if sync_status:
                last_synced_at = sync_status.last_successful_sync

            # Check if sync is due (SC2: per-peer interval)
            if _should_sync_peer(peer_config, last_synced_at):
                # Create sync task (will run concurrently)
                task = asyncio.create_task(
                    self._sync_peer_safe(peer_id)
                )
                sync_tasks.append(task)

        # Wait for all sync tasks to complete
        if sync_tasks:
            logger.debug(f"Starting {len(sync_tasks)} scheduled syncs")
            await asyncio.gather(*sync_tasks, return_exceptions=True)

    async def start(self) -> None:
        """
        Start the scheduler background task.

        SC1: Called during app startup to begin automatic scheduling.
        SC6/SC7/SC8: Dynamic peer changes are handled by re-checking
        peer list on each iteration.
        """
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True

        # Create and start the background task
        self._task = asyncio.create_task(self._scheduler_loop())

        logger.info("Peer sync scheduler started")

    async def stop(self) -> None:
        """
        Stop the scheduler gracefully.

        SC5: Ensures clean shutdown with no orphaned tasks.
        Waits for in-progress syncs to complete.
        """
        if not self._running:
            logger.warning("Scheduler not running")
            return

        logger.info("Stopping peer sync scheduler...")

        self._running = False

        # Cancel the scheduler task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Wait for any in-progress syncs to complete
        max_wait_seconds = 30
        wait_interval = 0.5
        waited = 0.0

        while self._syncing_peers and waited < max_wait_seconds:
            logger.info(
                f"Waiting for {len(self._syncing_peers)} syncs to complete: "
                f"{self._syncing_peers}"
            )
            await asyncio.sleep(wait_interval)
            waited += wait_interval

        if self._syncing_peers:
            logger.warning(
                f"Shutdown timeout: {len(self._syncing_peers)} syncs still in progress"
            )

        logger.info("Peer sync scheduler stopped")

    async def trigger_sync_all(self) -> Dict[str, bool]:
        """
        Manually trigger sync for all enabled peers.

        SC9: Called by refresh button to sync all peers immediately.

        Returns:
            Dictionary mapping peer_id to success status
        """
        logger.info("Manual sync triggered for all enabled peers")

        service = get_peer_federation_service()
        enabled_peers = service.list_peers(enabled=True)

        if not enabled_peers:
            logger.info("No enabled peers to sync")
            return {}

        # Create sync tasks for all enabled peers
        results: Dict[str, bool] = {}

        async def sync_and_record(peer_id: str) -> None:
            try:
                await self._sync_peer_safe(peer_id)
                # Check result from sync status
                status = service.get_sync_status(peer_id)
                results[peer_id] = status is not None and status.is_healthy
            except Exception as e:
                logger.error(f"Manual sync failed for '{peer_id}': {e}")
                results[peer_id] = False

        tasks = [
            asyncio.create_task(sync_and_record(peer.peer_id))
            for peer in enabled_peers
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        successful = sum(1 for v in results.values() if v)
        logger.info(
            f"Manual sync completed: {successful}/{len(results)} succeeded"
        )

        return results


# Singleton accessor function
_scheduler_instance: Optional[PeerSyncScheduler] = None


def get_peer_sync_scheduler() -> PeerSyncScheduler:
    """
    Get the singleton PeerSyncScheduler instance.

    Returns:
        PeerSyncScheduler singleton instance
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = PeerSyncScheduler()
    return _scheduler_instance
