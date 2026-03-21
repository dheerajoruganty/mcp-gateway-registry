"""GitHub HTTP client utility for authenticated access to private repositories.

Supports two authentication methods:
1. GitHub App (preferred): JWT -> installation access token, cached with TTL
2. Personal Access Token (PAT): Simple token-based auth

Falls back to unauthenticated requests when no credentials are configured.
"""

import logging
import threading
import time
from datetime import datetime

import httpx
import jwt

from ..core.config import settings

logger = logging.getLogger(__name__)

# GitHub domains that should receive authentication headers
_GITHUB_DOMAINS = frozenset(
    {
        "github.com",
        "raw.githubusercontent.com",
        "api.github.com",
    }
)

# Cache for GitHub App installation token
_token_cache_lock = threading.Lock()
_cached_installation_token: str | None = None
_cached_token_expiry: float = 0.0

# Safety margin before token expiry (seconds)
_TOKEN_EXPIRY_MARGIN: int = 300  # 5 minutes

# JWT lifetime for GitHub App authentication (seconds)
_JWT_LIFETIME: int = 600  # 10 minutes (GitHub maximum)


def _is_github_url(url: str) -> bool:
    """Check if a URL belongs to a GitHub domain.

    Args:
        url: The URL to check.

    Returns:
        True if the URL is a GitHub domain.
    """
    try:
        parsed = httpx.URL(url)
        host = parsed.host or ""
        return host in _GITHUB_DOMAINS or host.endswith(".github.com")
    except Exception:
        return False


def _create_github_app_jwt() -> str:
    """Create a JWT for GitHub App authentication.

    The JWT is signed with RS256 using the app's private key and is used
    to request installation access tokens.

    Returns:
        Encoded JWT string.

    Raises:
        ValueError: If GitHub App credentials are incomplete.
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued at time (60s in the past for clock drift)
        "exp": now + _JWT_LIFETIME,
        "iss": settings.github_app_id,
    }
    encoded = jwt.encode(
        payload,
        settings.github_app_private_key,
        algorithm="RS256",
    )
    logger.debug("Created GitHub App JWT for app_id=%s", settings.github_app_id)
    return encoded


async def _fetch_installation_token() -> tuple[str, float]:
    """Exchange a GitHub App JWT for an installation access token.

    Returns:
        Tuple of (access_token, expiry_timestamp).

    Raises:
        httpx.HTTPStatusError: If the GitHub API request fails.
    """
    app_jwt = _create_github_app_jwt()
    url = (
        f"https://api.github.com/app/installations/"
        f"{settings.github_app_installation_id}/access_tokens"
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10.0,
        )
        response.raise_for_status()

    data = response.json()
    token = data["token"]
    expires_at = data["expires_at"]  # ISO 8601 format

    expiry_ts = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
    logger.info(
        "Obtained GitHub App installation token, expires_at=%s",
        expires_at,
    )
    return token, expiry_ts


def _has_github_app_credentials() -> bool:
    """Check if all GitHub App credentials are configured."""
    return bool(
        settings.github_app_id
        and settings.github_app_installation_id
        and settings.github_app_private_key
    )


def _has_pat_credentials() -> bool:
    """Check if a GitHub PAT is configured."""
    return bool(settings.github_pat)


async def _get_cached_installation_token() -> str:
    """Get a cached installation token, refreshing if expired.

    Returns:
        Valid installation access token.
    """
    global _cached_installation_token, _cached_token_expiry

    with _token_cache_lock:
        now = time.time()
        if _cached_installation_token and now < (_cached_token_expiry - _TOKEN_EXPIRY_MARGIN):
            logger.debug("Using cached GitHub App installation token")
            return _cached_installation_token

    # Token is missing or expired, fetch a new one outside the lock
    token, expiry = await _fetch_installation_token()

    with _token_cache_lock:
        _cached_installation_token = token
        _cached_token_expiry = expiry

    return token


async def get_github_auth_headers() -> dict[str, str]:
    """Get authentication headers for GitHub API requests.

    Authentication priority:
    1. GitHub App (if app_id, installation_id, and private_key are set)
    2. Personal Access Token (if github_pat is set)
    3. Empty dict (unauthenticated fallback)

    Returns:
        Dictionary of HTTP headers for authentication.
    """
    if _has_github_app_credentials():
        try:
            token = await _get_cached_installation_token()
            return {"Authorization": f"token {token}"}
        except Exception:
            logger.exception("Failed to obtain GitHub App installation token")
            # Fall through to PAT if available
            if _has_pat_credentials():
                logger.warning("Falling back to PAT authentication")
            else:
                logger.warning("No fallback credentials, proceeding unauthenticated")

    if _has_pat_credentials():
        logger.debug("Using GitHub PAT authentication")
        return {"Authorization": f"token {settings.github_pat}"}

    logger.debug("No GitHub credentials configured, using unauthenticated access")
    return {}


async def get_authenticated_client(url: str) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with GitHub auth headers if the URL is a GitHub domain.

    For non-GitHub URLs, returns a plain client with no extra headers.

    Args:
        url: The target URL to configure authentication for.

    Returns:
        Configured httpx.AsyncClient instance. Caller is responsible for closing it.
    """
    headers: dict[str, str] = {}

    if _is_github_url(url):
        headers = await get_github_auth_headers()
        if headers:
            logger.debug("Created authenticated GitHub client for %s", url)
        else:
            logger.debug("Created unauthenticated client for GitHub URL %s", url)
    else:
        logger.debug("Created plain client for non-GitHub URL %s", url)

    return httpx.AsyncClient(headers=headers)
