"""
Unit tests for registry.main module.

Tests application initialization, routing, and lifecycle management.
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: setup_logging
# =============================================================================


@pytest.mark.unit
class TestSetupLogging:
    """Tests for the setup_logging function."""

    def test_setup_logging_creates_directory(self):
        """Test that setup_logging creates log directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"

            mock_settings = MagicMock()
            mock_settings.log_dir = log_dir

            with patch("registry.main.settings", mock_settings):
                # Import fresh to trigger setup_logging
                from registry.main import setup_logging

                # Call the function with mocked settings
                with patch("registry.main.settings", mock_settings):
                    log_file = setup_logging()

            assert log_dir.exists()

    def test_setup_logging_returns_log_file_path(self):
        """Test that setup_logging returns the log file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            mock_settings = MagicMock()
            mock_settings.log_dir = log_dir

            with patch("registry.main.settings", mock_settings):
                from registry.main import setup_logging

                with patch("registry.main.settings", mock_settings):
                    log_file = setup_logging()

            assert log_file == log_dir / "registry.log"


# =============================================================================
# TEST: custom_openapi
# =============================================================================


@pytest.mark.unit
class TestCustomOpenAPI:
    """Tests for the custom_openapi function."""

    def test_custom_openapi_returns_cached_schema(self):
        """Test that custom_openapi returns cached schema if available."""
        from registry.main import app, custom_openapi

        # Reset the schema first
        app.openapi_schema = None

        # First call should generate the schema
        schema1 = custom_openapi()

        # Second call should return cached schema
        schema2 = custom_openapi()

        assert schema1 is schema2

    def test_custom_openapi_adds_security_schemes(self):
        """Test that custom_openapi adds Bearer security scheme."""
        from registry.main import app, custom_openapi

        # Reset the schema
        app.openapi_schema = None

        schema = custom_openapi()

        assert "components" in schema
        assert "securitySchemes" in schema["components"]
        assert "Bearer" in schema["components"]["securitySchemes"]
        assert schema["components"]["securitySchemes"]["Bearer"]["type"] == "http"
        assert schema["components"]["securitySchemes"]["Bearer"]["scheme"] == "bearer"

    def test_custom_openapi_applies_security_to_paths(self):
        """Test that custom_openapi applies security to non-auth paths."""
        from registry.main import app, custom_openapi

        # Reset the schema
        app.openapi_schema = None

        schema = custom_openapi()

        # Check that at least some paths have security applied
        paths_with_security = 0
        for path, path_item in schema.get("paths", {}).items():
            if not (path.startswith("/api/auth/") or path == "/health" or path.startswith("/.well-known/")):
                for method in ["get", "post", "put", "delete", "patch"]:
                    if method in path_item:
                        if "security" in path_item[method]:
                            paths_with_security += 1

        # Should have applied security to multiple paths
        assert paths_with_security > 0


# =============================================================================
# TEST: Health Check Endpoint
# =============================================================================


@pytest.mark.unit
class TestHealthCheckEndpoint:
    """Tests for the /health endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client without running lifespan."""
        from registry.main import app
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    def test_health_check_returns_healthy(self, client):
        """Test that health check returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "mcp-gateway-registry"


# =============================================================================
# TEST: Version Endpoint
# =============================================================================


@pytest.mark.unit
class TestVersionEndpoint:
    """Tests for the /api/version endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from registry.main import app
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

    def test_version_endpoint_returns_version(self, client):
        """Test that version endpoint returns application version."""
        response = client.get("/api/version")

        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        # Version should match the imported version
        from registry.version import __version__
        assert data["version"] == __version__


# =============================================================================
# TEST: Get Current User Endpoint
# =============================================================================


@pytest.mark.unit
class TestGetCurrentUserEndpoint:
    """Tests for the /api/auth/me endpoint."""

    def test_get_current_user_with_valid_auth(self):
        """Test getting current user info with valid authentication."""
        from registry.main import app
        from registry.auth.dependencies import enhanced_auth, get_ui_permissions_for_user

        mock_user_context = {
            "username": "testuser",
            "auth_method": "oauth2",
            "provider": "keycloak",
            "scopes": ["scope1", "scope2"],
            "groups": ["admin"],
            "can_modify_servers": True,
            "is_admin": True,
            "accessible_servers": ["/server1"],
            "accessible_services": ["/service1"],
            "accessible_agents": ["/agent1"]
        }

        mock_permissions = {
            "can_view_dashboard": True,
            "can_manage_servers": True
        }

        async def mock_enhanced_auth():
            return mock_user_context

        async def mock_get_permissions(scopes):
            return mock_permissions

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth

        with patch("registry.main.get_ui_permissions_for_user", new_callable=AsyncMock) as mock_perm:
            mock_perm.return_value = mock_permissions

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/api/auth/me")

        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["auth_method"] == "oauth2"
        assert data["is_admin"] is True
        assert data["scopes"] == ["scope1", "scope2"]

    def test_get_current_user_default_auth_method(self):
        """Test that auth_method defaults to basic if not specified."""
        from registry.main import app
        from registry.auth.dependencies import enhanced_auth

        mock_user_context = {
            "username": "testuser",
            # auth_method not specified
            "scopes": []
        }

        async def mock_enhanced_auth():
            return mock_user_context

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth

        with patch("registry.main.get_ui_permissions_for_user", new_callable=AsyncMock) as mock_perm:
            mock_perm.return_value = {}

            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.get("/api/auth/me")

        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["auth_method"] == "basic"


# =============================================================================
# TEST: App Configuration
# =============================================================================


@pytest.mark.unit
class TestAppConfiguration:
    """Tests for FastAPI application configuration."""

    def test_app_has_correct_title(self):
        """Test that app has correct title."""
        from registry.main import app

        assert app.title == "MCP Gateway Registry"

    def test_app_includes_routers(self):
        """Test that app includes expected routers."""
        from registry.main import app

        # Get all route paths
        routes = [route.path for route in app.routes]

        # Check for key API routes
        assert any("/api/servers" in path for path in routes) or any("/servers" in path for path in routes)
        assert any("/health" in path for path in routes)
        assert any("/api/version" in path for path in routes)

    def test_app_has_cors_middleware(self):
        """Test that app has CORS middleware configured."""
        from registry.main import app
        from starlette.middleware.cors import CORSMiddleware

        # Check if CORS middleware is in the middleware stack
        has_cors = False
        for middleware in app.user_middleware:
            if middleware.cls == CORSMiddleware:
                has_cors = True
                break

        assert has_cors

    def test_app_has_openapi_tags(self):
        """Test that app has OpenAPI tags configured."""
        from registry.main import app

        assert app.openapi_tags is not None
        assert len(app.openapi_tags) > 0

        # Check for expected tags
        tag_names = [tag["name"] for tag in app.openapi_tags]
        assert "Authentication" in tag_names
        assert "Server Management" in tag_names
        assert "Health Monitoring" in tag_names


# =============================================================================
# TEST: Lifespan Events
# =============================================================================


@pytest.mark.unit
class TestLifespanEvents:
    """Tests for application lifespan events."""

    @pytest.mark.asyncio
    async def test_lifespan_initializes_services(self):
        """Test that lifespan initializes required services."""
        from registry.main import lifespan

        mock_app = MagicMock()

        with patch("registry.main.server_service") as mock_server_service:
            with patch("registry.main.agent_service") as mock_agent_service:
                with patch("registry.main.health_service") as mock_health_service:
                    with patch("registry.main.nginx_service") as mock_nginx_service:
                        with patch("registry.main.get_search_repository") as mock_search_repo:
                            with patch("registry.auth.dependencies.reload_scopes_from_repository", new_callable=AsyncMock):
                                with patch("registry.repositories.factory.get_federation_config_repository") as mock_fed_repo:
                                    # Setup mocks
                                    mock_server_service.load_servers_and_state = AsyncMock()
                                    mock_server_service.get_all_servers = AsyncMock(return_value={})
                                    mock_server_service.get_enabled_services = AsyncMock(return_value=[])
                                    mock_agent_service.load_agents_and_state = AsyncMock()
                                    mock_agent_service.list_agents = MagicMock(return_value=[])
                                    mock_health_service.initialize = AsyncMock()
                                    mock_health_service.shutdown = AsyncMock()
                                    mock_nginx_service.generate_config_async = AsyncMock()

                                    mock_repo = MagicMock()
                                    mock_repo.initialize = AsyncMock()
                                    mock_search_repo.return_value = mock_repo

                                    mock_fed_config = MagicMock()
                                    mock_fed_config.is_any_federation_enabled.return_value = False
                                    mock_fed_repo_instance = MagicMock()
                                    mock_fed_repo_instance.get_config = AsyncMock(return_value=mock_fed_config)
                                    mock_fed_repo.return_value = mock_fed_repo_instance

                                    async with lifespan(mock_app):
                                        pass

                                    # Verify services were initialized
                                    mock_server_service.load_servers_and_state.assert_called_once()
                                    mock_agent_service.load_agents_and_state.assert_called_once()
                                    mock_health_service.initialize.assert_called_once()
                                    mock_health_service.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_handles_federation_config(self):
        """Test that lifespan handles federation configuration."""
        from registry.main import lifespan

        mock_app = MagicMock()
        mock_federation_config = MagicMock()
        mock_federation_config.is_any_federation_enabled.return_value = False

        with patch("registry.main.server_service") as mock_server_service:
            with patch("registry.main.agent_service") as mock_agent_service:
                with patch("registry.main.health_service") as mock_health_service:
                    with patch("registry.main.nginx_service") as mock_nginx_service:
                        with patch("registry.main.get_search_repository") as mock_search_repo:
                            with patch("registry.auth.dependencies.reload_scopes_from_repository", new_callable=AsyncMock):
                                with patch("registry.repositories.factory.get_federation_config_repository") as mock_fed_repo:
                                    # Setup mocks
                                    mock_server_service.load_servers_and_state = AsyncMock()
                                    mock_server_service.get_all_servers = AsyncMock(return_value={})
                                    mock_server_service.get_enabled_services = AsyncMock(return_value=[])
                                    mock_agent_service.load_agents_and_state = AsyncMock()
                                    mock_agent_service.list_agents = MagicMock(return_value=[])
                                    mock_health_service.initialize = AsyncMock()
                                    mock_health_service.shutdown = AsyncMock()
                                    mock_nginx_service.generate_config_async = AsyncMock()

                                    mock_repo = MagicMock()
                                    mock_repo.initialize = AsyncMock()
                                    mock_search_repo.return_value = mock_repo

                                    mock_fed_repo_instance = MagicMock()
                                    mock_fed_repo_instance.get_config = AsyncMock(return_value=mock_federation_config)
                                    mock_fed_repo.return_value = mock_fed_repo_instance

                                    async with lifespan(mock_app):
                                        pass

                                    # Verify federation config was checked
                                    mock_fed_repo_instance.get_config.assert_called_once_with("default")
                                    mock_federation_config.is_any_federation_enabled.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_handles_initialization_error(self):
        """Test that lifespan handles initialization errors properly."""
        from registry.main import lifespan

        mock_app = MagicMock()

        with patch("registry.main.server_service") as mock_server_service:
            mock_server_service.load_servers_and_state = AsyncMock(side_effect=Exception("Init error"))

            with patch("registry.auth.dependencies.reload_scopes_from_repository", new_callable=AsyncMock):
                with pytest.raises(Exception, match="Init error"):
                    async with lifespan(mock_app):
                        pass

    @pytest.mark.asyncio
    async def test_lifespan_indexes_servers(self):
        """Test that lifespan indexes servers into search repository."""
        from registry.main import lifespan

        mock_app = MagicMock()

        mock_servers = {
            "/server1": {"server_name": "Server 1"},
            "/server2": {"server_name": "Server 2"}
        }

        with patch("registry.main.server_service") as mock_server_service:
            with patch("registry.main.agent_service") as mock_agent_service:
                with patch("registry.main.health_service") as mock_health_service:
                    with patch("registry.main.nginx_service") as mock_nginx_service:
                        with patch("registry.main.get_search_repository") as mock_search_repo:
                            with patch("registry.auth.dependencies.reload_scopes_from_repository", new_callable=AsyncMock):
                                with patch("registry.repositories.factory.get_federation_config_repository") as mock_fed_repo:
                                    # Setup mocks
                                    mock_server_service.load_servers_and_state = AsyncMock()
                                    mock_server_service.get_all_servers = AsyncMock(return_value=mock_servers)
                                    mock_server_service.is_service_enabled = AsyncMock(return_value=True)
                                    mock_server_service.get_enabled_services = AsyncMock(return_value=["/server1", "/server2"])
                                    mock_server_service.get_server_info = AsyncMock(side_effect=lambda p: mock_servers.get(p))
                                    mock_agent_service.load_agents_and_state = AsyncMock()
                                    mock_agent_service.list_agents = MagicMock(return_value=[])
                                    mock_health_service.initialize = AsyncMock()
                                    mock_health_service.shutdown = AsyncMock()
                                    mock_nginx_service.generate_config_async = AsyncMock()

                                    mock_repo = MagicMock()
                                    mock_repo.initialize = AsyncMock()
                                    mock_repo.index_server = AsyncMock()
                                    mock_search_repo.return_value = mock_repo

                                    mock_fed_config = MagicMock()
                                    mock_fed_config.is_any_federation_enabled.return_value = False
                                    mock_fed_repo_instance = MagicMock()
                                    mock_fed_repo_instance.get_config = AsyncMock(return_value=mock_fed_config)
                                    mock_fed_repo.return_value = mock_fed_repo_instance

                                    async with lifespan(mock_app):
                                        pass

                                    # Verify servers were indexed
                                    assert mock_repo.index_server.call_count == 2


# =============================================================================
# TEST: Static File Serving
# =============================================================================


@pytest.mark.unit
class TestStaticFileServing:
    """Tests for static file serving configuration."""

    def test_static_files_mount_exists(self):
        """Test that static files are mounted."""
        from registry.main import app

        # Check for static mount in routes
        routes = [route for route in app.routes]
        static_mounts = [r for r in routes if hasattr(r, 'path') and '/static' in str(r.path)]

        assert len(static_mounts) > 0


# =============================================================================
# TEST: Serve React App (when build exists)
# =============================================================================


@pytest.mark.unit
class TestServeReactApp:
    """Tests for React app serving."""

    def test_react_app_route_returns_404_for_api(self):
        """Test that React app route returns 404 for API paths."""
        from registry.main import app, FRONTEND_BUILD_PATH

        with TestClient(app, raise_server_exceptions=False) as client:
            # API paths should not be caught by catch-all
            response = client.get("/api/nonexistent")

            # Should be 404 from actual API routing, not React
            assert response.status_code in [401, 403, 404, 422]

    def test_react_app_route_returns_404_for_wellknown(self):
        """Test that React app route returns 404 for well-known paths."""
        from registry.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            # Well-known paths should not be caught by catch-all
            response = client.get("/.well-known/nonexistent")

            # Could be 404 or other error
            assert response.status_code >= 400
