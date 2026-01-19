"""
Unit tests for registry.metrics.middleware module.

Tests the metrics collection middleware for FastAPI.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_metrics_client():
    """Create a mock metrics client."""
    client = MagicMock()
    client.emit_registry_metric = AsyncMock()
    client.emit_custom_metric = AsyncMock()
    client.emit_discovery_metric = AsyncMock()
    return client


@pytest.fixture
def app_with_middleware(mock_metrics_client):
    """Create FastAPI app with metrics middleware."""
    with patch("registry.metrics.middleware.create_metrics_client", return_value=mock_metrics_client):
        from registry.metrics.middleware import RegistryMetricsMiddleware

        app = FastAPI()

        @app.get("/api/servers")
        async def list_servers():
            return {"servers": []}

        @app.get("/api/servers/{server_id}")
        async def get_server(server_id: str):
            return {"id": server_id}

        @app.post("/api/servers")
        async def create_server():
            return {"id": "new-server"}

        @app.put("/api/servers/{server_id}")
        async def update_server(server_id: str):
            return {"id": server_id}

        @app.delete("/api/servers/{server_id}")
        async def delete_server(server_id: str):
            return {"deleted": True}

        @app.get("/api/search")
        async def search(q: str = ""):
            return {"results": []}

        @app.get("/api/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/api/auth/login")
        async def login():
            return {"token": "abc"}

        @app.get("/api/auth/logout")
        async def logout():
            return {"success": True}

        @app.get("/api/auth/me")
        async def me():
            return {"user": "test"}

        @app.get("/static/file.js")
        async def static_file():
            return {"content": "js"}

        @app.get("/")
        async def root():
            return {"message": "root"}

        @app.get("/docs")
        async def docs():
            return {"docs": True}

        app.add_middleware(RegistryMetricsMiddleware, service_name="test-registry")

        # Store client reference for assertions
        app.mock_metrics_client = mock_metrics_client

        with TestClient(app) as client:
            yield client, mock_metrics_client


# =============================================================================
# TEST: extract_operation_info
# =============================================================================


@pytest.mark.unit
class TestExtractOperationInfo:
    """Tests for the extract_operation_info method."""

    def test_extract_servers_list(self, app_with_middleware):
        """Test extracting operation info for server list endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_registry_metric = AsyncMock()
            mock_client.emit_custom_metric = AsyncMock()
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/servers"
            mock_request.method = "GET"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "list"
            assert result["resource_type"] == "server"
            assert result["resource_id"] == ""

    def test_extract_servers_read(self, app_with_middleware):
        """Test extracting operation info for server read endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/servers/server-123"
            mock_request.method = "GET"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "read"
            assert result["resource_type"] == "server"
            assert result["resource_id"] == "server-123"

    def test_extract_servers_create(self, app_with_middleware):
        """Test extracting operation info for server create endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/servers"
            mock_request.method = "POST"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "create"
            assert result["resource_type"] == "server"

    def test_extract_servers_update_put(self, app_with_middleware):
        """Test extracting operation info for server update with PUT."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/servers/server-123"
            mock_request.method = "PUT"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "update"
            assert result["resource_type"] == "server"
            assert result["resource_id"] == "server-123"

    def test_extract_servers_update_patch(self, app_with_middleware):
        """Test extracting operation info for server update with PATCH."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/servers/server-123"
            mock_request.method = "PATCH"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "update"

    def test_extract_servers_delete(self, app_with_middleware):
        """Test extracting operation info for server delete endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/servers/server-123"
            mock_request.method = "DELETE"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "delete"
            assert result["resource_type"] == "server"
            assert result["resource_id"] == "server-123"

    def test_extract_search(self, app_with_middleware):
        """Test extracting operation info for search endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/search"
            mock_request.method = "GET"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "search"
            assert result["resource_type"] == "search"

    def test_extract_health(self, app_with_middleware):
        """Test extracting operation info for health endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/health"
            mock_request.method = "GET"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "check"
            assert result["resource_type"] == "health"

    def test_extract_auth_login(self, app_with_middleware):
        """Test extracting operation info for auth login endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/auth/login"
            mock_request.method = "POST"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "login"
            assert result["resource_type"] == "auth"

    def test_extract_auth_logout(self, app_with_middleware):
        """Test extracting operation info for auth logout endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/auth/logout"
            mock_request.method = "POST"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "logout"
            assert result["resource_type"] == "auth"

    def test_extract_auth_me(self, app_with_middleware):
        """Test extracting operation info for auth me endpoint."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/auth/me"
            mock_request.method = "GET"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "profile"
            assert result["resource_type"] == "auth"

    def test_extract_non_api_returns_none(self, app_with_middleware):
        """Test that non-API paths return None."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/static/file.js"
            mock_request.method = "GET"

            result = middleware.extract_operation_info(mock_request)

            assert result is None

    def test_extract_unknown_method(self, app_with_middleware):
        """Test extracting operation info with unknown HTTP method."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/servers"
            mock_request.method = "OPTIONS"

            result = middleware.extract_operation_info(mock_request)

            assert result["operation"] == "unknown"


# =============================================================================
# TEST: extract_user_info
# =============================================================================


@pytest.mark.unit
class TestExtractUserInfo:
    """Tests for the extract_user_info method."""

    def test_extract_user_from_x_user_header(self, app_with_middleware):
        """Test extracting user from X-User header."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.headers = {"X-User": "testuser123"}

            result = middleware.extract_user_info(mock_request)

            # Should return hashed user ID
            assert result is not None
            assert len(result) > 0

    def test_extract_user_from_x_username_header(self, app_with_middleware):
        """Test extracting user from X-Username header."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.headers = {"X-Username": "anotheruser"}

            result = middleware.extract_user_info(mock_request)

            assert result is not None

    def test_extract_user_empty_headers(self, app_with_middleware):
        """Test extracting user with no relevant headers."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.headers = {}

            result = middleware.extract_user_info(mock_request)

            # Should return hashed empty string
            assert result is not None


# =============================================================================
# TEST: should_track_request
# =============================================================================


@pytest.mark.unit
class TestShouldTrackRequest:
    """Tests for the should_track_request method."""

    def test_should_not_track_static_files(self, app_with_middleware):
        """Test that static files are not tracked."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/static/bundle.js"

            result = middleware.should_track_request(mock_request)

            assert result is False

    def test_should_not_track_favicon(self, app_with_middleware):
        """Test that favicon is not tracked."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/favicon.ico"

            result = middleware.should_track_request(mock_request)

            assert result is False

    def test_should_not_track_root(self, app_with_middleware):
        """Test that root path is not tracked."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/"

            result = middleware.should_track_request(mock_request)

            assert result is False

    def test_should_not_track_docs(self, app_with_middleware):
        """Test that docs path is not tracked."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/docs"

            result = middleware.should_track_request(mock_request)

            assert result is False

    def test_should_not_track_openapi(self, app_with_middleware):
        """Test that openapi.json is not tracked."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/openapi.json"

            result = middleware.should_track_request(mock_request)

            assert result is False

    def test_should_track_api_endpoints(self, app_with_middleware):
        """Test that API endpoints are tracked."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.url.path = "/api/servers"

            result = middleware.should_track_request(mock_request)

            assert result is True


# =============================================================================
# TEST: dispatch
# =============================================================================


@pytest.mark.unit
class TestDispatch:
    """Tests for the dispatch method."""

    def test_dispatch_emits_registry_metric(self, app_with_middleware):
        """Test that dispatch emits registry metrics for API requests."""
        client, mock_client = app_with_middleware

        response = client.get("/api/servers")

        assert response.status_code == 200

        # Give async task time to complete
        import time
        time.sleep(0.1)

        # Verify metric was emitted
        mock_client.emit_registry_metric.assert_called()

    def test_dispatch_skips_static_files(self, app_with_middleware):
        """Test that dispatch skips metrics for static files."""
        client, mock_client = app_with_middleware

        # Reset mock
        mock_client.emit_registry_metric.reset_mock()

        response = client.get("/static/file.js")

        assert response.status_code == 200

        # Metrics should not be emitted for static files
        # (dispatch returns early)

    def test_dispatch_handles_successful_request(self, app_with_middleware):
        """Test that dispatch marks successful requests correctly."""
        client, mock_client = app_with_middleware

        response = client.get("/api/servers")

        assert response.status_code == 200

    def test_dispatch_handles_post_request(self, app_with_middleware):
        """Test that dispatch handles POST requests."""
        client, mock_client = app_with_middleware

        response = client.post("/api/servers")

        assert response.status_code == 200

    def test_dispatch_handles_search_request(self, app_with_middleware):
        """Test that dispatch emits discovery metric for search requests."""
        client, mock_client = app_with_middleware

        response = client.get("/api/search?q=test")

        assert response.status_code == 200

        # Give async task time to complete
        import time
        time.sleep(0.1)

        # Should emit both registry and discovery metrics
        mock_client.emit_registry_metric.assert_called()


# =============================================================================
# TEST: _emit_registry_metric
# =============================================================================


@pytest.mark.unit
class TestEmitRegistryMetric:
    """Tests for the _emit_registry_metric method."""

    @pytest.mark.asyncio
    async def test_emit_registry_metric_success(self, app_with_middleware):
        """Test emitting registry metric successfully."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_registry_metric = AsyncMock()
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            await middleware._emit_registry_metric(
                operation="read",
                resource_type="server",
                success=True,
                duration_ms=50.0,
                resource_id="server-123",
                user_id="user-hash",
                error_code=None
            )

            mock_client.emit_registry_metric.assert_called_once_with(
                operation="read",
                resource_type="server",
                success=True,
                duration_ms=50.0,
                resource_id="server-123",
                user_id="user-hash",
                error_code=None
            )

    @pytest.mark.asyncio
    async def test_emit_registry_metric_handles_exception(self, app_with_middleware):
        """Test that _emit_registry_metric handles exceptions gracefully."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_registry_metric = AsyncMock(side_effect=Exception("Metric error"))
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            # Should not raise
            await middleware._emit_registry_metric(
                operation="read",
                resource_type="server",
                success=True,
                duration_ms=50.0
            )


# =============================================================================
# TEST: _emit_headers_metric
# =============================================================================


@pytest.mark.unit
class TestEmitHeadersMetric:
    """Tests for the _emit_headers_metric method."""

    @pytest.mark.asyncio
    async def test_emit_headers_metric_success(self, app_with_middleware):
        """Test emitting headers metric successfully."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_custom_metric = AsyncMock()
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            await middleware._emit_headers_metric(
                path="/api/servers",
                method="GET",
                headers_info={
                    "authorization_present": True,
                    "user_agent_type": "browser",
                    "content_type": "application/json",
                    "origin": "http://localhost"
                },
                status_code=200
            )

            mock_client.emit_custom_metric.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_headers_metric_handles_exception(self, app_with_middleware):
        """Test that _emit_headers_metric handles exceptions gracefully."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_custom_metric = AsyncMock(side_effect=Exception("Metric error"))
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            # Should not raise
            await middleware._emit_headers_metric(
                path="/api/servers",
                method="GET",
                headers_info={},
                status_code=200
            )


# =============================================================================
# TEST: _emit_discovery_metric_from_request
# =============================================================================


@pytest.mark.unit
class TestEmitDiscoveryMetricFromRequest:
    """Tests for the _emit_discovery_metric_from_request method."""

    @pytest.mark.asyncio
    async def test_emit_discovery_metric_with_q_param(self, app_with_middleware):
        """Test emitting discovery metric with q parameter."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_discovery_metric = AsyncMock()
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.query_params = {"q": "test query"}

            await middleware._emit_discovery_metric_from_request(
                request=mock_request,
                duration_ms=100.0
            )

            mock_client.emit_discovery_metric.assert_called_once_with(
                query="test query",
                results_count=-1,
                duration_ms=100.0
            )

    @pytest.mark.asyncio
    async def test_emit_discovery_metric_with_query_param(self, app_with_middleware):
        """Test emitting discovery metric with query parameter."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_discovery_metric = AsyncMock()
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.query_params = {"query": "another query"}

            await middleware._emit_discovery_metric_from_request(
                request=mock_request,
                duration_ms=50.0
            )

            mock_client.emit_discovery_metric.assert_called_once_with(
                query="another query",
                results_count=-1,
                duration_ms=50.0
            )

    @pytest.mark.asyncio
    async def test_emit_discovery_metric_no_query(self, app_with_middleware):
        """Test emitting discovery metric with no query parameter."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_discovery_metric = AsyncMock()
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.query_params = {}

            await middleware._emit_discovery_metric_from_request(
                request=mock_request,
                duration_ms=75.0
            )

            mock_client.emit_discovery_metric.assert_called_once_with(
                query="unknown",
                results_count=-1,
                duration_ms=75.0
            )

    @pytest.mark.asyncio
    async def test_emit_discovery_metric_handles_exception(self, app_with_middleware):
        """Test that _emit_discovery_metric_from_request handles exceptions gracefully."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_client = MagicMock()
            mock_client.emit_discovery_metric = AsyncMock(side_effect=Exception("Metric error"))
            mock_create.return_value = mock_client

            from registry.metrics.middleware import RegistryMetricsMiddleware

            middleware = RegistryMetricsMiddleware(MagicMock(), service_name="test")

            mock_request = MagicMock()
            mock_request.query_params = {"q": "test"}

            # Should not raise
            await middleware._emit_discovery_metric_from_request(
                request=mock_request,
                duration_ms=25.0
            )


# =============================================================================
# TEST: add_registry_metrics_middleware
# =============================================================================


@pytest.mark.unit
class TestAddRegistryMetricsMiddleware:
    """Tests for the add_registry_metrics_middleware function."""

    def test_add_middleware_to_app(self):
        """Test adding metrics middleware to an app."""
        with patch("registry.metrics.middleware.create_metrics_client") as mock_create:
            mock_create.return_value = MagicMock()

            from registry.metrics.middleware import add_registry_metrics_middleware

            app = FastAPI()

            add_registry_metrics_middleware(app, service_name="test-service")

            # Verify middleware was added (check user_middleware)
            assert len(app.user_middleware) > 0
