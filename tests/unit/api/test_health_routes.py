"""
Unit tests for registry.health.routes module.

Tests health monitoring WebSocket and HTTP endpoints.
"""

import logging
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

from registry.health.routes import router
from registry.core.config import settings


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def test_app():
    """Create test app with health routes."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    yield client


@pytest.fixture
def mock_health_status():
    """Create mock health status data."""
    return {
        "services": {
            "/test-server/": {
                "status": "healthy",
                "last_checked": "2024-01-01T00:00:00Z"
            }
        },
        "total": 1,
        "healthy": 1,
        "unhealthy": 0
    }


# =============================================================================
# TEST: HTTP Health Status Endpoint
# =============================================================================


@pytest.mark.unit
class TestHealthStatusHTTP:
    """Tests for the HTTP health status endpoint."""

    def test_health_status_http_success(self, test_app, mock_health_status):
        """Test HTTP health status endpoint returns data."""
        with patch("registry.health.routes.health_service") as mock_service:
            mock_service.get_all_health_status = AsyncMock(return_value=mock_health_status)

            response = test_app.get("/ws/health_status")

        assert response.status_code == 200
        data = response.json()
        assert "services" in data

    def test_health_status_http_empty(self, test_app):
        """Test HTTP health status with no services."""
        with patch("registry.health.routes.health_service") as mock_service:
            mock_service.get_all_health_status = AsyncMock(return_value={
                "services": {},
                "total": 0
            })

            response = test_app.get("/ws/health_status")

        assert response.status_code == 200
        data = response.json()
        assert data["services"] == {}


# =============================================================================
# TEST: WebSocket Stats Endpoint
# =============================================================================


@pytest.mark.unit
class TestWebSocketStats:
    """Tests for the WebSocket stats endpoint."""

    def test_websocket_stats_success(self, test_app):
        """Test WebSocket stats endpoint returns data."""
        mock_stats = {
            "active_connections": 5,
            "pending_updates": 0,
            "total_broadcasts": 100,
            "failed_sends": 2,
            "failed_connections": 0
        }

        with patch("registry.health.routes.health_service") as mock_service:
            mock_service.get_websocket_stats.return_value = mock_stats

            response = test_app.get("/ws/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["active_connections"] == 5
        assert data["total_broadcasts"] == 100

    def test_websocket_stats_empty(self, test_app):
        """Test WebSocket stats with no connections."""
        mock_stats = {
            "active_connections": 0,
            "pending_updates": 0,
            "total_broadcasts": 0,
            "failed_sends": 0,
            "failed_connections": 0
        }

        with patch("registry.health.routes.health_service") as mock_service:
            mock_service.get_websocket_stats.return_value = mock_stats

            response = test_app.get("/ws/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["active_connections"] == 0


# =============================================================================
# TEST: WebSocket Connection (without actual WebSocket)
# =============================================================================


@pytest.mark.unit
class TestWebSocketEndpointLogic:
    """Tests for WebSocket endpoint logic without actual WebSocket connection."""

    def test_signer_initialization(self):
        """Test that the signer is properly initialized."""
        from registry.health.routes import signer
        assert signer is not None

    @pytest.mark.asyncio
    async def test_websocket_auth_missing_cookie(self):
        """Test WebSocket rejects connection without session cookie."""
        from registry.health.routes import websocket_endpoint

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.client = MagicMock()
        mock_ws.cookies = {}
        mock_ws.headers = {}
        mock_ws.query_params = {}

        await websocket_endpoint(mock_ws)

        mock_ws.close.assert_called_once()
        args = mock_ws.close.call_args
        assert args[1]["code"] == 1008

    @pytest.mark.asyncio
    async def test_websocket_auth_invalid_cookie(self):
        """Test WebSocket rejects connection with invalid session cookie."""
        from registry.health.routes import websocket_endpoint

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.client = MagicMock()
        mock_ws.cookies = {settings.session_cookie_name: "invalid_session"}
        mock_ws.headers = {}
        mock_ws.query_params = {}

        await websocket_endpoint(mock_ws)

        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_auth_from_cookie_header(self):
        """Test WebSocket extracts cookie from header."""
        from registry.health.routes import websocket_endpoint
        from itsdangerous import URLSafeTimedSerializer

        serializer = URLSafeTimedSerializer(settings.secret_key)
        valid_session = serializer.dumps({"username": "testuser"})

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.client = MagicMock()
        mock_ws.cookies = {}
        mock_ws.headers = {
            "cookie": f"{settings.session_cookie_name}={valid_session}"
        }
        mock_ws.query_params = {}

        with patch("registry.health.routes.health_service") as mock_health:
            mock_health.add_websocket_connection = AsyncMock(return_value=True)
            mock_health.remove_websocket_connection = AsyncMock()

            # Make receive_text raise disconnect to exit loop
            from starlette.websockets import WebSocketDisconnect
            mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

            await websocket_endpoint(mock_ws)

        # Connection should have been added and removed
        mock_health.add_websocket_connection.assert_called_once()
        mock_health.remove_websocket_connection.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_auth_from_query_params(self):
        """Test WebSocket extracts session from query params as fallback."""
        from registry.health.routes import websocket_endpoint
        from itsdangerous import URLSafeTimedSerializer

        serializer = URLSafeTimedSerializer(settings.secret_key)
        valid_session = serializer.dumps({"username": "testuser"})

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.client = MagicMock()
        mock_ws.cookies = {}
        mock_ws.headers = {}
        mock_ws.query_params = {settings.session_cookie_name: valid_session}

        with patch("registry.health.routes.health_service") as mock_health:
            mock_health.add_websocket_connection = AsyncMock(return_value=True)
            mock_health.remove_websocket_connection = AsyncMock()

            from starlette.websockets import WebSocketDisconnect
            mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

            await websocket_endpoint(mock_ws)

        mock_health.add_websocket_connection.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_connection_rejected_at_capacity(self):
        """Test WebSocket connection rejected when at capacity."""
        from registry.health.routes import websocket_endpoint
        from itsdangerous import URLSafeTimedSerializer

        serializer = URLSafeTimedSerializer(settings.secret_key)
        valid_session = serializer.dumps({"username": "testuser"})

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.client = MagicMock()
        mock_ws.cookies = {settings.session_cookie_name: valid_session}
        mock_ws.headers = {}
        mock_ws.query_params = {}

        with patch("registry.health.routes.health_service") as mock_health:
            mock_health.add_websocket_connection = AsyncMock(return_value=False)

            await websocket_endpoint(mock_ws)

        # Should not attempt to remove connection since it wasn't added
        mock_health.remove_websocket_connection.assert_not_called()

    @pytest.mark.asyncio
    async def test_websocket_session_no_username(self):
        """Test WebSocket rejects session without username."""
        from registry.health.routes import websocket_endpoint
        from itsdangerous import URLSafeTimedSerializer

        serializer = URLSafeTimedSerializer(settings.secret_key)
        # Session without username
        invalid_session = serializer.dumps({"auth_method": "oauth2"})

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.client = MagicMock()
        mock_ws.cookies = {settings.session_cookie_name: invalid_session}
        mock_ws.headers = {}
        mock_ws.query_params = {}

        await websocket_endpoint(mock_ws)

        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_exception_during_connection(self):
        """Test WebSocket handles exception during connection."""
        from registry.health.routes import websocket_endpoint
        from itsdangerous import URLSafeTimedSerializer

        serializer = URLSafeTimedSerializer(settings.secret_key)
        valid_session = serializer.dumps({"username": "testuser"})

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.client = MagicMock()
        mock_ws.cookies = {settings.session_cookie_name: valid_session}
        mock_ws.headers = {}
        mock_ws.query_params = {}

        with patch("registry.health.routes.health_service") as mock_health:
            mock_health.add_websocket_connection = AsyncMock(return_value=True)
            mock_health.remove_websocket_connection = AsyncMock()

            # Raise generic exception
            mock_ws.receive_text = AsyncMock(side_effect=Exception("Network error"))

            await websocket_endpoint(mock_ws)

        # Should still remove connection in finally block
        mock_health.remove_websocket_connection.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_timeout_sends_ping(self):
        """Test WebSocket sends ping on timeout."""
        from registry.health.routes import websocket_endpoint
        from itsdangerous import URLSafeTimedSerializer
        import asyncio

        serializer = URLSafeTimedSerializer(settings.secret_key)
        valid_session = serializer.dumps({"username": "testuser"})

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.client = MagicMock()
        mock_ws.cookies = {settings.session_cookie_name: valid_session}
        mock_ws.headers = {}
        mock_ws.query_params = {}

        call_count = 0
        async def receive_with_timeout():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            else:
                from starlette.websockets import WebSocketDisconnect
                raise WebSocketDisconnect()

        mock_ws.receive_text = AsyncMock(side_effect=receive_with_timeout)
        mock_ws.ping = AsyncMock()

        with patch("registry.health.routes.health_service") as mock_health:
            mock_health.add_websocket_connection = AsyncMock(return_value=True)
            mock_health.remove_websocket_connection = AsyncMock()

            await websocket_endpoint(mock_ws)

        # Should have called ping after timeout
        mock_ws.ping.assert_called_once()
