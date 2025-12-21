"""OpenSearch client singleton."""

import logging
from typing import Optional
from opensearchpy import AsyncOpenSearch

from ...core.config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenSearch] = None


async def get_opensearch_client() -> AsyncOpenSearch:
    """Get OpenSearch client singleton."""
    global _client

    if _client is not None:
        return _client

    auth = None
    if settings.opensearch_user and settings.opensearch_password:
        auth = (settings.opensearch_user, settings.opensearch_password)

    _client = AsyncOpenSearch(
        hosts=[{
            "host": settings.opensearch_host,
            "port": settings.opensearch_port,
        }],
        http_auth=auth,
        use_ssl=settings.opensearch_use_ssl,
        verify_certs=settings.opensearch_verify_certs,
    )

    # Verify connection
    info = await _client.info()
    logger.info(f"Connected to OpenSearch {info['version']['number']}")

    return _client


async def close_opensearch_client() -> None:
    """Close OpenSearch client."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_index_name(base_name: str) -> str:
    """Get full index name with namespace."""
    return f"{base_name}-{settings.opensearch_namespace}"
