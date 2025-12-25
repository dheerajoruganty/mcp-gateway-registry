#!/usr/bin/env python3
"""Re-index servers into embeddings index with tags included."""

import asyncio
import logging
import sys
from pathlib import Path

# Add registry module to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from opensearchpy import AsyncOpenSearch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def reindex_servers():
    """Re-index all servers from mcp-servers to mcp-embeddings with tags."""
    # Connect to OpenSearch
    client = AsyncOpenSearch(
        hosts=[{"host": "localhost", "port": 9200}],
        http_auth=("admin", "admin"),
        use_ssl=False,
        verify_certs=False
    )

    try:
        # Get all servers from mcp-servers index
        response = await client.search(
            index="mcp-servers-default",
            body={"query": {"match_all": {}}, "size": 100}
        )

        servers = response["hits"]["hits"]
        logger.info(f"Found {len(servers)} servers to re-index")

        # Import embeddings client
        from registry.embeddings import create_embeddings_client
        from registry.core.config import settings

        # Create embeddings model
        embedding_model = create_embeddings_client(
            provider=settings.embeddings_provider,
            model_name=settings.embeddings_model_name,
            model_dir=settings.embeddings_model_dir,
            api_key=settings.embeddings_api_key,
            api_base=settings.embeddings_api_base,
            aws_region=settings.embeddings_aws_region,
            embedding_dimension=settings.embeddings_model_dimensions,
        )

        # Re-index each server
        for hit in servers:
            server_info = hit["_source"]
            path = server_info["path"]
            doc_id = hit["_id"]

            # Build text for embedding with tags
            text_parts = [
                server_info.get("server_name", ""),
                server_info.get("description", ""),
            ]

            # Add tags
            tags = server_info.get("tags", [])
            if tags:
                text_parts.append("Tags: " + ", ".join(tags))
                logger.info(f"Adding tags to {path}: {tags}")

            # Add tool names and descriptions
            for tool in server_info.get("tool_list", []):
                text_parts.append(tool.get("name", ""))
                text_parts.append(tool.get("description", ""))

            text_for_embedding = " ".join(filter(None, text_parts))

            # Generate embedding
            embedding = embedding_model.encode([text_for_embedding])[0].tolist()

            # Prepare document for embeddings index
            doc = {
                "entity_type": "mcp_server",
                "path": path,
                "name": server_info.get("server_name", ""),
                "description": server_info.get("description", ""),
                "tags": server_info.get("tags", []),
                "is_enabled": server_info.get("is_enabled", False),
                "text_for_embedding": text_for_embedding,
                "embedding": embedding,
                "tools": [
                    {"name": t.get("name"), "description": t.get("description")}
                    for t in server_info.get("tool_list", [])
                ],
                "metadata": server_info,
                "indexed_at": server_info.get("updated_at", server_info.get("registered_at"))
            }

            # Index in embeddings
            await client.index(
                index="mcp-embeddings-default",
                id=doc_id,
                body=doc,
                refresh=True
            )
            logger.info(f"Re-indexed server '{server_info.get('server_name')}' with tags: {tags}")

        logger.info(f"Successfully re-indexed {len(servers)} servers")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(reindex_servers())
