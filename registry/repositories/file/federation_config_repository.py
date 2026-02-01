"""File-based repository for federation configuration storage."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...schemas.federation_schema import FederationConfig
from ..interfaces import FederationConfigRepositoryBase

logger = logging.getLogger(__name__)


class FileFederationConfigRepository(FederationConfigRepositoryBase):
    """File-based implementation of federation configuration repository."""

    def __init__(self, config_dir: Path | None = None):
        """
        Initialize file-based federation config repository.

        Args:
            config_dir: Directory for config files (default: from settings)
        """
        if config_dir is None:
            config_dir = Path("/app/config/federation")

        self._config_dir = config_dir
        self._config_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Initialized File FederationConfigRepository with directory: {self._config_dir}"
        )

    def _get_config_path(self, config_id: str) -> Path:
        """Get file path for a config ID."""
        return self._config_dir / f"{config_id}.json"

    async def get_config(self, config_id: str = "default") -> FederationConfig | None:
        """
        Get federation configuration by ID.

        Args:
            config_id: Configuration ID

        Returns:
            FederationConfig if found, None otherwise
        """
        try:
            config_path = self._get_config_path(config_id)

            if not config_path.exists():
                logger.info(f"Federation config file not found: {config_path}")
                return None

            with open(config_path) as f:
                data = json.load(f)

            # Remove internal fields before creating Pydantic model
            data.pop("config_id", None)
            data.pop("created_at", None)
            data.pop("updated_at", None)

            config = FederationConfig(**data)
            logger.info(f"Retrieved federation config from file: {config_id}")
            return config

        except Exception as e:
            logger.error(f"Failed to read federation config {config_id}: {e}", exc_info=True)
            return None

    async def save_config(
        self, config: FederationConfig, config_id: str = "default"
    ) -> FederationConfig:
        """
        Save or update federation configuration.

        Args:
            config: Federation configuration to save
            config_id: Configuration ID

        Returns:
            Saved configuration
        """
        try:
            config_path = self._get_config_path(config_id)

            # Check if config exists
            existing = None
            if config_path.exists():
                with open(config_path) as f:
                    existing = json.load(f)

            # Prepare document
            doc = config.model_dump()
            doc["config_id"] = config_id

            now = datetime.now(UTC).isoformat()
            if existing:
                # Preserve created_at for updates
                doc["created_at"] = existing.get("created_at", now)
                doc["updated_at"] = now
            else:
                # New config
                doc["created_at"] = now
                doc["updated_at"] = now

            # Write to file
            with open(config_path, "w") as f:
                json.dump(doc, f, indent=2)

            logger.info(f"Saved federation config to file: {config_id} -> {config_path}")
            return config

        except Exception as e:
            logger.error(f"Failed to save federation config {config_id}: {e}", exc_info=True)
            raise

    async def delete_config(self, config_id: str = "default") -> bool:
        """
        Delete federation configuration.

        Args:
            config_id: Configuration ID

        Returns:
            True if deleted, False if not found
        """
        try:
            config_path = self._get_config_path(config_id)

            if not config_path.exists():
                logger.warning(f"Federation config file not found for deletion: {config_path}")
                return False

            config_path.unlink()
            logger.info(f"Deleted federation config file: {config_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete federation config {config_id}: {e}", exc_info=True)
            return False

    async def list_configs(self) -> list[dict[str, Any]]:
        """
        List all federation configurations.

        Returns:
            List of config summaries
        """
        try:
            if not self._config_dir.exists():
                return []

            configs = []
            for config_file in self._config_dir.glob("*.json"):
                try:
                    with open(config_file) as f:
                        data = json.load(f)

                    configs.append(
                        {
                            "id": data.get("config_id", config_file.stem),
                            "created_at": data.get("created_at"),
                            "updated_at": data.get("updated_at"),
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to read config file {config_file}: {e}")
                    continue

            logger.info(f"Listed {len(configs)} federation configs from files")
            return configs

        except Exception as e:
            logger.error(f"Failed to list federation configs: {e}", exc_info=True)
            return []
