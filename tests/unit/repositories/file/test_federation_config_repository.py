"""
Unit tests for file-based federation config repository.
"""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from registry.repositories.file.federation_config_repository import FileFederationConfigRepository
from registry.schemas.federation_schema import (
    FederationConfig,
    AnthropicFederationConfig,
    AsorFederationConfig,
)


logger = logging.getLogger(__name__)


@pytest.mark.unit
class TestFileFederationConfigRepository:
    """Tests for FileFederationConfigRepository."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        return FileFederationConfigRepository(config_dir=temp_dir)

    @pytest.fixture
    def sample_config(self):
        """Create a sample federation config."""
        return FederationConfig(
            anthropic=AnthropicFederationConfig(enabled=True),
            asor=AsorFederationConfig(enabled=False),
        )

    def test_init_creates_directory(self, temp_dir):
        """Test that init creates the config directory."""
        config_dir = temp_dir / "new_config_dir"
        repo = FileFederationConfigRepository(config_dir=config_dir)

        assert config_dir.exists()

    @pytest.mark.asyncio
    async def test_get_config_not_found(self, repo):
        """Test getting config that doesn't exist."""
        result = await repo.get_config("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_save_and_get_config(self, repo, sample_config):
        """Test saving and retrieving config."""
        await repo.save_config(sample_config, "test-config")

        result = await repo.get_config("test-config")

        assert result is not None
        assert result.anthropic.enabled is True
        assert result.asor.enabled is False

    @pytest.mark.asyncio
    async def test_save_config_default_id(self, repo, sample_config):
        """Test saving config with default ID."""
        result = await repo.save_config(sample_config)

        assert result is not None
        # Should be saved with default ID
        loaded = await repo.get_config("default")
        assert loaded is not None

    @pytest.mark.asyncio
    async def test_save_config_update_existing(self, repo, sample_config):
        """Test updating existing config preserves created_at."""
        # Save initial config
        await repo.save_config(sample_config, "test")

        # Read raw file to check created_at
        config_path = repo._get_config_path("test")
        with open(config_path) as f:
            initial_data = json.load(f)
        initial_created_at = initial_data["created_at"]

        # Update config
        updated_config = FederationConfig(
            anthropic=AnthropicFederationConfig(enabled=False),
        )
        await repo.save_config(updated_config, "test")

        # Verify created_at was preserved
        with open(config_path) as f:
            updated_data = json.load(f)
        assert updated_data["created_at"] == initial_created_at
        assert updated_data["updated_at"] != initial_created_at

    @pytest.mark.asyncio
    async def test_delete_config_success(self, repo, sample_config):
        """Test deleting existing config."""
        await repo.save_config(sample_config, "to-delete")

        result = await repo.delete_config("to-delete")

        assert result is True
        # Verify file is deleted
        loaded = await repo.get_config("to-delete")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_config_not_found(self, repo):
        """Test deleting non-existent config."""
        result = await repo.delete_config("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_configs_empty(self, repo):
        """Test listing configs when none exist."""
        result = await repo.list_configs()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_configs_multiple(self, repo, sample_config):
        """Test listing multiple configs."""
        await repo.save_config(sample_config, "config1")
        await repo.save_config(sample_config, "config2")
        await repo.save_config(sample_config, "config3")

        result = await repo.list_configs()

        assert len(result) == 3
        ids = [c["id"] for c in result]
        assert "config1" in ids
        assert "config2" in ids
        assert "config3" in ids

    @pytest.mark.asyncio
    async def test_get_config_path(self, repo):
        """Test the config path generation."""
        path = repo._get_config_path("my-config")

        assert path.name == "my-config.json"

    @pytest.mark.asyncio
    async def test_get_config_invalid_json(self, repo, temp_dir):
        """Test handling of invalid JSON file."""
        # Create an invalid JSON file
        config_path = temp_dir / "invalid.json"
        config_path.write_text("not valid json")

        result = await repo.get_config("invalid")

        assert result is None
