"""OpenSearch repository for federation configuration storage."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from opensearchpy import AsyncOpenSearch, NotFoundError

from ...core.config import settings
from ...schemas.federation_schema import FederationConfig
from ..interfaces import FederationConfigRepositoryBase
from .opensearch_client import get_opensearch_client
from .utils import get_index_name


logger = logging.getLogger(__name__)


class OpenSearchFederationConfigRepository(FederationConfigRepositoryBase):
    """OpenSearch implementation of federation configuration repository."""

    def __init__(self):
        """Initialize OpenSearch federation config repository."""
        self._index_name = get_index_name(settings.opensearch_index_federation_config)
        logger.info(f"Initialized OpenSearch FederationConfigRepository with index: {self._index_name}")


    async def _get_client(self) -> AsyncOpenSearch:
        """Get OpenSearch client."""
        return await get_opensearch_client()


    async def _ensure_index(self) -> None:
        """Ensure the federation config index exists with proper mapping."""
        client = await self._get_client()

        index_exists = await client.indices.exists(index=self._index_name)
        if index_exists:
            return

        # Define index mapping for federation config
        mapping = {
            "mappings": {
                "properties": {
                    "config_id": {
                        "type": "keyword"
                    },
                    "anthropic": {
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "endpoint": {"type": "keyword"},
                            "sync_on_startup": {"type": "boolean"},
                            "servers": {
                                "type": "nested",
                                "properties": {
                                    "name": {"type": "keyword"}
                                }
                            }
                        }
                    },
                    "asor": {
                        "properties": {
                            "enabled": {"type": "boolean"},
                            "endpoint": {"type": "keyword"},
                            "auth_env_var": {"type": "keyword"},
                            "sync_on_startup": {"type": "boolean"},
                            "agents": {
                                "type": "nested",
                                "properties": {
                                    "id": {"type": "keyword"}
                                }
                            }
                        }
                    },
                    "created_at": {
                        "type": "date",
                        "format": "strict_date_optional_time||epoch_millis"
                    },
                    "updated_at": {
                        "type": "date",
                        "format": "strict_date_optional_time||epoch_millis"
                    }
                }
            }
        }

        await client.indices.create(index=self._index_name, body=mapping)
        logger.info(f"Created federation config index: {self._index_name}")


    async def get_config(
        self,
        config_id: str = "default"
    ) -> Optional[FederationConfig]:
        """
        Get federation configuration by ID.

        Args:
            config_id: Configuration ID

        Returns:
            FederationConfig if found, None otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(
                index=self._index_name,
                id=config_id
            )

            source = response["_source"]

            # Remove internal fields before creating Pydantic model
            source.pop("config_id", None)
            source.pop("created_at", None)
            source.pop("updated_at", None)

            config = FederationConfig(**source)
            logger.info(f"Retrieved federation config: {config_id}")
            return config

        except NotFoundError:
            logger.info(f"Federation config not found: {config_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to get federation config {config_id}: {e}", exc_info=True)
            return None


    async def save_config(
        self,
        config: FederationConfig,
        config_id: str = "default"
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
            await self._ensure_index()
            client = await self._get_client()

            # Check if config exists to determine if this is create or update
            existing = None
            try:
                existing_doc = await client.get(index=self._index_name, id=config_id)
                existing = existing_doc["_source"]
            except NotFoundError:
                pass

            # Prepare document
            doc = config.model_dump()
            doc["config_id"] = config_id

            now = datetime.now(timezone.utc).isoformat()
            if existing:
                # Preserve created_at for updates
                doc["created_at"] = existing.get("created_at", now)
                doc["updated_at"] = now
            else:
                # New config
                doc["created_at"] = now
                doc["updated_at"] = now

            # Index the document
            await client.index(
                index=self._index_name,
                id=config_id,
                body=doc,
                refresh=True
            )

            logger.info(f"Saved federation config: {config_id}")
            return config

        except Exception as e:
            logger.error(f"Failed to save federation config {config_id}: {e}", exc_info=True)
            raise


    async def delete_config(
        self,
        config_id: str = "default"
    ) -> bool:
        """
        Delete federation configuration.

        Args:
            config_id: Configuration ID

        Returns:
            True if deleted, False if not found
        """
        try:
            client = await self._get_client()
            await client.delete(
                index=self._index_name,
                id=config_id,
                refresh=True
            )
            logger.info(f"Deleted federation config: {config_id}")
            return True

        except NotFoundError:
            logger.warning(f"Federation config not found for deletion: {config_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to delete federation config {config_id}: {e}", exc_info=True)
            return False


    async def list_configs(self) -> List[Dict[str, Any]]:
        """
        List all federation configurations.

        Returns:
            List of config summaries
        """
        try:
            client = await self._get_client()

            # Check if index exists
            index_exists = await client.indices.exists(index=self._index_name)
            if not index_exists:
                logger.info("Federation config index does not exist yet")
                return []

            response = await client.search(
                index=self._index_name,
                body={
                    "query": {"match_all": {}},
                    "_source": ["config_id", "created_at", "updated_at"]
                }
            )

            configs = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                configs.append({
                    "id": source.get("config_id", hit["_id"]),
                    "created_at": source.get("created_at"),
                    "updated_at": source.get("updated_at")
                })

            logger.info(f"Listed {len(configs)} federation configs")
            return configs

        except Exception as e:
            logger.error(f"Failed to list federation configs: {e}", exc_info=True)
            return []
