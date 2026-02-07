"""
URL utilities for GitHub URL translation and handling.

Provides functions to translate GitHub URLs to raw content URLs,
supporting both github.com and enterprise GitHub instances.
"""

import logging
import re
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


def _is_github_hostname(
    hostname: str,
) -> bool:
    """Check if hostname is a GitHub instance (public or enterprise).

    Args:
        hostname: The hostname to check

    Returns:
        True if the hostname appears to be a GitHub instance
    """
    hostname_lower = hostname.lower()

    # Public GitHub
    if hostname_lower in ("github.com", "raw.githubusercontent.com"):
        return True

    # Enterprise GitHub typically contains 'github' in the hostname
    # Examples: github.mycompany.com, mycompany-github.com
    if "github" in hostname_lower:
        return True

    return False


def _is_raw_github_url(
    hostname: str,
) -> bool:
    """Check if hostname is already a raw GitHub URL.

    Args:
        hostname: The hostname to check

    Returns:
        True if the hostname is a raw content URL
    """
    hostname_lower = hostname.lower()

    # Public GitHub raw URL
    if hostname_lower == "raw.githubusercontent.com":
        return True

    # Enterprise GitHub raw URLs typically have 'raw' subdomain
    # Examples: raw.github.mycompany.com
    if hostname_lower.startswith("raw.") and "github" in hostname_lower:
        return True

    return False


def _translate_github_url_to_raw(
    url: str,
) -> str:
    """Translate a GitHub blob URL to a raw content URL.

    Handles both public GitHub and enterprise GitHub instances.

    Examples:
        - github.com/owner/repo/blob/main/path/SKILL.md
          -> raw.githubusercontent.com/owner/repo/refs/heads/main/path/SKILL.md
        - github.mycompany.com/owner/repo/blob/main/path/SKILL.md
          -> raw.github.mycompany.com/owner/repo/refs/heads/main/path/SKILL.md

    Args:
        url: GitHub URL to translate

    Returns:
        Raw content URL
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    path = parsed.path

    # Pattern: /owner/repo/blob/branch/path/to/file
    blob_pattern = re.compile(r"^/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")
    match = blob_pattern.match(path)

    if not match:
        # If not a blob URL, return as-is
        logger.debug(f"URL path doesn't match blob pattern, returning as-is: {url}")
        return url

    owner, repo, branch, file_path = match.groups()

    # Construct raw URL based on hostname type
    hostname_lower = hostname.lower()

    if hostname_lower == "github.com":
        # Public GitHub: use raw.githubusercontent.com
        raw_url = (
            f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{branch}/{file_path}"
        )
    else:
        # Enterprise GitHub: prepend 'raw.' to hostname
        # If hostname already starts with something, replace it
        # e.g., github.mycompany.com -> raw.github.mycompany.com
        raw_hostname = f"raw.{hostname_lower}"
        raw_url = f"https://{raw_hostname}/{owner}/{repo}/refs/heads/{branch}/{file_path}"

    logger.debug(f"Translated GitHub URL: {url} -> {raw_url}")
    return raw_url


def translate_skill_url(
    url: str,
) -> tuple[str, str]:
    """Translate a skill URL to both user-provided and raw formats.

    This function handles:
    1. GitHub URLs (github.com/...) - translated to raw.githubusercontent.com
    2. Already raw GitHub URLs (raw.githubusercontent.com) - kept as-is
    3. Enterprise GitHub URLs (*.github.* domains) - translated to raw.*.github.*
    4. Non-GitHub URLs - used as-is for both fields

    Args:
        url: The URL provided by the user

    Returns:
        Tuple of (user_provided_url, raw_url)
        - user_provided_url: The original URL as provided
        - raw_url: The URL for fetching raw content
    """
    url = url.strip()
    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    if not hostname:
        logger.warning(f"URL has no hostname: {url}")
        return (url, url)

    # Check if it's a GitHub-related hostname
    if not _is_github_hostname(hostname):
        # Non-GitHub URL: use same URL for both
        logger.debug(f"Non-GitHub URL, using as-is: {url}")
        return (url, url)

    # Already a raw URL: keep as-is
    if _is_raw_github_url(hostname):
        logger.debug(f"Already a raw GitHub URL: {url}")
        return (url, url)

    # GitHub URL: translate to raw
    raw_url = _translate_github_url_to_raw(url)
    return (url, raw_url)
