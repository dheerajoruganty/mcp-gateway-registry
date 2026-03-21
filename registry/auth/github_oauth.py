"""GitHub OAuth router for user-level GitHub SSO.

Allows logged-in users to connect their GitHub account via OAuth,
storing the access token in their session cookie for authenticated
access to private GitHub repositories when fetching SKILL.md files.
"""

import logging
import time

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature

from ..core.config import settings
from .dependencies import nginx_proxied_auth, signer

logger = logging.getLogger(__name__)

router = APIRouter()

# State token max age in seconds
_STATE_MAX_AGE: int = 300


@router.get("/connect", summary="Initiate GitHub OAuth connection")
async def connect(
    request: Request,
    user_context: dict = Depends(nginx_proxied_auth),
):
    """Redirect user to GitHub OAuth authorization page.

    User must already be logged in. Generates a signed state parameter
    to prevent CSRF attacks during the OAuth flow.
    """
    if not settings.github_oauth_client_id:
        return JSONResponse(
            status_code=503,
            content={"detail": "GitHub OAuth not configured"},
        )

    username = user_context.get("username", "")
    state_data = {"username": username, "timestamp": int(time.time())}
    state = signer.dumps(state_data)

    callback_url = str(request.base_url).rstrip("/") + "/api/github/callback"

    github_authorize_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_oauth_client_id}"
        f"&redirect_uri={callback_url}"
        f"&scope=repo"
        f"&state={state}"
    )

    response = RedirectResponse(url=github_authorize_url)
    response.set_cookie(
        key="github_oauth_state",
        value=state,
        httponly=True,
        max_age=_STATE_MAX_AGE,
        samesite="lax",
    )
    return response


@router.get("/callback", summary="GitHub OAuth callback")
async def callback(
    request: Request,
    code: str = "",
    state: str = "",
):
    """Handle GitHub OAuth callback after user authorization.

    Exchanges the authorization code for an access token and stores
    it in the user's session cookie.
    """
    if not code or not state:
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing code or state parameter"},
        )

    # Validate state matches cookie
    cookie_state = request.cookies.get("github_oauth_state")
    if not cookie_state or cookie_state != state:
        logger.warning("GitHub OAuth state mismatch")
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid state parameter"},
        )

    # Validate state is properly signed and not expired
    try:
        signer.loads(state, max_age=_STATE_MAX_AGE)
    except BadSignature:
        logger.warning("GitHub OAuth state has invalid signature")
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid or expired state parameter"},
        )

    # Exchange code for access token
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": settings.github_oauth_client_id,
                    "client_secret": settings.github_oauth_client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            token_response.raise_for_status()
            token_data = token_response.json()
    except Exception:
        logger.exception("Failed to exchange GitHub OAuth code for token")
        return JSONResponse(
            status_code=502,
            content={"detail": "Failed to exchange code with GitHub"},
        )

    access_token = token_data.get("access_token")
    if not access_token:
        error = token_data.get("error_description", token_data.get("error", "unknown"))
        logger.error("GitHub OAuth token exchange returned error: %s", error)
        return JSONResponse(
            status_code=400,
            content={"detail": f"GitHub token exchange failed: {error}"},
        )

    # Read existing session cookie and add github_token
    session_cookie = request.cookies.get(settings.session_cookie_name)
    if not session_cookie:
        return JSONResponse(
            status_code=401,
            content={"detail": "No active session. Please log in first."},
        )

    try:
        session_data = signer.loads(session_cookie, max_age=settings.session_max_age_seconds)
    except Exception:
        logger.warning("Failed to decode session cookie during GitHub OAuth callback")
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid session. Please log in again."},
        )

    # Add GitHub token to session
    session_data["github_token"] = access_token
    updated_cookie = signer.dumps(session_data)

    response = RedirectResponse(url="/?github_connected=true")
    response.set_cookie(
        key=settings.session_cookie_name,
        value=updated_cookie,
        httponly=True,
        max_age=settings.session_max_age_seconds,
        samesite="lax",
    )
    # Delete the temporary state cookie
    response.delete_cookie(key="github_oauth_state")

    logger.info(
        "GitHub account connected for user %s",
        session_data.get("username"),
    )
    return response


@router.get("/status", summary="Check GitHub connection status")
async def status_check(
    request: Request,
    user_context: dict = Depends(nginx_proxied_auth),
):
    """Check if the current user has a connected GitHub account.

    If connected, validates the token by calling the GitHub API
    and returns the GitHub username.
    """
    github_token = _get_github_token_from_session(request)
    if not github_token:
        return {"connected": False, "github_username": None}

    # Validate token by calling GitHub API
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {github_token}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                user_data = resp.json()
                return {
                    "connected": True,
                    "github_username": user_data.get("login"),
                }
    except Exception:
        logger.warning("Failed to validate GitHub token")

    return {"connected": False, "github_username": None}


@router.post("/disconnect", summary="Disconnect GitHub account")
async def disconnect(
    request: Request,
    user_context: dict = Depends(nginx_proxied_auth),
):
    """Remove GitHub token from user's session."""
    session_cookie = request.cookies.get(settings.session_cookie_name)
    if not session_cookie:
        return {"disconnected": True}

    try:
        session_data = signer.loads(session_cookie, max_age=settings.session_max_age_seconds)
    except Exception:
        return {"disconnected": True}

    session_data.pop("github_token", None)
    updated_cookie = signer.dumps(session_data)

    response = JSONResponse(content={"disconnected": True})
    response.set_cookie(
        key=settings.session_cookie_name,
        value=updated_cookie,
        httponly=True,
        max_age=settings.session_max_age_seconds,
        samesite="lax",
    )

    logger.info(
        "GitHub account disconnected for user %s",
        session_data.get("username"),
    )
    return response


def _get_github_token_from_session(request: Request) -> str | None:
    """Extract GitHub OAuth token from session cookie.

    Args:
        request: The incoming HTTP request.

    Returns:
        GitHub token string or None if not present.
    """
    cookie_value = request.cookies.get(settings.session_cookie_name)
    if not cookie_value:
        return None
    try:
        session_data = signer.loads(cookie_value, max_age=settings.session_max_age_seconds)
        return session_data.get("github_token")
    except Exception:
        return None
