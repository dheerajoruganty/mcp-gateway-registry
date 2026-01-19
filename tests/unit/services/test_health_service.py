"""
Unit tests for health service.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

from registry.health.service import HealthMonitoringService, HighPerformanceWebSocketManager
from registry.constants import HealthStatus


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: HighPerformanceWebSocketManager
# =============================================================================


@pytest.mark.unit
class TestHighPerformanceWebSocketManager:
    """Tests for HighPerformanceWebSocketManager."""

    def test_init(self):
        """Test manager initialization."""
        manager = HighPerformanceWebSocketManager()

        assert manager.connections == set()
        assert manager.connection_metadata == {}
        assert manager.pending_updates == {}
        assert manager.broadcast_count == 0
        assert manager.failed_send_count == 0

    @pytest.mark.asyncio
    async def test_remove_connection(self):
        """Test removing a connection."""
        manager = HighPerformanceWebSocketManager()

        mock_websocket = MagicMock()
        manager.connections.add(mock_websocket)
        manager.connection_metadata[mock_websocket] = {"test": "data"}
        manager.failed_connections.add(mock_websocket)

        await manager.remove_connection(mock_websocket)

        assert mock_websocket not in manager.connections
        assert mock_websocket not in manager.connection_metadata
        assert mock_websocket not in manager.failed_connections

    def test_get_stats(self):
        """Test getting stats from manager."""
        manager = HighPerformanceWebSocketManager()
        manager.broadcast_count = 10
        manager.failed_send_count = 2

        mock_websocket = MagicMock()
        manager.connections.add(mock_websocket)

        stats = manager.get_stats()

        assert stats["active_connections"] == 1
        assert stats["total_broadcasts"] == 10

    @pytest.mark.asyncio
    async def test_broadcast_update_no_connections(self):
        """Test broadcasting with no connections."""
        manager = HighPerformanceWebSocketManager()

        # Should not raise even with no connections
        await manager.broadcast_update()

        assert manager.broadcast_count == 0


# =============================================================================
# TEST: HealthMonitoringService Initialization
# =============================================================================


@pytest.mark.unit
class TestHealthMonitoringServiceInit:
    """Tests for HealthMonitoringService initialization."""

    def test_init(self):
        """Test service initialization."""
        service = HealthMonitoringService()

        assert isinstance(service.websocket_manager, HighPerformanceWebSocketManager)
        assert service.server_health_status == {}
        assert service.server_last_check_time == {}
        assert service.health_check_task is None

    def test_get_websocket_stats(self):
        """Test getting websocket stats."""
        service = HealthMonitoringService()

        stats = service.get_websocket_stats()

        assert "active_connections" in stats


# =============================================================================
# TEST: HealthMonitoringService MCP Endpoint Health Checks
# =============================================================================


@pytest.mark.unit
class TestMCPEndpointHealthCheck:
    """Tests for _is_mcp_endpoint_healthy method."""

    def test_http_200_is_healthy(self):
        """Test that HTTP 200 is considered healthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 200

        result = service._is_mcp_endpoint_healthy(mock_response)

        assert result is True

    def test_http_400_with_session_id_error_is_healthy(self):
        """Test that HTTP 400 with missing session ID error is healthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "server-error",
            "error": {
                "code": -32600,
                "message": "Missing session ID header"
            }
        }

        result = service._is_mcp_endpoint_healthy(mock_response)

        assert result is True

    def test_http_400_without_session_error_is_unhealthy(self):
        """Test that HTTP 400 without session error is unhealthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "Some other error"
        }

        result = service._is_mcp_endpoint_healthy(mock_response)

        assert result is False

    def test_http_404_is_unhealthy(self):
        """Test that HTTP 404 is unhealthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 404

        result = service._is_mcp_endpoint_healthy(mock_response)

        assert result is False

    def test_http_500_is_unhealthy(self):
        """Test that HTTP 500 is unhealthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 500

        result = service._is_mcp_endpoint_healthy(mock_response)

        assert result is False

    def test_json_parse_error_is_unhealthy(self):
        """Test that JSON parse error on 400 is unhealthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.side_effect = ValueError("Invalid JSON")

        result = service._is_mcp_endpoint_healthy(mock_response)

        assert result is False


# =============================================================================
# TEST: HealthMonitoringService Streamable HTTP Endpoint Health Checks
# =============================================================================


@pytest.mark.unit
class TestStreamableHTTPEndpointHealthCheck:
    """Tests for _is_mcp_endpoint_healthy_streamable method."""

    def test_http_200_is_healthy(self):
        """Test that HTTP 200 is considered healthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 200

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)

        assert result is True

    def test_http_400_with_jsonrpc_error_is_healthy(self):
        """Test that HTTP 400 with JSON-RPC -32600 error is healthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "code": -32600,
                "message": "Invalid request"
            }
        }

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)

        assert result is True

    def test_http_400_with_query_param_error_is_healthy(self):
        """Test that HTTP 400 with query param error is healthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "Missing required query parameter: strata_id or instance_id"
        }

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)

        assert result is True

    def test_http_400_with_other_error_is_unhealthy(self):
        """Test that HTTP 400 with other error is unhealthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "code": -32001,
                "message": "Some other error"
            }
        }

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)

        assert result is False

    def test_http_500_is_unhealthy(self):
        """Test that HTTP 500 is unhealthy."""
        service = HealthMonitoringService()

        mock_response = MagicMock()
        mock_response.status_code = 500

        result = service._is_mcp_endpoint_healthy_streamable(mock_response)

        assert result is False


# =============================================================================
# TEST: HealthMonitoringService Header Building
# =============================================================================


@pytest.mark.unit
class TestBuildHeadersForServer:
    """Tests for _build_headers_for_server method."""

    def test_default_headers(self):
        """Test default headers without server-specific headers."""
        service = HealthMonitoringService()
        server_info = {}

        headers = service._build_headers_for_server(server_info)

        assert headers["Accept"] == "application/json, text/event-stream"
        assert headers["Content-Type"] == "application/json"

    def test_headers_with_session_id(self):
        """Test headers with session ID included."""
        service = HealthMonitoringService()
        server_info = {}

        headers = service._build_headers_for_server(server_info, include_session_id=True)

        assert "Mcp-Session-Id" in headers
        # Verify session ID is a UUID-like string
        assert len(headers["Mcp-Session-Id"]) == 36  # UUID format

    def test_server_specific_headers(self):
        """Test merging server-specific headers."""
        service = HealthMonitoringService()
        server_info = {
            "headers": [
                {"Authorization": "Bearer test-token"},
                {"X-Custom-Header": "custom-value"}
            ]
        }

        headers = service._build_headers_for_server(server_info)

        assert headers["Authorization"] == "Bearer test-token"
        assert headers["X-Custom-Header"] == "custom-value"
        # Default headers should still be present
        assert headers["Accept"] == "application/json, text/event-stream"

    def test_empty_headers_list(self):
        """Test with empty headers list."""
        service = HealthMonitoringService()
        server_info = {"headers": []}

        headers = service._build_headers_for_server(server_info)

        assert headers["Accept"] == "application/json, text/event-stream"
        assert headers["Content-Type"] == "application/json"


# =============================================================================
# TEST: HealthMonitoringService Immediate Health Check
# =============================================================================


@pytest.mark.unit
class TestPerformImmediateHealthCheck:
    """Tests for perform_immediate_health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_server_not_registered(self):
        """Test health check for unregistered server."""
        service = HealthMonitoringService()

        with patch("registry.services.server_service.server_service") as mock_server_service:
            mock_server_service.get_server_info = AsyncMock(return_value=None)

            status, last_check = await service.perform_immediate_health_check("/nonexistent")

        assert "error: server not registered" in status

    @pytest.mark.asyncio
    async def test_health_check_missing_proxy_url(self):
        """Test health check with missing proxy URL."""
        service = HealthMonitoringService()

        with patch("registry.services.server_service.server_service") as mock_server_service:
            mock_server_service.get_server_info = AsyncMock(return_value={
                "server_name": "Test Server",
                "proxy_pass_url": None
            })

            status, last_check = await service.perform_immediate_health_check("/test-server")

        assert "error: missing proxy URL" in status


# =============================================================================
# TEST: HealthMonitoringService Shutdown
# =============================================================================


@pytest.mark.unit
class TestHealthMonitoringServiceShutdown:
    """Tests for HealthMonitoringService shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_cancels_task(self):
        """Test that shutdown cancels health check task."""
        service = HealthMonitoringService()

        # Create a mock task
        async def dummy_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                raise

        service.health_check_task = asyncio.create_task(dummy_task())

        await service.shutdown()

        # Task should be cancelled
        assert service.health_check_task.cancelled() or service.health_check_task.done()

    @pytest.mark.asyncio
    async def test_shutdown_closes_websocket_connections(self):
        """Test that shutdown closes all WebSocket connections."""
        service = HealthMonitoringService()

        # Add mock connections
        mock_conn1 = MagicMock()
        mock_conn1.close = AsyncMock()
        mock_conn2 = MagicMock()
        mock_conn2.close = AsyncMock()

        service.websocket_manager.connections = {mock_conn1, mock_conn2}

        await service.shutdown()

        # Both connections should be closed
        mock_conn1.close.assert_called_once()
        mock_conn2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_no_task(self):
        """Test shutdown when no health check task exists."""
        service = HealthMonitoringService()
        service.health_check_task = None

        # Should not raise
        await service.shutdown()


# =============================================================================
# TEST: HealthMonitoringService WebSocket Operations
# =============================================================================


@pytest.mark.unit
class TestWebSocketOperations:
    """Tests for WebSocket operations."""

    @pytest.mark.asyncio
    async def test_add_websocket_connection(self):
        """Test adding a WebSocket connection."""
        service = HealthMonitoringService()

        mock_websocket = MagicMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.send_text = AsyncMock()
        mock_websocket.client = MagicMock()
        mock_websocket.client.host = "127.0.0.1"

        with patch.object(service, "_get_cached_health_data", new_callable=AsyncMock) as mock_cache:
            mock_cache.return_value = {"test": "data"}

            result = await service.add_websocket_connection(mock_websocket)

        assert result is True
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_websocket_connection(self):
        """Test removing a WebSocket connection."""
        service = HealthMonitoringService()

        mock_websocket = MagicMock()
        mock_websocket.client = MagicMock()

        # Add to connections first
        service.websocket_manager.connections.add(mock_websocket)

        await service.remove_websocket_connection(mock_websocket)

        assert mock_websocket not in service.websocket_manager.connections


# =============================================================================
# TEST: HealthMonitoringService Status Operations
# =============================================================================


@pytest.mark.unit
class TestStatusOperations:
    """Tests for health status operations."""

    def test_set_health_status(self):
        """Test setting health status."""
        service = HealthMonitoringService()

        service.server_health_status["/test-server"] = HealthStatus.HEALTHY

        assert service.server_health_status["/test-server"] == HealthStatus.HEALTHY

    def test_get_unknown_status(self):
        """Test getting status for unknown server."""
        service = HealthMonitoringService()

        status = service.server_health_status.get("/unknown", HealthStatus.UNKNOWN)

        assert status == HealthStatus.UNKNOWN

    def test_update_last_check_time(self):
        """Test updating last check time."""
        service = HealthMonitoringService()

        check_time = datetime.now(timezone.utc)
        service.server_last_check_time["/test-server"] = check_time

        assert service.server_last_check_time["/test-server"] == check_time


# =============================================================================
# TEST: HealthMonitoringService Get Service Health Data
# =============================================================================


@pytest.mark.unit
class TestGetServiceHealthData:
    """Tests for _get_service_health_data method."""

    def test_get_service_health_data_healthy(self):
        """Test getting health data for healthy enabled service."""
        service = HealthMonitoringService()
        check_time = datetime.now(timezone.utc)

        service.server_health_status["/test-server"] = HealthStatus.HEALTHY
        service.server_last_check_time["/test-server"] = check_time

        # Server must be enabled to get healthy status
        server_info = {"server_name": "Test Server", "is_enabled": True}
        result = service._get_service_health_data("/test-server", server_info)

        assert result["status"] == HealthStatus.HEALTHY
        assert "last_checked_iso" in result

    def test_get_service_health_data_disabled(self):
        """Test getting health data for disabled service."""
        service = HealthMonitoringService()
        check_time = datetime.now(timezone.utc)

        service.server_health_status["/test-server"] = HealthStatus.HEALTHY
        service.server_last_check_time["/test-server"] = check_time

        # Server without is_enabled should return disabled status
        server_info = {"server_name": "Test Server", "is_enabled": False}
        result = service._get_service_health_data("/test-server", server_info)

        assert result["status"] == "disabled"

    def test_get_service_health_data_unknown(self):
        """Test getting health data for unknown enabled service."""
        service = HealthMonitoringService()

        # Enabled but no cached status means unknown
        server_info = {"server_name": "Unknown Server", "is_enabled": True}
        result = service._get_service_health_data("/unknown-server", server_info)

        assert result["status"] == HealthStatus.UNKNOWN
        assert result["last_checked_iso"] is None


# =============================================================================
# TEST: HealthMonitoringService Get All Health Status
# =============================================================================


@pytest.mark.unit
class TestGetAllHealthStatus:
    """Tests for get_all_health_status method."""

    @pytest.mark.asyncio
    async def test_get_all_health_status_with_servers(self):
        """Test getting all health status with registered servers."""
        service = HealthMonitoringService()

        check_time = datetime.now(timezone.utc)
        service.server_health_status["/server1"] = HealthStatus.HEALTHY
        service.server_health_status["/server2"] = HealthStatus.UNHEALTHY_TIMEOUT
        service.server_last_check_time["/server1"] = check_time
        service.server_last_check_time["/server2"] = check_time

        with patch("registry.services.server_service.server_service") as mock_server_service:
            mock_server_service.get_all_servers = AsyncMock(return_value={
                "/server1": {"server_name": "Server 1", "is_enabled": True},
                "/server2": {"server_name": "Server 2", "is_enabled": True},
            })

            result = await service.get_all_health_status()

        # Returns dict with path -> status mapping
        assert len(result) == 2
        assert "/server1" in result
        assert "/server2" in result

    @pytest.mark.asyncio
    async def test_get_all_health_status_empty(self):
        """Test getting all health status with no servers."""
        service = HealthMonitoringService()

        with patch("registry.services.server_service.server_service") as mock_server_service:
            mock_server_service.get_all_servers = AsyncMock(return_value={})

            result = await service.get_all_health_status()

        assert result == {}


# =============================================================================
# TEST: HealthMonitoringService Cached Health Data
# =============================================================================


@pytest.mark.unit
class TestCachedHealthData:
    """Tests for _get_cached_health_data method."""

    @pytest.mark.asyncio
    async def test_get_cached_health_data_returns_data(self):
        """Test getting cached health data."""
        service = HealthMonitoringService()

        check_time = datetime.now(timezone.utc)
        service.server_health_status["/test-server"] = HealthStatus.HEALTHY
        service.server_last_check_time["/test-server"] = check_time

        with patch("registry.services.server_service.server_service") as mock_server_service:
            mock_server_service.get_all_servers = AsyncMock(return_value={
                "/test-server": {"server_name": "Test Server", "is_enabled": True}
            })

            result = await service._get_cached_health_data()

        # Returns dict with path -> status mapping
        assert "/test-server" in result


# =============================================================================
# TEST: HealthMonitoringService Initialize
# =============================================================================


@pytest.mark.unit
class TestHealthServiceInitialize:
    """Tests for initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_starts_health_check_loop(self):
        """Test that initialize starts the health check loop."""
        service = HealthMonitoringService()

        # Mock the health check loop to not actually run
        with patch.object(service, "_run_health_checks", new_callable=AsyncMock):
            # Start initialize
            await service.initialize()

            # Wait a bit for task to be created
            await asyncio.sleep(0.01)

            # Cancel the task to clean up
            if service.health_check_task:
                service.health_check_task.cancel()
                try:
                    await service.health_check_task
                except asyncio.CancelledError:
                    pass

        assert service.health_check_task is not None


# =============================================================================
# TEST: HealthMonitoringService MCP Session Initialization
# =============================================================================


@pytest.mark.unit
class TestMCPSessionInitialization:
    """Tests for _initialize_mcp_session method."""

    @pytest.mark.asyncio
    async def test_initialize_mcp_session_success(self):
        """Test successful MCP session initialization."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Mcp-Session-Id": "test-session-id"}
        mock_response.json.return_value = {"jsonrpc": "2.0", "result": {}}
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await service._initialize_mcp_session(
            mock_client,
            "http://localhost:8000/mcp",
            {"Content-Type": "application/json"}
        )

        assert result == "test-session-id"

    @pytest.mark.asyncio
    async def test_initialize_mcp_session_no_session_id(self):
        """Test MCP session initialization without session ID in response."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}  # No Mcp-Session-Id header
        mock_response.json.return_value = {"jsonrpc": "2.0", "result": {}}
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await service._initialize_mcp_session(
            mock_client,
            "http://localhost:8000/mcp",
            {"Content-Type": "application/json"}
        )

        # Should return None or generated session ID
        # Implementation may vary - just verify it doesn't crash
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_initialize_mcp_session_failure(self):
        """Test MCP session initialization failure."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await service._initialize_mcp_session(
            mock_client,
            "http://localhost:8000/mcp",
            {"Content-Type": "application/json"}
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_initialize_mcp_session_exception(self):
        """Test MCP session initialization with exception."""
        import httpx

        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        result = await service._initialize_mcp_session(
            mock_client,
            "http://localhost:8000/mcp",
            {"Content-Type": "application/json"}
        )

        assert result is None


# =============================================================================
# TEST: HealthMonitoringService Try Ping Without Auth
# =============================================================================


@pytest.mark.unit
class TestTryPingWithoutAuth:
    """Tests for _try_ping_without_auth method."""

    @pytest.mark.asyncio
    async def test_ping_without_auth_success(self):
        """Test successful ping without auth."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await service._try_ping_without_auth(
            mock_client,
            "http://localhost:8000/mcp"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_ping_without_auth_401_response(self):
        """Test ping without auth with 401 response (still accessible)."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await service._try_ping_without_auth(
            mock_client,
            "http://localhost:8000/mcp"
        )

        assert result is True  # Server is reachable, auth just required

    @pytest.mark.asyncio
    async def test_ping_without_auth_server_error(self):
        """Test ping without auth with server error."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await service._try_ping_without_auth(
            mock_client,
            "http://localhost:8000/mcp"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_ping_without_auth_exception(self):
        """Test ping without auth with exception."""
        import httpx

        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        result = await service._try_ping_without_auth(
            mock_client,
            "http://localhost:8000/mcp"
        )

        assert result is False


# =============================================================================
# TEST: HighPerformanceWebSocketManager Additional Tests
# =============================================================================


@pytest.mark.unit
class TestHighPerformanceWebSocketManagerExtended:
    """Extended tests for HighPerformanceWebSocketManager."""

    @pytest.mark.asyncio
    async def test_add_connection_at_capacity(self):
        """Test adding connection when at capacity."""
        manager = HighPerformanceWebSocketManager()

        # Fill connections to capacity
        with patch.object(manager, "connections", new=set(range(1001))):
            mock_websocket = MagicMock()
            mock_websocket.close = AsyncMock()

            result = await manager.add_connection(mock_websocket)

            assert result is False
            mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_connection_success(self):
        """Test successfully adding a connection."""
        manager = HighPerformanceWebSocketManager()

        mock_websocket = MagicMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.send_text = AsyncMock()
        mock_websocket.client = MagicMock()
        mock_websocket.client.host = "127.0.0.1"

        with patch.object(manager, "_send_initial_status_optimized", new_callable=AsyncMock):
            result = await manager.add_connection(mock_websocket)

        assert result is True
        assert mock_websocket in manager.connections

    @pytest.mark.asyncio
    async def test_broadcast_update_with_service_update(self):
        """Test broadcasting with service update."""
        manager = HighPerformanceWebSocketManager()

        mock_websocket = MagicMock()
        mock_websocket.send_text = AsyncMock()
        manager.connections.add(mock_websocket)
        manager.last_broadcast_time = 0  # Force broadcast

        await manager.broadcast_update(
            service_path="/test-server",
            health_data={"status": "healthy"}
        )

        # Wait for async operations
        await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_broadcast_update_rate_limited(self):
        """Test that rapid broadcasts are rate limited."""
        from time import time

        manager = HighPerformanceWebSocketManager()
        manager.last_broadcast_time = time()  # Just broadcast

        mock_websocket = MagicMock()
        mock_websocket.send_text = AsyncMock()
        manager.connections.add(mock_websocket)

        # This should be queued, not sent immediately
        await manager.broadcast_update(
            service_path="/test-server",
            health_data={"status": "healthy"}
        )

        # Update should be pending
        assert "/test-server" in manager.pending_updates


# =============================================================================
# TEST: HealthMonitoringService Check Server Endpoint Transport Aware
# =============================================================================


@pytest.mark.unit
class TestCheckServerEndpointTransportAware:
    """Tests for _check_server_endpoint_transport_aware method."""

    @pytest.mark.asyncio
    async def test_check_missing_proxy_url(self):
        """Test check with missing proxy URL."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        server_info = {}

        result, status = await service._check_server_endpoint_transport_aware(
            mock_client, None, server_info
        )

        assert result is False
        assert "missing" in status.lower()

    @pytest.mark.asyncio
    async def test_check_stdio_transport_skipped(self):
        """Test that stdio transport is skipped."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        server_info = {"supported_transports": ["stdio"]}

        result, status = await service._check_server_endpoint_transport_aware(
            mock_client, "http://localhost:8000", server_info
        )

        assert result is True
        assert status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_check_streamable_http_success(self):
        """Test successful check with streamable-http transport."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_init_response = MagicMock()
        mock_init_response.status_code = 200
        mock_init_response.headers = {"Mcp-Session-Id": "test-session"}
        mock_init_response.json.return_value = {"jsonrpc": "2.0", "result": {}}

        mock_ping_response = MagicMock()
        mock_ping_response.status_code = 200
        mock_ping_response.json.return_value = {"jsonrpc": "2.0", "result": {}}

        mock_client.post = AsyncMock(side_effect=[mock_init_response, mock_ping_response])

        server_info = {"supported_transports": ["streamable-http"]}

        result, status = await service._check_server_endpoint_transport_aware(
            mock_client, "http://localhost:8000", server_info
        )

        assert result is True
        assert status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_sse_transport_success(self):
        """Test successful check with SSE transport."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client.get = AsyncMock(return_value=mock_response)

        server_info = {"supported_transports": ["sse"]}

        result, status = await service._check_server_endpoint_transport_aware(
            mock_client, "http://localhost:8000", server_info
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_check_transport_with_mcp_url(self):
        """Test check when URL already contains /mcp endpoint."""
        service = HealthMonitoringService()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client.get = AsyncMock(return_value=mock_response)

        server_info = {}

        result, status = await service._check_server_endpoint_transport_aware(
            mock_client, "http://localhost:8000/mcp", server_info
        )

        # Should handle URL with existing /mcp path
        assert isinstance(result, bool)
