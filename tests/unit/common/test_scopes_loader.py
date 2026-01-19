"""
Unit tests for scopes loader module.
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import yaml

from registry.common.scopes_loader import (
    load_scopes_from_yaml,
    load_scopes_from_repository,
    reload_scopes_config,
)


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_scope_repo():
    """Create a mock scope repository."""
    repo = MagicMock()
    repo.load_all = AsyncMock()
    repo.list_groups = AsyncMock(return_value={
        "admin-group": {},
        "user-group": {},
    })
    repo.get_group = AsyncMock(side_effect=lambda name: {
        "admin-group": {
            "group_mappings": ["keycloak-admin"],
            "server_access": ["*"],
            "ui_permissions": {"admin": True}
        },
        "user-group": {
            "group_mappings": ["keycloak-users"],
            "server_access": ["server-a", "server-b"],
            "ui_permissions": {"read": True}
        }
    }.get(name))
    return repo


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.storage_backend = "file"
    return settings


# =============================================================================
# TEST: load_scopes_from_repository
# =============================================================================


@pytest.mark.unit
class TestLoadScopesFromRepository:
    """Tests for load_scopes_from_repository function."""

    @pytest.mark.asyncio
    async def test_load_success(self, mock_scope_repo, mock_settings):
        """Test successful loading from repository."""
        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", return_value=mock_scope_repo):
                config = await load_scopes_from_repository(max_retries=1)

        assert "group_mappings" in config
        assert "UI-Scopes" in config
        assert "admin-group" in config
        assert config["group_mappings"]["keycloak-admin"] == ["admin-group"]

    @pytest.mark.asyncio
    async def test_load_empty_groups(self, mock_settings):
        """Test loading with no groups."""
        mock_repo = MagicMock()
        mock_repo.load_all = AsyncMock()
        mock_repo.list_groups = AsyncMock(return_value={})

        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", return_value=mock_repo):
                config = await load_scopes_from_repository(max_retries=1)

        assert config == {"group_mappings": {}, "UI-Scopes": {}}

    @pytest.mark.asyncio
    async def test_load_group_without_data(self, mock_settings):
        """Test loading when group returns None."""
        mock_repo = MagicMock()
        mock_repo.load_all = AsyncMock()
        mock_repo.list_groups = AsyncMock(return_value={"empty-group": {}})
        mock_repo.get_group = AsyncMock(return_value=None)

        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", return_value=mock_repo):
                config = await load_scopes_from_repository(max_retries=1)

        assert config == {"group_mappings": {}, "UI-Scopes": {}}

    @pytest.mark.asyncio
    async def test_load_group_without_ui_permissions(self, mock_settings):
        """Test loading group without UI permissions."""
        mock_repo = MagicMock()
        mock_repo.load_all = AsyncMock()
        mock_repo.list_groups = AsyncMock(return_value={"simple-group": {}})
        mock_repo.get_group = AsyncMock(return_value={
            "group_mappings": ["keycloak-group"],
            "server_access": ["server-x"]
            # No ui_permissions
        })

        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", return_value=mock_repo):
                config = await load_scopes_from_repository(max_retries=1)

        assert "simple-group" in config
        assert config["group_mappings"]["keycloak-group"] == ["simple-group"]

    @pytest.mark.asyncio
    async def test_load_connection_refused_retry(self, mock_settings):
        """Test retry on ConnectionRefusedError."""
        mock_repo = MagicMock()
        mock_repo.load_all = AsyncMock()
        mock_repo.list_groups = AsyncMock(return_value={})

        call_count = 0

        def get_repo_with_error():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionRefusedError("Connection refused")
            return mock_repo

        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", side_effect=get_repo_with_error):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    config = await load_scopes_from_repository(max_retries=2, initial_delay=0.01)

        assert "group_mappings" in config

    @pytest.mark.asyncio
    async def test_load_all_retries_fail(self, mock_settings):
        """Test all retries failing returns empty config."""
        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", side_effect=ConnectionRefusedError("fail")):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    config = await load_scopes_from_repository(max_retries=2, initial_delay=0.01)

        assert config == {"group_mappings": {}}

    @pytest.mark.asyncio
    async def test_load_generic_exception_retry(self, mock_settings):
        """Test retry on generic exception."""
        mock_repo = MagicMock()
        mock_repo.load_all = AsyncMock()
        mock_repo.list_groups = AsyncMock(return_value={})

        call_count = 0

        def get_repo_with_error():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Database error")
            return mock_repo

        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", side_effect=get_repo_with_error):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    config = await load_scopes_from_repository(max_retries=2, initial_delay=0.01)

        assert "group_mappings" in config

    @pytest.mark.asyncio
    async def test_load_multiple_groups_same_keycloak_mapping(self, mock_settings):
        """Test multiple groups mapping to same Keycloak group."""
        mock_repo = MagicMock()
        mock_repo.load_all = AsyncMock()
        mock_repo.list_groups = AsyncMock(return_value={
            "group-a": {},
            "group-b": {}
        })
        mock_repo.get_group = AsyncMock(side_effect=lambda name: {
            "group-a": {"group_mappings": ["shared-keycloak"]},
            "group-b": {"group_mappings": ["shared-keycloak"]}
        }.get(name))

        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", return_value=mock_repo):
                config = await load_scopes_from_repository(max_retries=1)

        # Both groups should be in the mapping
        assert "group-a" in config["group_mappings"]["shared-keycloak"]
        assert "group-b" in config["group_mappings"]["shared-keycloak"]

    @pytest.mark.asyncio
    async def test_load_os_error_retry(self, mock_settings):
        """Test retry on OSError."""
        mock_repo = MagicMock()
        mock_repo.load_all = AsyncMock()
        mock_repo.list_groups = AsyncMock(return_value={})

        call_count = 0

        def get_repo_with_error():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("Network unreachable")
            return mock_repo

        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", side_effect=get_repo_with_error):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    config = await load_scopes_from_repository(max_retries=2, initial_delay=0.01)

        assert "group_mappings" in config


# =============================================================================
# TEST: reload_scopes_config
# =============================================================================


@pytest.mark.unit
class TestReloadScopesConfig:
    """Tests for reload_scopes_config function."""

    @pytest.mark.asyncio
    async def test_reload_documentdb_backend(self):
        """Test reload with documentdb backend."""
        with patch("registry.common.scopes_loader.load_scopes_from_repository", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {"group_mappings": {"admin": ["scope"]}}

            config = await reload_scopes_config(storage_backend="documentdb")

        mock_load.assert_called_once()
        assert "group_mappings" in config

    @pytest.mark.asyncio
    async def test_reload_mongodb_ce_backend(self):
        """Test reload with mongodb-ce backend."""
        with patch("registry.common.scopes_loader.load_scopes_from_repository", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {"group_mappings": {}}

            config = await reload_scopes_config(storage_backend="mongodb-ce")

        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_file_backend(self, mock_scope_repo):
        """Test reload with file backend."""
        with patch("registry.repositories.factory.get_scope_repository", return_value=mock_scope_repo):
            with patch("registry.common.scopes_loader.load_scopes_from_yaml") as mock_yaml:
                mock_yaml.return_value = {"group_mappings": {"file": ["scope"]}}
                with patch.dict("os.environ", {"SCOPES_CONFIG_PATH": "/path/to/scopes.yml"}):
                    config = await reload_scopes_config(storage_backend="file")

        mock_scope_repo.load_all.assert_called_once()
        mock_yaml.assert_called_once_with("/path/to/scopes.yml")

    @pytest.mark.asyncio
    async def test_reload_default_backend(self, mock_scope_repo, mock_settings):
        """Test reload uses settings.storage_backend by default."""
        mock_settings.storage_backend = "file"

        with patch("registry.core.config.settings", mock_settings):
            with patch("registry.repositories.factory.get_scope_repository", return_value=mock_scope_repo):
                with patch("registry.common.scopes_loader.load_scopes_from_yaml") as mock_yaml:
                    mock_yaml.return_value = {"group_mappings": {}}

                    config = await reload_scopes_config()  # No backend specified

        # Should use file backend from settings
        mock_scope_repo.load_all.assert_called_once()


# =============================================================================
# TEST: load_scopes_from_yaml
# =============================================================================


@pytest.mark.unit
class TestLoadScopesFromYaml:
    """Tests for load_scopes_from_yaml function."""

    def test_load_from_valid_file(self):
        """Test loading from a valid YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                "group_mappings": {
                    "admin": ["admin-scope"],
                    "user": ["user-scope"],
                },
                "admin-scope": [{"server": "/admin-server"}],
                "user-scope": [{"server": "/user-server"}],
            }, f)
            f.flush()

            config = load_scopes_from_yaml(f.name)

            assert "group_mappings" in config
            assert len(config["group_mappings"]) == 2
            assert "admin" in config["group_mappings"]

    def test_load_from_nonexistent_file(self):
        """Test loading from nonexistent file returns empty config."""
        config = load_scopes_from_yaml("/nonexistent/path/scopes.yml")
        assert config == {"group_mappings": {}}

    def test_load_from_invalid_yaml(self):
        """Test loading from invalid YAML returns empty config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()

            config = load_scopes_from_yaml(f.name)
            assert config == {"group_mappings": {}}

    def test_load_from_default_path(self):
        """Test loading from default path when file doesn't exist."""
        # Mock Path.exists to return False
        with patch.object(Path, 'exists', return_value=False):
            config = load_scopes_from_yaml(None)
            assert config == {"group_mappings": {}}

    def test_load_with_empty_file(self):
        """Test loading from empty YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("")
            f.flush()

            config = load_scopes_from_yaml(f.name)
            # Empty YAML should return None, which we handle
            assert config is None or config == {"group_mappings": {}}

    def test_load_with_valid_group_mappings_only(self):
        """Test loading YAML with only group_mappings."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump({
                "group_mappings": {
                    "admin": ["admin-scope"],
                },
            }, f)
            f.flush()

            config = load_scopes_from_yaml(f.name)

            assert "group_mappings" in config
            assert "admin" in config["group_mappings"]
