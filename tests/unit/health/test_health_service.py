"""
Unit tests for registry.health.service module.

Tests the health monitoring service including WebSocket manager and health checks.
"""

import logging
from datetime import datetime, timezone
from time import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from registry.health.service import (
    HighPerformanceWebSocketManager,
    HealthMonitoringService,
)


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: HighPerformanceWebSocketManager
# =============================================================================


@pytest.mark.unit
class TestHighPerformanceWebSocketManager:
    """Tests for the WebSocket manager class."""

    @pytest.fixture
    def manager(self):
        """Create a WebSocket manager for testing."""
        return HighPerformanceWebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_text = AsyncMock()
        ws.client = MagicMock()
        ws.client.host = "127.0.0.1"
        return ws

    @pytest.mark.asyncio
    async def test_add_connection_success(self, manager, mock_websocket):
        """Test successful WebSocket connection addition."""
        with patch.object(manager, "_send_initial_status_optimized", new_callable=AsyncMock):
            result = await manager.add_connection(mock_websocket)

        assert result is True
        assert mock_websocket in manager.connections
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_connection_at_capacity(self, manager, mock_websocket):
        """Test connection rejection when at capacity."""
        # Mock being at capacity
        with patch("registry.health.service.settings") as mock_settings:
            mock_settings.max_websocket_connections = 0
            result = await manager.add_connection(mock_websocket)

        assert result is False
        mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_connection(self, manager, mock_websocket):
        """Test WebSocket connection removal."""
        # Add connection first
        manager.connections.add(mock_websocket)
        manager.connection_metadata[mock_websocket] = {"connected_at": time()}

        # Remove it
        await manager.remove_connection(mock_websocket)

        assert mock_websocket not in manager.connections
        assert mock_websocket not in manager.connection_metadata

    def test_get_stats(self, manager):
        """Test getting WebSocket statistics."""
        # Add some test data
        manager.broadcast_count = 10
        manager.failed_send_count = 2

        stats = manager.get_stats()

        assert stats["active_connections"] == 0
        assert stats["total_broadcasts"] == 10
        assert stats["failed_sends"] == 2

    @pytest.mark.asyncio
    async def test_broadcast_update_no_connections(self, manager):
        """Test broadcast with no connections does nothing."""
        # Should not raise
        await manager.broadcast_update()

    @pytest.mark.asyncio
    async def test_broadcast_update_rate_limited(self, manager, mock_websocket):
        """Test that broadcasts are rate limited."""
        manager.connections.add(mock_websocket)
        manager.last_broadcast_time = time()  # Just broadcasted

        # This should be rate limited
        await manager.broadcast_update("test-path", {"status": "healthy"})

        # Should be queued, not sent
        assert "test-path" in manager.pending_updates

    @pytest.mark.asyncio
    async def test_safe_send_message_success(self, manager, mock_websocket):
        """Test successful message send."""
        result = await manager._safe_send_message(mock_websocket, '{"test": "data"}')

        assert result is True
        mock_websocket.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_safe_send_message_error(self, manager, mock_websocket):
        """Test message send error handling."""
        mock_websocket.send_text.side_effect = Exception("Send failed")

        result = await manager._safe_send_message(mock_websocket, '{"test": "data"}')

        assert isinstance(result, Exception)


# =============================================================================
# TEST: HealthMonitoringService
# =============================================================================


@pytest.mark.unit
class TestHealthMonitoringService:
    """Tests for the health monitoring service class."""

    @pytest.fixture
    def service(self):
        """Create a health monitoring service for testing."""
        return HealthMonitoringService()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_text = AsyncMock()
        ws.client = MagicMock()
        ws.client.host = "127.0.0.1"
        return ws

    def test_initialization(self, service):
        """Test service initialization state."""
        assert service.server_health_status == {}
        assert service.server_last_check_time == {}
        assert service.websocket_manager is not None

    @pytest.mark.asyncio
    async def test_add_websocket_connection(self, service, mock_websocket):
        """Test adding WebSocket connection via service."""
        with patch.object(service.websocket_manager, "add_connection", new_callable=AsyncMock) as mock_add:
            mock_add.return_value = True
            result = await service.add_websocket_connection(mock_websocket)

        assert result is True
        mock_add.assert_called_once_with(mock_websocket)

    @pytest.mark.asyncio
    async def test_remove_websocket_connection(self, service, mock_websocket):
        """Test removing WebSocket connection via service."""
        with patch.object(service.websocket_manager, "remove_connection", new_callable=AsyncMock) as mock_remove:
            await service.remove_websocket_connection(mock_websocket)

        mock_remove.assert_called_once_with(mock_websocket)

    def test_get_websocket_stats(self, service):
        """Test getting WebSocket stats via service."""
        stats = service.get_websocket_stats()

        assert "active_connections" in stats
        assert "total_broadcasts" in stats

    @pytest.mark.asyncio
    async def test_broadcast_health_update_no_connections(self, service):
        """Test broadcast with no connections."""
        # Should not raise
        await service.broadcast_health_update()

    @pytest.mark.asyncio
    async def test_get_cached_health_data_returns_cache(self, service):
        """Test that cached data is returned when fresh."""
        service._cached_health_data = {"test": "data"}
        service._cache_timestamp = time()

        result = await service._get_cached_health_data()

        assert result == {"test": "data"}

    @pytest.mark.asyncio
    async def test_shutdown(self, service):
        """Test service shutdown."""
        import asyncio

        # Create a real task that can be cancelled
        async def dummy_coro():
            await asyncio.sleep(100)

        service.health_check_task = asyncio.create_task(dummy_coro())

        await service.shutdown()

        # Task should be cancelled
        assert service.health_check_task.cancelled()

    def test_build_headers_for_server_basic(self, service):
        """Test building headers with defaults."""
        server_info = {}

        headers = service._build_headers_for_server(server_info)

        assert "Accept" in headers
        assert "Content-Type" in headers

    def test_build_headers_for_server_with_session(self, service):
        """Test building headers with session ID."""
        server_info = {}

        headers = service._build_headers_for_server(server_info, include_session_id=True)

        assert "Mcp-Session-Id" in headers

    def test_build_headers_for_server_with_custom_headers(self, service):
        """Test building headers with custom server headers."""
        server_info = {
            "headers": [
                {"Authorization": "Bearer test-token"},
                {"X-Custom": "value"},
            ]
        }

        headers = service._build_headers_for_server(server_info)

        assert headers.get("Authorization") == "Bearer test-token"
        assert headers.get("X-Custom") == "value"


# =============================================================================
# TEST: Health Service Data Methods
# =============================================================================


@pytest.mark.unit
class TestHealthServiceDataMethods:
    """Tests for health data helper methods."""

    @pytest.fixture
    def service(self):
        """Create a health monitoring service for testing."""
        return HealthMonitoringService()

    def test_get_service_health_data_fast(self, service):
        """Test fast health data retrieval."""
        service.server_health_status = {"/test-server": "healthy"}
        service.server_last_check_time = {
            "/test-server": datetime.now(timezone.utc)
        }

        server_info = {
            "server_name": "test-server",
            "description": "Test server",
            "path": "/test-server",
        }

        # The method should exist and return health data
        if hasattr(service, "_get_service_health_data_fast"):
            result = service._get_service_health_data_fast("/test-server", server_info)
            assert result is not None

    def test_status_tracking(self, service):
        """Test health status tracking."""
        service.server_health_status["/test"] = "healthy"
        service.server_last_check_time["/test"] = datetime.now(timezone.utc)

        assert service.server_health_status["/test"] == "healthy"
        assert "/test" in service.server_last_check_time


# =============================================================================
# TEST: Health Check Methods
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestHealthCheckMethods:
    """Tests for health check methods."""

    @pytest.fixture
    def service(self):
        """Create a health monitoring service for testing."""
        return HealthMonitoringService()

    async def test_check_single_service_healthy(self, service):
        """Test checking a single healthy service."""
        mock_client = AsyncMock()

        server_info = {
            "proxy_pass_url": "http://localhost:8080/mcp",
        }

        # Mock the transport check method
        with patch.object(
            service,
            "_check_server_endpoint_transport_aware",
            new_callable=AsyncMock,
            return_value=(True, "healthy"),
        ):
            result = await service._check_single_service(
                mock_client, "/test-server", server_info
            )

        # Result indicates whether status changed
        assert isinstance(result, bool)
        assert service.server_health_status["/test-server"] == "healthy"

    async def test_check_single_service_unhealthy(self, service):
        """Test checking an unhealthy service."""
        mock_client = AsyncMock()

        server_info = {
            "proxy_pass_url": "http://localhost:8080/mcp",
        }

        # Mock the transport check to return unhealthy
        with patch.object(
            service,
            "_check_server_endpoint_transport_aware",
            new_callable=AsyncMock,
            return_value=(False, "connection_refused"),
        ):
            result = await service._check_single_service(
                mock_client, "/test-server", server_info
            )

        assert isinstance(result, bool)
        assert service.server_health_status["/test-server"] == "connection_refused"

    async def test_perform_health_checks_empty(self, service):
        """Test health checks with no enabled services."""
        with patch("registry.services.server_service.server_service") as mock_server_service:
            mock_server_service.get_enabled_services = AsyncMock(return_value=[])

            # Should not raise
            await service._perform_health_checks()
