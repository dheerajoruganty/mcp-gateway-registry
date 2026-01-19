"""
Unit tests for repository factory module.
"""

import logging
from unittest.mock import MagicMock

import pytest

import registry.repositories.factory as factory_module
from registry.repositories.factory import reset_repositories


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: reset_repositories
# =============================================================================


@pytest.mark.unit
class TestResetRepositories:
    """Tests for reset_repositories function."""

    def test_reset_clears_all_singletons(self):
        """Test that reset_repositories clears all cached instances."""
        # Set all singletons
        factory_module._server_repo = MagicMock()
        factory_module._agent_repo = MagicMock()
        factory_module._scope_repo = MagicMock()
        factory_module._security_scan_repo = MagicMock()
        factory_module._search_repo = MagicMock()
        factory_module._federation_config_repo = MagicMock()
        factory_module._peer_federation_repo = MagicMock()

        # Reset
        reset_repositories()

        # Verify all cleared
        assert factory_module._server_repo is None
        assert factory_module._agent_repo is None
        assert factory_module._scope_repo is None
        assert factory_module._security_scan_repo is None
        assert factory_module._search_repo is None
        assert factory_module._federation_config_repo is None
        assert factory_module._peer_federation_repo is None

    def test_reset_is_idempotent(self):
        """Test that reset_repositories can be called multiple times."""
        # Should not raise
        reset_repositories()
        reset_repositories()
        reset_repositories()
