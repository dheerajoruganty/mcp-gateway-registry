"""
Unit tests for health monitoring service.
"""

import logging
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

import pytest

from registry.health.service import (
    HighPerformanceWebSocketManager,
    HealthMonitoringService,
)
from registry.constants import HealthStatus


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: HighPerformanceWebSocketManager
# =============================================================================


@pytest.mark.unit
class TestHighPerformanceWebSocketManager:
    """Tests for HighPerformanceWebSocketManager class."""

    def test_init(self):
        """Test WebSocket manager initialization."""
        manager = HighPerformanceWebSocketManager()
        assert len(manager.connections) == 0
        assert len(manager.connection_metadata) == 0
        assert len(manager.failed_connections) == 0
        assert manager.broadcast_count == 0
        assert manager.failed_send_count == 0

    @pytest.mark.asyncio
    async def test_add_connection_success(self):
        """Test adding a WebSocket connection successfully."""
        manager = HighPerformanceWebSocketManager()

        mock_websocket = AsyncMock()
        mock_websocket.client = MagicMock()
        mock_websocket.client.host = "127.0.0.1"

        with patch.object(manager, '_send_initial_status_optimized', new_callable=AsyncMock):
            result = await manager.add_connection(mock_websocket)

        assert result is True
        assert mock_websocket in manager.connections
        assert mock_websocket in manager.connection_metadata
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_connection_at_capacity(self):
        """Test connection limit enforcement."""
        manager = HighPerformanceWebSocketManager()

        with patch("registry.health.service.settings") as mock_settings:
            mock_settings.max_websocket_connections = 0  # At capacity
            mock_settings.websocket_broadcast_interval_ms = 100
            mock_settings.websocket_max_batch_size = 100
            mock_settings.websocket_cache_ttl_seconds = 1
            mock_settings.websocket_send_timeout_seconds = 5

            mock_websocket = AsyncMock()
            mock_websocket.client = None

            result = await manager.add_connection(mock_websocket)

        assert result is False
        mock_websocket.close.assert_called()

    @pytest.mark.asyncio
    async def test_remove_connection(self):
        """Test removing a WebSocket connection."""
        manager = HighPerformanceWebSocketManager()

        mock_websocket = AsyncMock()
        manager.connections.add(mock_websocket)
        manager.connection_metadata[mock_websocket] = {"connected_at": 0}
        manager.failed_connections.add(mock_websocket)

        await manager.remove_connection(mock_websocket)

        assert mock_websocket not in manager.connections
        assert mock_websocket not in manager.connection_metadata
        assert mock_websocket not in manager.failed_connections

    def test_get_stats(self):
        """Test getting performance statistics."""
        manager = HighPerformanceWebSocketManager()
        manager.broadcast_count = 5
        manager.failed_send_count = 2

        stats = manager.get_stats()

        assert stats["active_connections"] == 0
        assert stats["pending_updates"] == 0
        assert stats["total_broadcasts"] == 5
        assert stats["failed_sends"] == 2
        assert stats["failed_connections"] == 0

    @pytest.mark.asyncio
    async def test_broadcast_update_no_connections(self):
        """Test broadcast with no connections does nothing."""
        manager = HighPerformanceWebSocketManager()

        # Should not raise
        await manager.broadcast_update()

    @pytest.mark.asyncio
    async def test_safe_send_message_success(self):
        """Test successful message send."""
        manager = HighPerformanceWebSocketManager()
        mock_conn = AsyncMock()

        with patch("registry.health.service.settings") as mock_settings:
            mock_settings.websocket_send_timeout_seconds = 5
            result = await manager._safe_send_message(mock_conn, "test message")

        assert result is True
        mock_conn.send_text.assert_called_once_with("test message")

    @pytest.mark.asyncio
    async def test_safe_send_message_timeout(self):
        """Test message send timeout."""
        manager = HighPerformanceWebSocketManager()
        mock_conn = AsyncMock()
        mock_conn.send_text.side_effect = asyncio.TimeoutError()

        with patch("registry.health.service.settings") as mock_settings:
            mock_settings.websocket_send_timeout_seconds = 0.001
            result = await manager._safe_send_message(mock_conn, "test message")

        assert isinstance(result, asyncio.TimeoutError)

    @pytest.mark.asyncio
    async def test_cleanup_failed_connections(self):
        """Test cleanup of failed connections."""
        manager = HighPerformanceWebSocketManager()
        mock_conn1 = AsyncMock()
        mock_conn2 = AsyncMock()

        manager.connections.add(mock_conn1)
        manager.connections.add(mock_conn2)
        manager.connection_metadata[mock_conn1] = {}
        manager.connection_metadata[mock_conn2] = {}
        manager.failed_connections.add(mock_conn1)

        await manager._cleanup_failed_connections()

        assert mock_conn1 not in manager.connections
        assert mock_conn2 in manager.connections


# =============================================================================
# TEST: HealthMonitoringService
# =============================================================================


@pytest.mark.unit
class TestHealthMonitoringService:
    """Tests for HealthMonitoringService class."""

    def test_init(self):
        """Test service initialization."""
        service = HealthMonitoringService()
        assert isinstance(service.websocket_manager, HighPerformanceWebSocketManager)
        assert service.health_check_task is None
        assert len(service.server_health_status) == 0
        assert len(service.server_last_check_time) == 0

    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test service initialization with background task."""
        service = HealthMonitoringService()

        with patch.object(service, '_run_health_checks', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = None

            await service.initialize()

            assert service.health_check_task is not None

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test service shutdown without health check task."""
        service = HealthMonitoringService()
        service.health_check_task = None  # No task to cancel

        # Add a mock connection
        mock_conn = AsyncMock()
        service.websocket_manager.connections.add(mock_conn)

        # Should not raise
        await service.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_with_task(self):
        """Test service shutdown cancels health check task."""
        service = HealthMonitoringService()

        # Create an actual task that we can cancel
        async def infinite_loop():
            try:
                while True:
                    await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(infinite_loop())
        service.health_check_task = task

        await service.shutdown()

        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_add_websocket_connection(self):
        """Test adding a WebSocket connection through the service."""
        service = HealthMonitoringService()
        mock_websocket = AsyncMock()

        with patch.object(service.websocket_manager, 'add_connection', new_callable=AsyncMock) as mock_add:
            mock_add.return_value = True

            result = await service.add_websocket_connection(mock_websocket)

            assert result is True
            mock_add.assert_called_once_with(mock_websocket)

    @pytest.mark.asyncio
    async def test_remove_websocket_connection(self):
        """Test removing a WebSocket connection through the service."""
        service = HealthMonitoringService()
        mock_websocket = AsyncMock()
        mock_websocket.client = "test-client"

        with patch.object(service.websocket_manager, 'remove_connection', new_callable=AsyncMock) as mock_remove:
            await service.remove_websocket_connection(mock_websocket)

            mock_remove.assert_called_once_with(mock_websocket)

    def test_get_websocket_stats(self):
        """Test getting WebSocket statistics."""
        service = HealthMonitoringService()

        stats = service.get_websocket_stats()

        assert "active_connections" in stats
        assert "pending_updates" in stats
        assert "total_broadcasts" in stats

    @pytest.mark.asyncio
    async def test_broadcast_health_update_no_connections(self):
        """Test broadcast with no WebSocket connections."""
        service = HealthMonitoringService()

        # Should not raise when no connections
        await service.broadcast_health_update()

    @pytest.mark.asyncio
    async def test_get_cached_health_data_uses_cache(self):
        """Test that cached health data is returned when valid."""
        service = HealthMonitoringService()

        # Set up cached data
        service._cached_health_data = {"test": "data"}
        service._cache_timestamp = float('inf')  # Far future - cache always valid

        with patch("registry.health.service.settings") as mock_settings:
            mock_settings.websocket_cache_ttl_seconds = 10

            result = await service._get_cached_health_data()

        assert result == {"test": "data"}

    def test_build_headers_for_server_basic(self):
        """Test building headers with default values."""
        service = HealthMonitoringService()
        server_info = {}

        headers = service._build_headers_for_server(server_info)

        assert headers["Accept"] == "application/json, text/event-stream"
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_for_server_with_session_id(self):
        """Test building headers with session ID."""
        service = HealthMonitoringService()
        server_info = {}

        headers = service._build_headers_for_server(server_info, include_session_id=True)

        assert "Mcp-Session-Id" in headers

    def test_build_headers_for_server_with_custom_headers(self):
        """Test building headers with custom server headers."""
        service = HealthMonitoringService()
        server_info = {
            "headers": [
                {"X-Custom-Header": "custom-value"},
                {"Authorization": "Bearer token123"}
            ]
        }

        headers = service._build_headers_for_server(server_info)

        assert headers["X-Custom-Header"] == "custom-value"
        assert headers["Authorization"] == "Bearer token123"

    def test_build_headers_for_server_ignores_invalid_headers(self):
        """Test that invalid header formats are ignored."""
        service = HealthMonitoringService()
        server_info = {
            "headers": [
                {"valid": "header"},
                "invalid-not-a-dict",
                123
            ]
        }

        headers = service._build_headers_for_server(server_info)

        assert headers["valid"] == "header"
        # Invalid entries should be ignored

    @pytest.mark.asyncio
    async def test_check_single_service_timeout(self):
        """Test health check handles timeout."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        service_path = "/test-server"
        server_info = {"proxy_pass_url": "http://localhost:8080"}

        with patch.object(service, '_check_server_endpoint_transport_aware', new_callable=AsyncMock) as mock_check:
            import httpx
            mock_check.side_effect = httpx.TimeoutException("timeout")

            result = await service._check_single_service(mock_client, service_path, server_info)

        assert service.server_health_status[service_path] == HealthStatus.UNHEALTHY_TIMEOUT

    @pytest.mark.asyncio
    async def test_check_single_service_connection_error(self):
        """Test health check handles connection error."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        service_path = "/test-server"
        server_info = {"proxy_pass_url": "http://localhost:8080"}

        with patch.object(service, '_check_server_endpoint_transport_aware', new_callable=AsyncMock) as mock_check:
            import httpx
            mock_check.side_effect = httpx.ConnectError("connection refused")

            result = await service._check_single_service(mock_client, service_path, server_info)

        assert service.server_health_status[service_path] == HealthStatus.UNHEALTHY_CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_check_single_service_healthy(self):
        """Test health check for healthy service."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        service_path = "/test-server"
        server_info = {"proxy_pass_url": "http://localhost:8080"}

        with patch.object(service, '_check_server_endpoint_transport_aware', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (True, HealthStatus.HEALTHY)

            result = await service._check_single_service(mock_client, service_path, server_info)

        assert service.server_health_status[service_path] == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_single_service_status_changed(self):
        """Test that status change is detected."""
        service = HealthMonitoringService()
        service_path = "/test-server"

        # Set previous status to unknown
        service.server_health_status[service_path] = HealthStatus.UNKNOWN

        mock_client = AsyncMock()
        server_info = {"proxy_pass_url": "http://localhost:8080"}

        with patch.object(service, '_check_server_endpoint_transport_aware', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = (True, HealthStatus.HEALTHY)

            result = await service._check_single_service(mock_client, service_path, server_info)

        # Status changed from UNKNOWN to HEALTHY
        assert result is True


# =============================================================================
# TEST: Service health data methods
# =============================================================================


@pytest.mark.unit
class TestHealthServiceDataMethods:
    """Tests for health service data methods."""

    def test_get_service_health_data_fast_basic(self):
        """Test fast health data retrieval."""
        service = HealthMonitoringService()
        service_path = "/test-server"
        server_info = {
            "name": "Test Server",
            "proxy_pass_url": "http://localhost:8080",
            "enabled": True,
        }
        service.server_health_status[service_path] = HealthStatus.HEALTHY
        service.server_last_check_time[service_path] = datetime.now(timezone.utc)

        # This method should exist based on how it's called in broadcast_health_update
        assert hasattr(service, '_get_service_health_data_fast')


# =============================================================================
# TEST: MCP endpoint health checks
# =============================================================================


@pytest.mark.unit
class TestMcpEndpointHealthChecks:
    """Tests for MCP endpoint health check methods."""

    def test_is_mcp_endpoint_healthy_streamable_200(self):
        """Test streamable endpoint healthy with 200 status."""
        service = HealthMonitoringService()
        mock_response = MagicMock()
        mock_response.status_code = 200

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)
        assert result is True

    def test_is_mcp_endpoint_healthy_streamable_400_with_error(self):
        """Test streamable endpoint healthy with 400 and JSON-RPC error."""
        service = HealthMonitoringService()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": {"code": -32600, "message": "Invalid request"}}

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)
        assert result is True

    def test_is_mcp_endpoint_healthy_streamable_400_with_query_error(self):
        """Test streamable endpoint healthy with 400 and query parameter error."""
        service = HealthMonitoringService()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Missing required query parameter: strata_id or instance_id"}

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)
        assert result is True

    def test_is_mcp_endpoint_healthy_streamable_400_invalid_json(self):
        """Test streamable endpoint unhealthy with 400 and invalid JSON."""
        service = HealthMonitoringService()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.side_effect = ValueError("Invalid JSON")

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)
        assert result is False

    def test_is_mcp_endpoint_healthy_streamable_500(self):
        """Test streamable endpoint unhealthy with 500 status."""
        service = HealthMonitoringService()
        mock_response = MagicMock()
        mock_response.status_code = 500

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)
        assert result is False

    def test_is_mcp_endpoint_healthy_200(self):
        """Test MCP endpoint healthy with 200 status."""
        service = HealthMonitoringService()
        mock_response = MagicMock()
        mock_response.status_code = 200

        result = service._is_mcp_endpoint_healthy(mock_response)
        assert result is True

    def test_is_mcp_endpoint_healthy_400_session_id_error(self):
        """Test MCP endpoint healthy with 400 and missing session ID error."""
        service = HealthMonitoringService()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "server-error",
            "error": {"code": -32600, "message": "Missing session ID in request"}
        }

        result = service._is_mcp_endpoint_healthy(mock_response)
        assert result is True

    def test_is_mcp_endpoint_healthy_404(self):
        """Test MCP endpoint unhealthy with 404 status."""
        service = HealthMonitoringService()
        mock_response = MagicMock()
        mock_response.status_code = 404

        result = service._is_mcp_endpoint_healthy(mock_response)
        assert result is False
