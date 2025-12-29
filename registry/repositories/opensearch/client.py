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

    # Configure authentication based on auth_type
    auth = None
    connection_class = None

    if settings.opensearch_auth_type == "aws_iam":
        # AWS IAM authentication for OpenSearch Serverless
        if not settings.opensearch_region:
            raise ValueError("opensearch_region is required when using aws_iam auth")

        # Import AWS-specific modules only when needed
        from .aws_auth import get_aws_auth, get_aws_connection_class

        auth = get_aws_auth(settings.opensearch_region)
        connection_class = get_aws_connection_class()

        logger.info(
            f"Using AWS IAM authentication for OpenSearch "
            f"(region: {settings.opensearch_region})"
        )

    elif settings.opensearch_auth_type == "basic":
        # Basic authentication (username/password)
        if settings.opensearch_user and settings.opensearch_password:
            auth = (settings.opensearch_user, settings.opensearch_password)
            logger.info("Using basic authentication for OpenSearch")
        else:
            logger.info("Using no authentication for OpenSearch")

    else:
        raise ValueError(
            f"Unknown opensearch_auth_type: {settings.opensearch_auth_type}. "
            f"Must be 'basic' or 'aws_iam'"
        )

    # Build client parameters
    client_params = {
        "hosts": [{
            "host": settings.opensearch_host,
            "port": settings.opensearch_port,
        }],
        "http_auth": auth,
        "use_ssl": settings.opensearch_use_ssl,
        "verify_certs": settings.opensearch_verify_certs,
    }

    # Add connection_class if specified (for AWS)
    if connection_class:
        client_params["connection_class"] = connection_class

    _client = AsyncOpenSearch(**client_params)

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
