"""Tests for registry.auth.github_oauth - GitHub OAuth router endpoints."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry.auth.dependencies import signer
from registry.auth.github_oauth import router
from registry.core.config import settings


def _make_session_cookie(
    username: str = "testuser",
    auth_method: str = "oauth2",
    github_token: str | None = None,
) -> str:
    """Create a signed session cookie for testing."""
    data = {"username": username, "auth_method": auth_method, "provider": "keycloak"}
    if github_token:
        data["github_token"] = github_token
    return signer.dumps(data)


def _build_app() -> FastAPI:
    """Build a minimal FastAPI app with the GitHub OAuth router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/github")
    return app


# ---------------------------------------------------------------------------
# /api/github/connect tests
# ---------------------------------------------------------------------------


class TestConnect:
    """Tests for GET /api/github/connect endpoint."""

    @patch("registry.auth.github_oauth.settings")
    @patch("registry.auth.github_oauth.nginx_proxied_auth")
    def test_connect_redirects_to_github(self, mock_auth, mock_settings):
        """Should redirect to GitHub OAuth authorize URL when configured."""
        mock_settings.github_oauth_client_id = "test-client-id"
        mock_auth.return_value = {"username": "testuser"}
        app = _build_app()
        app.dependency_overrides[
            __import__("registry.auth.dependencies", fromlist=["nginx_proxied_auth"]).nginx_proxied_auth
        ] = lambda: {"username": "testuser"}

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/github/connect", follow_redirects=False)

        assert response.status_code == 307
        location = response.headers["location"]
        assert "github.com/login/oauth/authorize" in location
        assert "client_id=test-client-id" in location
        assert "scope=repo" in location

    @patch("registry.auth.github_oauth.settings")
    def test_connect_returns_503_when_not_configured(self, mock_settings):
        """Should return 503 when GitHub OAuth client ID is empty."""
        mock_settings.github_oauth_client_id = ""
        app = _build_app()

        from registry.auth.dependencies import nginx_proxied_auth

        app.dependency_overrides[nginx_proxied_auth] = lambda: {"username": "testuser"}

        with TestClient(app) as client:
            response = client.get("/api/github/connect")

        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]

    def test_connect_requires_auth(self):
        """Should return 401 when no session cookie is provided."""
        app = _build_app()
        # Do NOT override the auth dependency, so the real one runs
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/github/connect")

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# /api/github/callback tests
# ---------------------------------------------------------------------------


class TestCallback:
    """Tests for GET /api/github/callback endpoint."""

    @patch("registry.auth.github_oauth.httpx.AsyncClient")
    @patch("registry.auth.github_oauth.settings")
    def test_callback_exchanges_code_for_token(self, mock_settings, mock_client_cls):
        """Should exchange code for token and update session with github_token."""
        mock_settings.github_oauth_client_id = "test-client-id"
        mock_settings.github_oauth_client_secret = "test-secret"
        mock_settings.session_cookie_name = settings.session_cookie_name
        mock_settings.session_max_age_seconds = settings.session_max_age_seconds

        # Create signed state
        state_data = {"username": "testuser", "timestamp": int(time.time())}
        state = signer.dumps(state_data)

        # Mock GitHub token exchange response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "gho_user_token_123"}
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http_client

        session_cookie = _make_session_cookie()

        app = _build_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                f"/api/github/callback?code=test_code&state={state}",
                cookies={
                    "github_oauth_state": state,
                    settings.session_cookie_name: session_cookie,
                },
                follow_redirects=False,
            )

        # Should redirect after successful token exchange
        assert response.status_code == 307
        assert "github_connected=true" in response.headers.get("location", "")

        # Verify updated session cookie contains github_token
        updated_cookie = response.cookies.get(settings.session_cookie_name)
        if updated_cookie:
            session_data = signer.loads(updated_cookie)
            assert session_data.get("github_token") == "gho_user_token_123"

    def test_callback_rejects_invalid_state(self):
        """Should return 400 when state parameter doesn't match cookie."""
        state = signer.dumps({"username": "testuser", "timestamp": int(time.time())})
        wrong_state = signer.dumps({"username": "hacker", "timestamp": int(time.time())})

        app = _build_app()
        with TestClient(app) as client:
            response = client.get(
                f"/api/github/callback?code=test_code&state={state}",
                cookies={"github_oauth_state": wrong_state},
            )

        assert response.status_code == 400
        assert "state" in response.json()["detail"].lower()

    def test_callback_rejects_missing_code(self):
        """Should return 400 when code parameter is missing."""
        app = _build_app()
        with TestClient(app) as client:
            response = client.get("/api/github/callback?state=some_state")

        assert response.status_code == 400
        assert "Missing" in response.json()["detail"]

    def test_callback_rejects_missing_state(self):
        """Should return 400 when state parameter is missing."""
        app = _build_app()
        with TestClient(app) as client:
            response = client.get("/api/github/callback?code=some_code")

        assert response.status_code == 400


# ---------------------------------------------------------------------------
# /api/github/status tests
# ---------------------------------------------------------------------------


class TestStatus:
    """Tests for GET /api/github/status endpoint."""

    @patch("registry.auth.github_oauth.httpx.AsyncClient")
    @patch("registry.auth.github_oauth.settings")
    def test_status_connected(self, mock_settings, mock_client_cls):
        """Should return connected=True with username when token is valid."""
        mock_settings.session_cookie_name = settings.session_cookie_name
        mock_settings.session_max_age_seconds = settings.session_max_age_seconds
        mock_settings.github_oauth_client_id = "test-client-id"

        # Mock GitHub user API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"login": "octocat"}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http_client

        session_cookie = _make_session_cookie(github_token="gho_valid_token")

        app = _build_app()

        from registry.auth.dependencies import nginx_proxied_auth

        app.dependency_overrides[nginx_proxied_auth] = lambda: {"username": "testuser"}

        with TestClient(app) as client:
            response = client.get(
                "/api/github/status",
                cookies={settings.session_cookie_name: session_cookie},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["github_username"] == "octocat"

    @patch("registry.auth.github_oauth.settings")
    def test_status_disconnected(self, mock_settings):
        """Should return connected=False when no github_token in session."""
        mock_settings.session_cookie_name = settings.session_cookie_name
        mock_settings.session_max_age_seconds = settings.session_max_age_seconds

        session_cookie = _make_session_cookie()  # No github_token

        app = _build_app()

        from registry.auth.dependencies import nginx_proxied_auth

        app.dependency_overrides[nginx_proxied_auth] = lambda: {"username": "testuser"}

        with TestClient(app) as client:
            response = client.get(
                "/api/github/status",
                cookies={settings.session_cookie_name: session_cookie},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    @patch("registry.auth.github_oauth.settings")
    def test_status_no_session_returns_disconnected(self, mock_settings):
        """Should return connected=False when no session cookie."""
        mock_settings.session_cookie_name = settings.session_cookie_name
        mock_settings.session_max_age_seconds = settings.session_max_age_seconds

        app = _build_app()

        from registry.auth.dependencies import nginx_proxied_auth

        app.dependency_overrides[nginx_proxied_auth] = lambda: {"username": "testuser"}

        with TestClient(app) as client:
            response = client.get("/api/github/status")

        assert response.status_code == 200
        assert response.json()["connected"] is False


# ---------------------------------------------------------------------------
# /api/github/disconnect tests
# ---------------------------------------------------------------------------


class TestDisconnect:
    """Tests for POST /api/github/disconnect endpoint."""

    @patch("registry.auth.github_oauth.settings")
    def test_disconnect_removes_token(self, mock_settings):
        """Should remove github_token from session and return disconnected=True."""
        mock_settings.session_cookie_name = settings.session_cookie_name
        mock_settings.session_max_age_seconds = settings.session_max_age_seconds

        session_cookie = _make_session_cookie(github_token="gho_to_remove")

        app = _build_app()

        from registry.auth.dependencies import nginx_proxied_auth

        app.dependency_overrides[nginx_proxied_auth] = lambda: {"username": "testuser"}

        with TestClient(app) as client:
            response = client.post(
                "/api/github/disconnect",
                cookies={settings.session_cookie_name: session_cookie},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["disconnected"] is True

        # Verify github_token is removed from session cookie
        updated_cookie = response.cookies.get(settings.session_cookie_name)
        if updated_cookie:
            session_data = signer.loads(updated_cookie)
            assert "github_token" not in session_data

    @patch("registry.auth.github_oauth.settings")
    def test_disconnect_without_session(self, mock_settings):
        """Should return disconnected=True even without session."""
        mock_settings.session_cookie_name = settings.session_cookie_name
        mock_settings.session_max_age_seconds = settings.session_max_age_seconds

        app = _build_app()

        from registry.auth.dependencies import nginx_proxied_auth

        app.dependency_overrides[nginx_proxied_auth] = lambda: {"username": "testuser"}

        with TestClient(app) as client:
            response = client.post("/api/github/disconnect")

        assert response.status_code == 200
        assert response.json()["disconnected"] is True
