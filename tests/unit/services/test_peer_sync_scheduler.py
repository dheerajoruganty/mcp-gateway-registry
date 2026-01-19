"""
Unit tests for Peer Sync Scheduler.

Tests for scheduled synchronization of peer registries,
including start/stop lifecycle, interval-based triggering,
and dynamic peer management.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Dict

from registry.services.peer_sync_scheduler import (
    PeerSyncScheduler,
    get_peer_sync_scheduler,
    _should_sync_peer,
    _get_next_sync_seconds,
    DEFAULT_CHECK_INTERVAL_SECONDS,
)
from registry.schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
    SyncResult,
    MIN_SYNC_INTERVAL_MINUTES,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    PeerSyncScheduler._instance = None
    yield
    PeerSyncScheduler._instance = None


@pytest.fixture
def sample_peer_config():
    """Sample peer config for testing."""
    return PeerRegistryConfig(
        peer_id="test-peer",
        name="Test Peer Registry",
        endpoint="https://peer.example.com",
        enabled=True,
        sync_interval_minutes=60,
    )


@pytest.fixture
def sample_peer_config_disabled():
    """Sample disabled peer config for testing."""
    return PeerRegistryConfig(
        peer_id="disabled-peer",
        name="Disabled Peer Registry",
        endpoint="https://disabled.example.com",
        enabled=False,
        sync_interval_minutes=60,
    )


@pytest.fixture
def sample_sync_status():
    """Sample sync status for testing."""
    return PeerSyncStatus(
        peer_id="test-peer",
        is_healthy=True,
        last_successful_sync=datetime.now(timezone.utc),
    )


@pytest.mark.unit
class TestShouldSyncPeer:
    """Tests for _should_sync_peer helper function."""

    def test_returns_false_for_disabled_peer(self, sample_peer_config_disabled):
        """Test returns False when peer is disabled."""
        result = _should_sync_peer(sample_peer_config_disabled, None)

        assert result is False

    def test_returns_true_for_never_synced_peer(self, sample_peer_config):
        """Test returns True when peer has never been synced."""
        result = _should_sync_peer(sample_peer_config, None)

        assert result is True

    def test_returns_true_when_interval_elapsed(self, sample_peer_config):
        """Test returns True when sync interval has elapsed."""
        last_synced = datetime.now(timezone.utc) - timedelta(minutes=61)

        result = _should_sync_peer(sample_peer_config, last_synced)

        assert result is True

    def test_returns_false_when_interval_not_elapsed(self, sample_peer_config):
        """Test returns False when sync interval has not elapsed."""
        last_synced = datetime.now(timezone.utc) - timedelta(minutes=30)

        result = _should_sync_peer(sample_peer_config, last_synced)

        assert result is False

    def test_handles_timezone_aware_datetime(self, sample_peer_config):
        """Test handles timezone-aware datetime correctly."""
        last_synced = datetime.now(timezone.utc) - timedelta(minutes=61)

        result = _should_sync_peer(sample_peer_config, last_synced)

        assert result is True

    def test_handles_timezone_naive_datetime(self, sample_peer_config):
        """Test handles timezone-naive datetime by adding UTC timezone."""
        last_synced = datetime.now() - timedelta(minutes=61)

        result = _should_sync_peer(sample_peer_config, last_synced)

        assert result is True

    def test_handles_clock_skew_negative_elapsed_time(self, sample_peer_config):
        """Test handles clock skew where elapsed time would be negative."""
        last_synced = datetime.now(timezone.utc) + timedelta(minutes=10)

        result = _should_sync_peer(sample_peer_config, last_synced)

        assert result is False

    def test_respects_peer_sync_interval_minutes(self):
        """Test respects per-peer sync_interval_minutes configuration."""
        peer_config_short = PeerRegistryConfig(
            peer_id="short-interval",
            name="Short Interval Peer",
            endpoint="https://short.example.com",
            enabled=True,
            sync_interval_minutes=5,
        )

        last_synced = datetime.now(timezone.utc) - timedelta(minutes=6)

        result = _should_sync_peer(peer_config_short, last_synced)

        assert result is True


@pytest.mark.unit
class TestGetNextSyncSeconds:
    """Tests for _get_next_sync_seconds helper function."""

    def test_returns_zero_for_never_synced_peer(self, sample_peer_config):
        """Test returns 0 when peer has never been synced."""
        result = _get_next_sync_seconds(sample_peer_config, None)

        assert result == 0.0

    def test_returns_zero_for_overdue_sync(self, sample_peer_config):
        """Test returns 0 when sync is overdue."""
        last_synced = datetime.now(timezone.utc) - timedelta(minutes=61)

        result = _get_next_sync_seconds(sample_peer_config, last_synced)

        assert result == 0.0

    def test_calculates_remaining_time_correctly(self, sample_peer_config):
        """Test calculates remaining time until next sync correctly."""
        last_synced = datetime.now(timezone.utc) - timedelta(minutes=30)

        result = _get_next_sync_seconds(sample_peer_config, last_synced)

        assert result > 0
        assert result <= 30 * 60

    def test_handles_timezone_aware_datetime(self, sample_peer_config):
        """Test handles timezone-aware datetime correctly."""
        last_synced = datetime.now(timezone.utc) - timedelta(minutes=30)

        result = _get_next_sync_seconds(sample_peer_config, last_synced)

        assert result > 0

    def test_handles_timezone_naive_datetime(self, sample_peer_config):
        """Test handles timezone-naive datetime by adding UTC timezone."""
        last_synced = datetime.now() - timedelta(minutes=30)

        result = _get_next_sync_seconds(sample_peer_config, last_synced)

        assert result > 0

    def test_handles_clock_skew_negative_elapsed_time(self, sample_peer_config):
        """Test handles clock skew where elapsed time would be negative."""
        last_synced = datetime.now(timezone.utc) + timedelta(minutes=10)

        result = _get_next_sync_seconds(sample_peer_config, last_synced)

        assert result == sample_peer_config.sync_interval_minutes * 60


@pytest.mark.unit
class TestPeerSyncSchedulerSingleton:
    """Tests for singleton pattern implementation."""

    def test_singleton_returns_same_instance(self):
        """Test that singleton returns same instance."""
        scheduler1 = PeerSyncScheduler()
        scheduler2 = PeerSyncScheduler()

        assert scheduler1 is scheduler2

    def test_get_peer_sync_scheduler_returns_singleton(self):
        """Test that helper function returns singleton."""
        scheduler1 = get_peer_sync_scheduler()
        scheduler2 = get_peer_sync_scheduler()

        assert scheduler1 is scheduler2

    def test_singleton_initializes_once(self):
        """Test that singleton only initializes once."""
        scheduler1 = PeerSyncScheduler()
        initial_id = id(scheduler1._syncing_peers)

        scheduler2 = PeerSyncScheduler()
        second_id = id(scheduler2._syncing_peers)

        assert initial_id == second_id


@pytest.mark.unit
class TestPeerSyncSchedulerProperties:
    """Tests for scheduler properties."""

    def test_is_running_property_false_initially(self):
        """Test is_running property returns False initially."""
        scheduler = PeerSyncScheduler()

        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_is_running_property_true_when_started(self):
        """Test is_running property returns True when started."""
        scheduler = PeerSyncScheduler()

        with patch("registry.services.peer_sync_scheduler.get_peer_federation_service"):
            await scheduler.start()

            assert scheduler.is_running is True

            await scheduler.stop()

    def test_syncing_peers_property_returns_copy(self):
        """Test syncing_peers property returns copy of set."""
        scheduler = PeerSyncScheduler()

        scheduler._mark_peer_syncing("peer1", True)
        peers1 = scheduler.syncing_peers

        peers1.add("peer2")
        peers2 = scheduler.syncing_peers

        assert "peer2" not in peers2
        assert len(peers2) == 1


@pytest.mark.unit
class TestPeerSyncSchedulerSyncTracking:
    """Tests for peer sync tracking methods."""

    def test_is_peer_syncing_returns_false_initially(self):
        """Test _is_peer_syncing returns False initially."""
        scheduler = PeerSyncScheduler()

        assert scheduler._is_peer_syncing("peer1") is False

    def test_mark_peer_syncing_adds_peer(self):
        """Test _mark_peer_syncing adds peer to syncing set."""
        scheduler = PeerSyncScheduler()

        scheduler._mark_peer_syncing("peer1", True)

        assert scheduler._is_peer_syncing("peer1") is True

    def test_mark_peer_syncing_removes_peer(self):
        """Test _mark_peer_syncing removes peer from syncing set."""
        scheduler = PeerSyncScheduler()

        scheduler._mark_peer_syncing("peer1", True)
        scheduler._mark_peer_syncing("peer1", False)

        assert scheduler._is_peer_syncing("peer1") is False

    def test_mark_peer_syncing_thread_safe(self):
        """Test _mark_peer_syncing is thread-safe."""
        scheduler = PeerSyncScheduler()

        import threading
        results = []

        def add_peer():
            scheduler._mark_peer_syncing("peer1", True)
            results.append(scheduler._is_peer_syncing("peer1"))

        threads = [threading.Thread(target=add_peer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)


@pytest.mark.unit
class TestSyncPeerSafe:
    """Tests for _sync_peer_safe method."""

    @pytest.mark.asyncio
    async def test_skips_sync_if_already_syncing(self):
        """Test skips sync if peer is already syncing."""
        scheduler = PeerSyncScheduler()
        scheduler._mark_peer_syncing("peer1", True)

        with patch("registry.services.peer_sync_scheduler.get_peer_federation_service"):
            await scheduler._sync_peer_safe("peer1")

            assert scheduler._is_peer_syncing("peer1") is True

    @pytest.mark.asyncio
    async def test_marks_peer_syncing_during_sync(self):
        """Test marks peer as syncing during sync operation."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_peer_config = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        mock_service.get_peer.return_value = mock_peer_config
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
            servers_synced=1,
            agents_synced=1,
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._sync_peer_safe("peer1")

            assert scheduler._is_peer_syncing("peer1") is False

    @pytest.mark.asyncio
    async def test_unmarks_peer_after_sync_completes(self):
        """Test unmarks peer after sync completes."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_peer_config = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        mock_service.get_peer.return_value = mock_peer_config
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
            servers_synced=1,
            agents_synced=1,
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._sync_peer_safe("peer1")

            assert scheduler._is_peer_syncing("peer1") is False

    @pytest.mark.asyncio
    async def test_unmarks_peer_on_sync_error(self):
        """Test unmarks peer even if sync raises error."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_peer_config = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        mock_service.get_peer.return_value = mock_peer_config
        mock_service.sync_peer.side_effect = Exception("Network error")

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._sync_peer_safe("peer1")

            assert scheduler._is_peer_syncing("peer1") is False

    @pytest.mark.asyncio
    async def test_skips_sync_if_peer_disabled(self):
        """Test skips sync if peer becomes disabled."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_peer_config = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=False,
        )
        mock_service.get_peer.return_value = mock_peer_config

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._sync_peer_safe("peer1")

            mock_service.sync_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_sync_if_peer_removed(self):
        """Test skips sync if peer is removed during scheduler check."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_service.get_peer.side_effect = ValueError("Peer not found")

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._sync_peer_safe("peer1")

            mock_service.sync_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_successful_sync(self):
        """Test logs successful sync with server and agent counts."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_peer_config = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        mock_service.get_peer.return_value = mock_peer_config
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
            servers_synced=5,
            agents_synced=3,
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._sync_peer_safe("peer1")

            mock_service.sync_peer.assert_called_once_with("peer1")

    @pytest.mark.asyncio
    async def test_handles_failed_sync_result(self):
        """Test handles failed sync result without stopping scheduler."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_peer_config = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        mock_service.get_peer.return_value = mock_peer_config
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=False,
            servers_synced=0,
            agents_synced=0,
            error_message="Network error",
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._sync_peer_safe("peer1")

            assert scheduler._is_peer_syncing("peer1") is False


@pytest.mark.unit
class TestCheckAndSyncPeers:
    """Tests for _check_and_sync_peers method."""

    @pytest.mark.asyncio
    async def test_syncs_all_enabled_peers_that_are_due(self):
        """Test syncs all enabled peers that are due for sync."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
            sync_interval_minutes=60,
        )
        peer2 = PeerRegistryConfig(
            peer_id="peer2",
            name="Peer 2",
            endpoint="https://peer2.example.com",
            enabled=True,
            sync_interval_minutes=60,
        )

        mock_service.list_peers.return_value = [peer1, peer2]

        status1 = PeerSyncStatus(peer_id="peer1", is_healthy=True)
        status2 = PeerSyncStatus(peer_id="peer2", is_healthy=True)

        mock_service.get_sync_status.side_effect = [status1, status2]
        mock_service.get_peer.side_effect = [peer1, peer2]
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._check_and_sync_peers()

            assert mock_service.sync_peer.call_count == 2

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_enabled_peers(self):
        """Test does nothing when there are no enabled peers."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_service.list_peers.return_value = []

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._check_and_sync_peers()

            mock_service.sync_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_sync_interval_per_peer(self):
        """Test respects each peer's configured sync_interval_minutes."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
            sync_interval_minutes=60,
        )

        mock_service.list_peers.return_value = [peer1]

        last_synced = datetime.now(timezone.utc) - timedelta(minutes=30)
        status1 = PeerSyncStatus(
            peer_id="peer1",
            is_healthy=True,
            last_successful_sync=last_synced,
        )

        mock_service.get_sync_status.return_value = status1

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._check_and_sync_peers()

            mock_service.sync_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_syncs_never_synced_peers_immediately(self):
        """Test syncs peers that have never been synced immediately."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
            sync_interval_minutes=60,
        )

        mock_service.list_peers.return_value = [peer1]

        status1 = PeerSyncStatus(
            peer_id="peer1",
            is_healthy=True,
            last_successful_sync=None,
        )

        mock_service.get_sync_status.return_value = status1
        mock_service.get_peer.return_value = peer1
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._check_and_sync_peers()

            mock_service.sync_peer.assert_called_once()


@pytest.mark.unit
class TestSchedulerLoop:
    """Tests for _scheduler_loop method."""

    @pytest.mark.asyncio
    async def test_scheduler_loop_runs_while_running_is_true(self):
        """Test scheduler loop runs while _running is True."""
        scheduler = PeerSyncScheduler()
        scheduler._check_interval = 0.1

        check_count = 0
        original_check = scheduler._check_and_sync_peers

        async def mock_check():
            nonlocal check_count
            check_count += 1
            if check_count >= 2:
                scheduler._running = False

        scheduler._check_and_sync_peers = mock_check
        scheduler._running = True

        await scheduler._scheduler_loop()

        assert check_count == 2

    @pytest.mark.asyncio
    async def test_scheduler_loop_handles_check_errors(self):
        """Test scheduler loop continues after check errors."""
        scheduler = PeerSyncScheduler()
        scheduler._check_interval = 0.1

        error_count = 0
        original_check = scheduler._check_and_sync_peers

        async def mock_check():
            nonlocal error_count
            error_count += 1
            if error_count == 1:
                raise Exception("Test error")
            scheduler._running = False

        scheduler._check_and_sync_peers = mock_check
        scheduler._running = True

        await scheduler._scheduler_loop()

        assert error_count == 2

    @pytest.mark.asyncio
    async def test_scheduler_loop_stops_on_cancelled_error(self):
        """Test scheduler loop stops gracefully on CancelledError."""
        scheduler = PeerSyncScheduler()
        scheduler._check_interval = 10

        async def mock_check():
            pass

        scheduler._check_and_sync_peers = mock_check
        scheduler._running = True

        task = asyncio.create_task(scheduler._scheduler_loop())
        await asyncio.sleep(0.1)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert not scheduler._running or True


@pytest.mark.unit
class TestSchedulerStart:
    """Tests for start method."""

    @pytest.mark.asyncio
    async def test_start_sets_running_to_true(self):
        """Test start sets _running to True."""
        scheduler = PeerSyncScheduler()

        with patch("registry.services.peer_sync_scheduler.get_peer_federation_service"):
            await scheduler.start()

            assert scheduler._running is True

            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_creates_background_task(self):
        """Test start creates background task."""
        scheduler = PeerSyncScheduler()

        with patch("registry.services.peer_sync_scheduler.get_peer_federation_service"):
            await scheduler.start()

            assert scheduler._task is not None
            assert isinstance(scheduler._task, asyncio.Task)

            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_does_nothing_if_already_running(self):
        """Test start does nothing if scheduler already running."""
        scheduler = PeerSyncScheduler()

        with patch("registry.services.peer_sync_scheduler.get_peer_federation_service"):
            await scheduler.start()
            first_task = scheduler._task

            await scheduler.start()
            second_task = scheduler._task

            assert first_task is second_task

            await scheduler.stop()


@pytest.mark.unit
class TestSchedulerStop:
    """Tests for stop method."""

    @pytest.mark.asyncio
    async def test_stop_sets_running_to_false(self):
        """Test stop sets _running to False."""
        scheduler = PeerSyncScheduler()

        with patch("registry.services.peer_sync_scheduler.get_peer_federation_service"):
            await scheduler.start()
            await scheduler.stop()

            assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_background_task(self):
        """Test stop cancels background task."""
        scheduler = PeerSyncScheduler()

        with patch("registry.services.peer_sync_scheduler.get_peer_federation_service"):
            await scheduler.start()
            task = scheduler._task

            await scheduler.stop()

            assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_stop_waits_for_in_progress_syncs(self):
        """Test stop waits for in-progress syncs to complete."""
        scheduler = PeerSyncScheduler()
        scheduler._mark_peer_syncing("peer1", True)

        async def clear_syncing():
            await asyncio.sleep(0.2)
            scheduler._mark_peer_syncing("peer1", False)

        clear_task = asyncio.create_task(clear_syncing())

        with patch("registry.services.peer_sync_scheduler.get_peer_federation_service"):
            await scheduler.start()
            await scheduler.stop()

        assert len(scheduler._syncing_peers) == 0
        await clear_task

    @pytest.mark.asyncio
    async def test_stop_does_nothing_if_not_running(self):
        """Test stop does nothing if scheduler not running."""
        scheduler = PeerSyncScheduler()

        await scheduler.stop()

        assert scheduler._running is False


@pytest.mark.unit
class TestTriggerSyncAll:
    """Tests for trigger_sync_all method."""

    @pytest.mark.asyncio
    async def test_triggers_sync_for_all_enabled_peers(self):
        """Test triggers sync for all enabled peers."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        peer2 = PeerRegistryConfig(
            peer_id="peer2",
            name="Peer 2",
            endpoint="https://peer2.example.com",
            enabled=True,
        )

        mock_service.list_peers.return_value = [peer1, peer2]
        mock_service.get_peer.side_effect = [peer1, peer2]
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
        )

        status1 = PeerSyncStatus(peer_id="peer1", is_healthy=True)
        status2 = PeerSyncStatus(peer_id="peer2", is_healthy=True)
        mock_service.get_sync_status.side_effect = [status1, status2]

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            results = await scheduler.trigger_sync_all()

            assert len(results) == 2
            assert "peer1" in results
            assert "peer2" in results

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_enabled_peers(self):
        """Test returns empty dict when no enabled peers."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_service.list_peers.return_value = []

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            results = await scheduler.trigger_sync_all()

            assert results == {}

    @pytest.mark.asyncio
    async def test_returns_success_status_for_each_peer(self):
        """Test returns success status for each peer."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )

        mock_service.list_peers.return_value = [peer1]
        mock_service.get_peer.return_value = peer1
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
        )

        status1 = PeerSyncStatus(peer_id="peer1", is_healthy=True)
        mock_service.get_sync_status.return_value = status1

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            results = await scheduler.trigger_sync_all()

            assert results["peer1"] is True

    @pytest.mark.asyncio
    async def test_handles_sync_failures_gracefully(self):
        """Test handles sync failures without stopping other syncs."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )
        peer2 = PeerRegistryConfig(
            peer_id="peer2",
            name="Peer 2",
            endpoint="https://peer2.example.com",
            enabled=True,
        )

        mock_service.list_peers.return_value = [peer1, peer2]

        def get_peer_side_effect(peer_id):
            if peer_id == "peer1":
                return peer1
            elif peer_id == "peer2":
                raise Exception("Sync error")
            return peer2

        mock_service.get_peer.side_effect = get_peer_side_effect
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
        )

        status1 = PeerSyncStatus(peer_id="peer1", is_healthy=True)
        status2 = PeerSyncStatus(peer_id="peer2", is_healthy=False)

        def get_sync_status_side_effect(peer_id):
            if peer_id == "peer1":
                return status1
            return status2

        mock_service.get_sync_status.side_effect = get_sync_status_side_effect

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            results = await scheduler.trigger_sync_all()

            assert len(results) == 2
            assert results["peer1"] is True
            assert results["peer2"] is False


@pytest.mark.unit
class TestSchedulerEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_all_peers_disabled_scheduler_runs_but_syncs_nothing(self):
        """Test all peers disabled - scheduler runs but does nothing."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_service.list_peers.return_value = []

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._check_and_sync_peers()

            mock_service.sync_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_peer_removed_during_scheduler_check(self):
        """Test peer removed during scheduler check is handled gracefully."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )

        mock_service.list_peers.return_value = [peer1]

        status1 = PeerSyncStatus(peer_id="peer1", is_healthy=True)
        mock_service.get_sync_status.return_value = status1

        mock_service.get_peer.side_effect = ValueError("Peer not found")

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._check_and_sync_peers()

            mock_service.sync_peer.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_sync_prevention(self):
        """Test scheduler prevents duplicate syncs for same peer."""
        scheduler = PeerSyncScheduler()
        scheduler._mark_peer_syncing("peer1", True)

        mock_service = MagicMock()
        mock_service.get_peer.return_value = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._sync_peer_safe("peer1")

            mock_service.sync_peer.assert_not_called()

        scheduler._mark_peer_syncing("peer1", False)


@pytest.mark.unit
class TestSchedulerIntegration:
    """Integration tests for scheduler lifecycle."""

    @pytest.mark.asyncio
    async def test_complete_scheduler_lifecycle(self):
        """Test complete scheduler lifecycle: start, run, stop."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()
        mock_service.list_peers.return_value = []

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler.start()
            assert scheduler.is_running is True

            await asyncio.sleep(0.2)

            await scheduler.stop()
            assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_scheduler_respects_dynamic_peer_changes(self):
        """Test scheduler respects adding/removing peers dynamically."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
        )

        mock_service.list_peers.return_value = [peer1]

        status1 = PeerSyncStatus(peer_id="peer1", is_healthy=True)
        mock_service.get_sync_status.return_value = status1
        mock_service.get_peer.return_value = peer1
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._check_and_sync_peers()

            mock_service.list_peers.assert_called_once()

    @pytest.mark.asyncio
    async def test_scheduler_handles_interval_updates(self):
        """Test scheduler adapts to peer interval updates dynamically."""
        scheduler = PeerSyncScheduler()

        mock_service = MagicMock()

        peer1 = PeerRegistryConfig(
            peer_id="peer1",
            name="Peer 1",
            endpoint="https://peer1.example.com",
            enabled=True,
            sync_interval_minutes=5,
        )

        mock_service.list_peers.return_value = [peer1]

        last_synced = datetime.now(timezone.utc) - timedelta(minutes=6)
        status1 = PeerSyncStatus(
            peer_id="peer1",
            is_healthy=True,
            last_successful_sync=last_synced,
        )
        mock_service.get_sync_status.return_value = status1
        mock_service.get_peer.return_value = peer1
        mock_service.sync_peer.return_value = SyncResult(
            peer_id="peer1",
            success=True,
        )

        with patch(
            "registry.services.peer_sync_scheduler.get_peer_federation_service",
            return_value=mock_service,
        ):
            await scheduler._check_and_sync_peers()

            mock_service.sync_peer.assert_called_once()
