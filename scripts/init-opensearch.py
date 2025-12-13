#!/usr/bin/env python3
"""
Initialize OpenSearch indices and pipelines.

Usage:
    uv run python scripts/init-opensearch.py
    uv run python scripts/init-opensearch.py --namespace tenant-a
    uv run python scripts/init-opensearch.py --recreate

Requires OpenSearch running on localhost:9200.
"""

import argparse
import json
import logging
import os
from pathlib import Path
from opensearchpy import OpenSearch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCHEMAS_DIR = Path(__file__).parent / "opensearch-schemas"
INDEX_BASE_NAMES = ["mcp-servers", "mcp-agents", "mcp-scopes", "mcp-embeddings"]


def main():
    parser = argparse.ArgumentParser(description="Initialize OpenSearch indices")
    parser.add_argument(
        "--namespace",
        default=os.getenv("OPENSEARCH_NAMESPACE", "default"),
        help="Namespace for index names (default: 'default')",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("OPENSEARCH_HOST", "localhost"),
        help="OpenSearch host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("OPENSEARCH_PORT", "9200")),
        help="OpenSearch port",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate indices if they exist",
    )
    args = parser.parse_args()

    client = OpenSearch(
        hosts=[{"host": args.host, "port": args.port}],
        use_ssl=False,
    )

    # Verify connection
    info = client.info()
    logger.info(f"Connected to OpenSearch {info['version']['number']}")
    logger.info(f"Using namespace: {args.namespace}")

    # Create indices with namespace suffix
    for base_name in INDEX_BASE_NAMES:
        index_name = f"{base_name}-{args.namespace}"
        schema_file = SCHEMAS_DIR / f"{base_name}.json"

        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_file}")
            continue

        with open(schema_file) as f:
            schema = json.load(f)

        if client.indices.exists(index=index_name):
            if args.recreate:
                logger.info(f"Deleting existing index: {index_name}")
                client.indices.delete(index=index_name)
            else:
                logger.info(f"Index {index_name} already exists, skipping")
                continue

        client.indices.create(index=index_name, body=schema)
        logger.info(f"Created index: {index_name}")

    # Create search pipeline (shared across namespaces)
    pipeline_file = SCHEMAS_DIR / "hybrid-search-pipeline.json"
    if pipeline_file.exists():
        with open(pipeline_file) as f:
            pipeline = json.load(f)

        try:
            client.http.put(
                "/_search/pipeline/hybrid-search-pipeline",
                body=pipeline,
            )
            logger.info("Created hybrid search pipeline")
        except Exception as e:
            logger.warning(f"Pipeline creation failed (may already exist): {e}")

    logger.info(f"OpenSearch initialization complete for namespace '{args.namespace}'")


if __name__ == "__main__":
    main()
