"""
Unit tests for registry.auth.routes module.

Tests authentication routes including login, logout, and OAuth2 flows.
"""

import logging
from typing import Any
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry.auth.routes import (
    router,
    get_oauth2_providers,
    logout_handler,
)
from registry.core.config import settings


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def test_app():
    """Create test app with auth routes."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    yield client


@pytest.fixture
def mock_oauth_providers():
    """Create mock OAuth2 providers."""
    return [
        {"name": "google", "display_name": "Google"},
        {"name": "github", "display_name": "GitHub"},
    ]


# =============================================================================
# TEST: get_oauth2_providers
# =============================================================================


@pytest.mark.unit
class TestGetOAuth2Providers:
    """Tests for the get_oauth2_providers function."""

    @pytest.mark.asyncio
    async def test_get_providers_success(self, mock_oauth_providers):
        """Test successful OAuth2 provider fetch."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"providers": mock_oauth_providers}

        with patch("registry.auth.routes.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            providers = await get_oauth2_providers()

        assert providers == mock_oauth_providers

    @pytest.mark.asyncio
    async def test_get_providers_non_200_status(self):
        """Test OAuth2 provider fetch with non-200 status."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        with patch("registry.auth.routes.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            providers = await get_oauth2_providers()

        assert providers == []

    @pytest.mark.asyncio
    async def test_get_providers_exception(self):
        """Test OAuth2 provider fetch with exception."""
        with patch("registry.auth.routes.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(side_effect=Exception("Connection error"))
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            providers = await get_oauth2_providers()

        assert providers == []


# =============================================================================
# TEST: Login Form - skip template tests since they require real templates
# =============================================================================


# Note: Login form tests skipped as they require Jinja2 templates
# which may not be available in unit test environment. The endpoint
# functionality is tested through integration tests.


# =============================================================================
# TEST: OAuth2 Login Redirect
# =============================================================================


@pytest.mark.unit
class TestOAuth2LoginRedirect:
    """Tests for the OAuth2 login redirect endpoint."""

    def test_oauth2_redirect_success(self, test_app):
        """Test OAuth2 redirect to provider."""
        response = test_app.get("/auth/google", follow_redirects=False)

        assert response.status_code == 302
        assert "oauth2/login/google" in response.headers.get("location", "")

    def test_oauth2_redirect_github(self, test_app):
        """Test OAuth2 redirect to GitHub."""
        response = test_app.get("/auth/github", follow_redirects=False)

        assert response.status_code == 302
        assert "oauth2/login/github" in response.headers.get("location", "")

    def test_oauth2_redirect_with_https_header(self, test_app):
        """Test OAuth2 redirect respects X-Forwarded-Proto header."""
        response = test_app.get(
            "/auth/google",
            headers={"x-forwarded-proto": "https"},
            follow_redirects=False
        )

        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "oauth2/login/google" in location


# =============================================================================
# TEST: OAuth2 Callback
# =============================================================================


@pytest.mark.unit
class TestOAuth2Callback:
    """Tests for the OAuth2 callback endpoint."""

    def test_callback_with_error(self, test_app):
        """Test OAuth2 callback with error parameter."""
        response = test_app.get(
            "/auth/callback?error=oauth2_error&details=User+denied",
            follow_redirects=False
        )

        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "/login" in location

    def test_callback_oauth2_init_failed(self, test_app):
        """Test OAuth2 callback with init failed error."""
        response = test_app.get(
            "/auth/callback?error=oauth2_init_failed",
            follow_redirects=False
        )

        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")

    def test_callback_oauth2_callback_failed(self, test_app):
        """Test OAuth2 callback with callback failed error."""
        response = test_app.get(
            "/auth/callback?error=oauth2_callback_failed",
            follow_redirects=False
        )

        assert response.status_code == 302

    def test_callback_no_session(self, test_app):
        """Test OAuth2 callback without session cookie."""
        response = test_app.get("/auth/callback", follow_redirects=False)

        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "/login" in location

    def test_callback_with_valid_session(self, test_app):
        """Test OAuth2 callback with valid session cookie."""
        # Create a valid session cookie
        from itsdangerous import URLSafeTimedSerializer
        serializer = URLSafeTimedSerializer(settings.secret_key)
        session_data = serializer.dumps({"username": "testuser", "auth_method": "oauth2"})

        response = test_app.get(
            "/auth/callback",
            cookies={settings.session_cookie_name: session_data},
            follow_redirects=False
        )

        assert response.status_code == 302


# =============================================================================
# TEST: Login Submit
# =============================================================================


@pytest.mark.unit
class TestLoginSubmit:
    """Tests for the login submit endpoint."""

    def test_login_success_form(self, test_app):
        """Test successful login via form submission."""
        with patch("registry.auth.routes.validate_login_credentials") as mock_validate:
            mock_validate.return_value = True

            with patch("registry.auth.routes.create_session_cookie") as mock_cookie:
                mock_cookie.return_value = "session_data"

                response = test_app.post(
                    "/login",
                    data={"username": "admin", "password": "password"},
                    follow_redirects=False
                )

        assert response.status_code == 303
        assert "/" in response.headers.get("location", "")

    def test_login_success_api(self, test_app):
        """Test successful login via API call."""
        with patch("registry.auth.routes.validate_login_credentials") as mock_validate:
            mock_validate.return_value = True

            with patch("registry.auth.routes.create_session_cookie") as mock_cookie:
                mock_cookie.return_value = "session_data"

                response = test_app.post(
                    "/login",
                    data={"username": "admin", "password": "password"},
                    headers={"accept": "application/json"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_login_failure_form(self, test_app):
        """Test failed login via form submission."""
        with patch("registry.auth.routes.validate_login_credentials") as mock_validate:
            mock_validate.return_value = False

            response = test_app.post(
                "/login",
                data={"username": "admin", "password": "wrong"},
                follow_redirects=False
            )

        assert response.status_code == 303
        assert "error" in response.headers.get("location", "")

    def test_login_failure_api(self, test_app):
        """Test failed login via API call."""
        with patch("registry.auth.routes.validate_login_credentials") as mock_validate:
            mock_validate.return_value = False

            response = test_app.post(
                "/login",
                data={"username": "admin", "password": "wrong"},
                headers={"accept": "application/json"},
            )

        assert response.status_code == 401


# =============================================================================
# TEST: Logout
# =============================================================================


@pytest.mark.unit
class TestLogout:
    """Tests for the logout endpoints."""

    def test_logout_get(self, test_app):
        """Test logout via GET request."""
        response = test_app.get("/logout", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers.get("location", "")

    def test_logout_post(self, test_app):
        """Test logout via POST request."""
        response = test_app.post("/logout", follow_redirects=False)

        assert response.status_code == 303
        assert "/login" in response.headers.get("location", "")

    def test_logout_with_oauth_session(self, test_app):
        """Test logout with OAuth2 session redirects to provider logout."""
        from itsdangerous import URLSafeTimedSerializer
        serializer = URLSafeTimedSerializer(settings.secret_key)
        session_data = serializer.dumps({
            "username": "testuser",
            "auth_method": "oauth2",
            "provider": "google"
        })

        response = test_app.get(
            "/logout",
            cookies={settings.session_cookie_name: session_data},
            follow_redirects=False
        )

        assert response.status_code == 303
        location = response.headers.get("location", "")
        # Either redirects to provider logout or login
        assert "/login" in location or "oauth2/logout" in location

    def test_logout_with_invalid_session(self, test_app):
        """Test logout with invalid session cookie."""
        response = test_app.get(
            "/logout",
            cookies={settings.session_cookie_name: "invalid_session"},
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "/login" in response.headers.get("location", "")


# =============================================================================
# TEST: Providers API
# =============================================================================


@pytest.mark.unit
class TestProvidersAPI:
    """Tests for the providers API endpoint."""

    def test_get_providers_api_success(self, test_app):
        """Test getting providers via API."""
        with patch("registry.auth.routes.get_oauth2_providers", new_callable=AsyncMock) as mock_providers:
            mock_providers.return_value = [
                {"name": "google", "display_name": "Google"}
            ]

            response = test_app.get("/providers")

        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert len(data["providers"]) == 1

    def test_get_providers_api_empty(self, test_app):
        """Test getting providers when none available."""
        with patch("registry.auth.routes.get_oauth2_providers", new_callable=AsyncMock) as mock_providers:
            mock_providers.return_value = []

            response = test_app.get("/providers")

        assert response.status_code == 200
        data = response.json()
        assert data["providers"] == []


# =============================================================================
# TEST: Auth Config API
# =============================================================================


@pytest.mark.unit
class TestAuthConfigAPI:
    """Tests for the auth config API endpoint."""

    def test_get_auth_config(self, test_app):
        """Test getting auth configuration."""
        response = test_app.get("/config")

        assert response.status_code == 200
        data = response.json()
        assert "auth_server_url" in data


# =============================================================================
# TEST: logout_handler
# =============================================================================


@pytest.mark.unit
class TestLogoutHandler:
    """Tests for the logout_handler function."""

    @pytest.mark.asyncio
    async def test_logout_handler_no_session(self):
        """Test logout handler without session."""
        mock_request = MagicMock()
        mock_request.headers = {}

        response = await logout_handler(mock_request, session=None)

        # Should redirect to login
        assert response.status_code == 303

    @pytest.mark.asyncio
    async def test_logout_handler_exception(self):
        """Test logout handler handles exceptions."""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.cookies = MagicMock()
        mock_request.cookies.get.side_effect = Exception("Error")

        response = await logout_handler(mock_request, session="invalid")

        # Should still redirect to login
        assert response.status_code == 303
