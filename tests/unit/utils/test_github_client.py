"""
Unit tests for registry.utils.github_client.

Tests GitHub URL detection, authentication header generation (PAT and GitHub App),
token caching, preference ordering, and integration with skill service/routes.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from registry.utils.github_client import (
    _has_github_app_credentials,
    _has_pat_credentials,
    _is_github_url,
    get_authenticated_client,
    get_github_auth_headers,
)


# ---------------------------------------------------------------------------
# _is_github_url tests
# ---------------------------------------------------------------------------


class TestIsGithubUrl:
    """Tests for _is_github_url function."""

    def test_github_com_https(self):
        """HTTPS github.com URL should be detected."""
        assert _is_github_url("https://github.com/org/repo") is True

    def test_github_com_http(self):
        """HTTP github.com URL should be detected."""
        assert _is_github_url("http://github.com/org/repo") is True

    def test_raw_githubusercontent(self):
        """raw.githubusercontent.com URL should be detected."""
        assert _is_github_url(
            "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        ) is True

    def test_api_github_com(self):
        """api.github.com URL should be detected."""
        assert _is_github_url("https://api.github.com/repos/org/repo") is True

    def test_subdomain_of_github_com(self):
        """Subdomains of github.com should be detected."""
        assert _is_github_url("https://gist.github.com/user/abc") is True

    def test_gitlab_url(self):
        """GitLab URL should not be detected."""
        assert _is_github_url("https://gitlab.com/org/repo") is False

    def test_bitbucket_url(self):
        """Bitbucket URL should not be detected."""
        assert _is_github_url("https://bitbucket.org/org/repo") is False

    def test_random_url(self):
        """Random URL should not be detected."""
        assert _is_github_url("https://example.com/something") is False

    def test_empty_string(self):
        """Empty string should return False."""
        assert _is_github_url("") is False

    def test_invalid_url(self):
        """Invalid URL should return False."""
        assert _is_github_url("not-a-url") is False


# ---------------------------------------------------------------------------
# Credential detection helpers
# ---------------------------------------------------------------------------


class TestHasCredentials:
    """Tests for _has_pat_credentials and _has_github_app_credentials."""

    @patch("registry.utils.github_client.settings")
    def test_has_pat_when_set(self, mock_settings):
        """Should return True when PAT is configured."""
        mock_settings.github_pat = "ghp_test123"
        assert _has_pat_credentials() is True

    @patch("registry.utils.github_client.settings")
    def test_has_pat_when_empty(self, mock_settings):
        """Should return False when PAT is empty."""
        mock_settings.github_pat = ""
        assert _has_pat_credentials() is False

    @patch("registry.utils.github_client.settings")
    def test_has_app_credentials_when_all_set(self, mock_settings):
        """Should return True when all GitHub App fields are set."""
        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        assert _has_github_app_credentials() is True

    @patch("registry.utils.github_client.settings")
    def test_has_app_credentials_missing_id(self, mock_settings):
        """Should return False when app_id is empty."""
        mock_settings.github_app_id = ""
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        assert _has_github_app_credentials() is False

    @patch("registry.utils.github_client.settings")
    def test_has_app_credentials_missing_installation_id(self, mock_settings):
        """Should return False when installation_id is empty."""
        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = ""
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        assert _has_github_app_credentials() is False

    @patch("registry.utils.github_client.settings")
    def test_has_app_credentials_missing_private_key(self, mock_settings):
        """Should return False when private_key is empty."""
        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = ""
        assert _has_github_app_credentials() is False


# ---------------------------------------------------------------------------
# get_github_auth_headers tests
# ---------------------------------------------------------------------------


class TestGetGithubAuthHeaders:
    """Tests for get_github_auth_headers function."""

    @pytest.mark.asyncio
    @patch("registry.utils.github_client.settings")
    async def test_pat_auth_returns_token_header(self, mock_settings):
        """Should return Authorization header with PAT token."""
        mock_settings.github_pat = "ghp_test123"
        mock_settings.github_app_id = ""
        mock_settings.github_app_installation_id = ""
        mock_settings.github_app_private_key = ""

        headers = await get_github_auth_headers()
        assert headers == {"Authorization": "token ghp_test123"}

    @pytest.mark.asyncio
    @patch("registry.utils.github_client.settings")
    async def test_no_credentials_returns_empty(self, mock_settings):
        """Should return empty dict when no credentials configured."""
        mock_settings.github_pat = ""
        mock_settings.github_app_id = ""
        mock_settings.github_app_installation_id = ""
        mock_settings.github_app_private_key = ""

        headers = await get_github_auth_headers()
        assert headers == {}

    @pytest.mark.asyncio
    @patch("registry.utils.github_client._get_cached_installation_token", new_callable=AsyncMock)
    @patch("registry.utils.github_client.settings")
    async def test_github_app_auth_returns_installation_token(
        self, mock_settings, mock_get_token
    ):
        """Should return Authorization header with installation token when App configured."""
        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        mock_settings.github_pat = ""

        mock_get_token.return_value = "ghs_installation_token_abc"

        headers = await get_github_auth_headers()
        assert headers == {"Authorization": "token ghs_installation_token_abc"}
        mock_get_token.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("registry.utils.github_client._get_cached_installation_token", new_callable=AsyncMock)
    @patch("registry.utils.github_client.settings")
    async def test_github_app_preferred_over_pat(self, mock_settings, mock_get_token):
        """When both App and PAT are configured, App should take precedence."""
        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        mock_settings.github_pat = "ghp_fallback"

        mock_get_token.return_value = "ghs_app_token"

        headers = await get_github_auth_headers()
        assert headers == {"Authorization": "token ghs_app_token"}

    @pytest.mark.asyncio
    @patch("registry.utils.github_client._get_cached_installation_token", new_callable=AsyncMock)
    @patch("registry.utils.github_client.settings")
    async def test_fallback_to_pat_when_app_fails(self, mock_settings, mock_get_token):
        """Should fall back to PAT when GitHub App token fetch fails."""
        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        mock_settings.github_pat = "ghp_fallback"

        mock_get_token.side_effect = Exception("API error")

        headers = await get_github_auth_headers()
        assert headers == {"Authorization": "token ghp_fallback"}

    @pytest.mark.asyncio
    @patch("registry.utils.github_client._get_cached_installation_token", new_callable=AsyncMock)
    @patch("registry.utils.github_client.settings")
    async def test_fallback_to_unauthenticated_when_all_fail(
        self, mock_settings, mock_get_token
    ):
        """Should return empty dict when App fails and no PAT configured."""
        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        mock_settings.github_pat = ""

        mock_get_token.side_effect = Exception("API error")

        headers = await get_github_auth_headers()
        assert headers == {}


# ---------------------------------------------------------------------------
# Token caching tests
# ---------------------------------------------------------------------------


class TestTokenCaching:
    """Tests for GitHub App installation token caching."""

    @pytest.mark.asyncio
    @patch("registry.utils.github_client._fetch_installation_token", new_callable=AsyncMock)
    @patch("registry.utils.github_client.settings")
    async def test_token_is_cached_on_second_call(self, mock_settings, mock_fetch):
        """Second call should use cached token and not re-fetch."""
        import registry.utils.github_client as ghc

        # Reset cache state
        ghc._cached_installation_token = None
        ghc._cached_token_expiry = 0.0

        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        mock_settings.github_pat = ""

        # Return a token that expires far in the future
        future_expiry = time.time() + 3600
        mock_fetch.return_value = ("ghs_cached_token", future_expiry)

        headers1 = await get_github_auth_headers()
        headers2 = await get_github_auth_headers()

        assert headers1 == {"Authorization": "token ghs_cached_token"}
        assert headers2 == {"Authorization": "token ghs_cached_token"}
        # Should only fetch once due to caching
        assert mock_fetch.await_count == 1

        # Clean up cache
        ghc._cached_installation_token = None
        ghc._cached_token_expiry = 0.0

    @pytest.mark.asyncio
    @patch("registry.utils.github_client._fetch_installation_token", new_callable=AsyncMock)
    @patch("registry.utils.github_client.settings")
    async def test_expired_token_triggers_refetch(self, mock_settings, mock_fetch):
        """Expired token should trigger a new fetch."""
        import registry.utils.github_client as ghc

        # Reset cache state
        ghc._cached_installation_token = None
        ghc._cached_token_expiry = 0.0

        mock_settings.github_app_id = "12345"
        mock_settings.github_app_installation_id = "67890"
        mock_settings.github_app_private_key = "-----BEGIN RSA PRIVATE KEY-----"
        mock_settings.github_pat = ""

        # First call: token that's already expired (past the margin)
        past_expiry = time.time() - 100
        mock_fetch.return_value = ("ghs_token_v1", past_expiry)

        await get_github_auth_headers()

        # Token is cached but expired. Next call should re-fetch.
        future_expiry = time.time() + 3600
        mock_fetch.return_value = ("ghs_token_v2", future_expiry)

        headers = await get_github_auth_headers()
        assert headers == {"Authorization": "token ghs_token_v2"}
        assert mock_fetch.await_count == 2

        # Clean up cache
        ghc._cached_installation_token = None
        ghc._cached_token_expiry = 0.0


# ---------------------------------------------------------------------------
# get_authenticated_client tests
# ---------------------------------------------------------------------------


class TestGetAuthenticatedClient:
    """Tests for get_authenticated_client function."""

    @pytest.mark.asyncio
    @patch("registry.utils.github_client.get_github_auth_headers", new_callable=AsyncMock)
    async def test_github_url_gets_auth_headers(self, mock_auth_headers):
        """GitHub URL should produce a client with auth headers."""
        mock_auth_headers.return_value = {"Authorization": "token ghp_test"}

        client = await get_authenticated_client(
            "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        )

        try:
            assert client.headers.get("authorization") == "token ghp_test"
        finally:
            await client.aclose()

        mock_auth_headers.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("registry.utils.github_client.get_github_auth_headers", new_callable=AsyncMock)
    async def test_non_github_url_gets_no_auth(self, mock_auth_headers):
        """Non-GitHub URL should produce a client without auth headers."""
        client = await get_authenticated_client("https://gitlab.com/org/repo/SKILL.md")

        try:
            assert "authorization" not in client.headers
        finally:
            await client.aclose()

        mock_auth_headers.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("registry.utils.github_client.get_github_auth_headers", new_callable=AsyncMock)
    async def test_github_url_no_credentials_empty_headers(self, mock_auth_headers):
        """GitHub URL with no credentials should produce a client without auth."""
        mock_auth_headers.return_value = {}

        client = await get_authenticated_client("https://github.com/org/repo")

        try:
            assert "authorization" not in client.headers
        finally:
            await client.aclose()


# ---------------------------------------------------------------------------
# Integration: skill_service uses get_authenticated_client
# ---------------------------------------------------------------------------


class TestSkillServiceGitHubIntegration:
    """Tests for skill_service.py using get_authenticated_client."""

    @pytest.mark.asyncio
    @patch("registry.services.skill_service._is_safe_url", return_value=True)
    @patch("registry.services.skill_service.get_authenticated_client", new_callable=AsyncMock)
    async def test_validate_skill_md_url_github_uses_auth(
        self, mock_get_client, mock_safe_url
    ):
        """_validate_skill_md_url should use get_authenticated_client for GitHub URLs."""
        from registry.services.skill_service import _validate_skill_md_url

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"# My Skill"
        mock_response.url = httpx.URL("https://raw.githubusercontent.com/org/repo/main/SKILL.md")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_get_client.return_value = mock_client

        url = "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        result = await _validate_skill_md_url(url)

        assert result["valid"] is True
        mock_get_client.assert_awaited_once_with(url)

    @pytest.mark.asyncio
    @patch("registry.services.skill_service._is_safe_url", return_value=True)
    @patch("registry.services.skill_service.get_authenticated_client", new_callable=AsyncMock)
    async def test_validate_skill_md_url_non_github_uses_client(
        self, mock_get_client, mock_safe_url
    ):
        """_validate_skill_md_url should also use get_authenticated_client for non-GitHub."""
        from registry.services.skill_service import _validate_skill_md_url

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"# My Skill"
        mock_response.url = httpx.URL("https://gitlab.com/org/repo/SKILL.md")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_get_client.return_value = mock_client

        url = "https://gitlab.com/org/repo/SKILL.md"
        result = await _validate_skill_md_url(url)

        assert result["valid"] is True
        mock_get_client.assert_awaited_once_with(url)

    @pytest.mark.asyncio
    @patch("registry.services.skill_service._is_safe_url", return_value=True)
    @patch("registry.services.skill_service.get_authenticated_client", new_callable=AsyncMock)
    async def test_check_skill_health_uses_auth_client(
        self, mock_get_client, mock_safe_url
    ):
        """_check_skill_health should use get_authenticated_client."""
        from registry.services.skill_service import _check_skill_health

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = httpx.URL(
            "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        )

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_get_client.return_value = mock_client

        url = "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        result = await _check_skill_health(url)

        assert result["healthy"] is True
        mock_get_client.assert_awaited_once_with(url)

    @pytest.mark.asyncio
    @patch("registry.services.skill_service._is_safe_url", return_value=True)
    @patch("registry.services.skill_service.translate_skill_url")
    @patch("registry.services.skill_service.get_authenticated_client", new_callable=AsyncMock)
    async def test_parse_skill_md_content_uses_auth_client(
        self, mock_get_client, mock_translate, mock_safe_url
    ):
        """_parse_skill_md_content should use get_authenticated_client."""
        from registry.services.skill_service import _parse_skill_md_content

        mock_translate.return_value = (
            "https://github.com/org/repo/blob/main/SKILL.md",
            "https://raw.githubusercontent.com/org/repo/main/SKILL.md",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"# Test Skill\nA test skill description."
        mock_response.text = "# Test Skill\nA test skill description."
        mock_response.url = httpx.URL(
            "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_get_client.return_value = mock_client

        result = await _parse_skill_md_content(
            "https://github.com/org/repo/blob/main/SKILL.md"
        )

        assert result["name"] == "Test Skill"
        mock_get_client.assert_awaited_once_with(
            "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        )


# ---------------------------------------------------------------------------
# Integration: skill_routes uses get_authenticated_client
# ---------------------------------------------------------------------------


class TestSkillRoutesGitHubIntegration:
    """Tests for skill_routes.py get_skill_content using get_authenticated_client."""

    @pytest.mark.asyncio
    @patch("registry.api.skill_routes._is_safe_url", return_value=True)
    @patch("registry.api.skill_routes._user_can_access_skill", return_value=True)
    @patch("registry.utils.github_client.get_authenticated_client", new_callable=AsyncMock)
    @patch("registry.api.skill_routes.get_skill_service")
    async def test_get_skill_content_uses_auth_for_github(
        self,
        mock_get_service,
        mock_get_client,
        mock_access,
        mock_safe_url,
    ):
        """get_skill_content should use get_authenticated_client for fetching."""
        from registry.api.skill_routes import get_skill_content

        # Mock skill
        mock_skill = MagicMock()
        mock_skill.skill_md_raw_url = "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        mock_skill.skill_md_url = "https://github.com/org/repo/blob/main/SKILL.md"
        mock_skill.visibility = "public"
        mock_skill.owner = "testuser"

        mock_service = AsyncMock()
        mock_service.get_skill = AsyncMock(return_value=mock_skill)
        mock_get_service.return_value = mock_service

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# My Skill Content"
        mock_response.url = httpx.URL(
            "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_get_client.return_value = mock_client

        user_context = {"username": "testuser", "is_admin": False}
        result = await get_skill_content(
            user_context=user_context,
            skill_path="my-skill",
        )

        assert result["content"] == "# My Skill Content"
        mock_get_client.assert_awaited_once_with(
            "https://raw.githubusercontent.com/org/repo/main/SKILL.md"
        )
