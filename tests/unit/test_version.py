"""
Unit tests for version module.
"""

import logging
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from registry.version import (
    _get_git_version,
    get_version,
    DEFAULT_VERSION,
)


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: _get_git_version
# =============================================================================


@pytest.mark.unit
class TestGetGitVersion:
    """Tests for _get_git_version function."""

    def test_git_version_success(self):
        """Test successful git version retrieval."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "v1.0.7\n"

        with patch("registry.version.subprocess.run", return_value=mock_result):
            result = _get_git_version()
            assert result == "1.0.7"

    def test_git_version_success_no_prefix(self):
        """Test git version without v prefix."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "1.2.3\n"

        with patch("registry.version.subprocess.run", return_value=mock_result):
            result = _get_git_version()
            assert result == "1.2.3"

    def test_git_version_with_commits(self):
        """Test git version with commits after tag."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "v1.0.7-3-g1234abc\n"

        with patch("registry.version.subprocess.run", return_value=mock_result):
            result = _get_git_version()
            assert result == "1.0.7-3-g1234abc"

    def test_git_version_failure(self):
        """Test git version failure."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: not a git repository"

        with patch("registry.version.subprocess.run", return_value=mock_result):
            result = _get_git_version()
            assert result is None

    def test_git_command_not_found(self):
        """Test when git command is not found."""
        with patch("registry.version.subprocess.run", side_effect=FileNotFoundError()):
            result = _get_git_version()
            assert result is None

    def test_git_command_timeout(self):
        """Test git command timeout."""
        with patch("registry.version.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            result = _get_git_version()
            assert result is None

    def test_git_command_exception(self):
        """Test general exception handling."""
        with patch("registry.version.subprocess.run", side_effect=Exception("Unknown error")):
            result = _get_git_version()
            assert result is None


# =============================================================================
# TEST: get_version
# =============================================================================


@pytest.mark.unit
class TestGetVersion:
    """Tests for get_version function."""

    def test_get_version_from_env(self):
        """Test getting version from BUILD_VERSION env var."""
        with patch.dict("os.environ", {"BUILD_VERSION": "2.0.0"}):
            result = get_version()
            assert result == "2.0.0"

    def test_get_version_from_git(self):
        """Test getting version from git when env var not set."""
        with patch.dict("os.environ", {}, clear=False):
            # Remove BUILD_VERSION if it exists
            import os
            env_backup = os.environ.pop("BUILD_VERSION", None)
            try:
                with patch("registry.version._get_git_version", return_value="1.5.0"):
                    result = get_version()
                    assert result == "1.5.0"
            finally:
                if env_backup:
                    os.environ["BUILD_VERSION"] = env_backup

    def test_get_version_default_fallback(self):
        """Test fallback to default version."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            env_backup = os.environ.pop("BUILD_VERSION", None)
            try:
                with patch("registry.version._get_git_version", return_value=None):
                    result = get_version()
                    assert result == DEFAULT_VERSION
            finally:
                if env_backup:
                    os.environ["BUILD_VERSION"] = env_backup

    def test_get_version_env_priority_over_git(self):
        """Test that env var takes priority over git."""
        with patch.dict("os.environ", {"BUILD_VERSION": "env-version"}):
            with patch("registry.version._get_git_version", return_value="git-version") as mock_git:
                result = get_version()
                assert result == "env-version"
                # Git should not be called when env var is set
                mock_git.assert_not_called()

    def test_get_version_empty_env_uses_git(self):
        """Test that empty env var uses git."""
        with patch.dict("os.environ", {"BUILD_VERSION": ""}):
            with patch("registry.version._get_git_version", return_value="git-version"):
                result = get_version()
                # Empty string is falsy, so should fall through to git
                assert result == "git-version"


# =============================================================================
# TEST: DEFAULT_VERSION constant
# =============================================================================


@pytest.mark.unit
class TestDefaultVersion:
    """Tests for DEFAULT_VERSION constant."""

    def test_default_version_format(self):
        """Test default version format."""
        assert DEFAULT_VERSION == "1.0.0"

    def test_default_version_is_string(self):
        """Test default version is a string."""
        assert isinstance(DEFAULT_VERSION, str)
