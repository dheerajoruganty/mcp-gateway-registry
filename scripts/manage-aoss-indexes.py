#!/usr/bin/env python3
"""
Manage AWS OpenSearch Serverless indexes.

This script is designed to run inside an ECS task with proper IAM permissions.

Usage:
    # List all indexes
    python manage-aoss-indexes.py list

    # Inspect specific index
    python manage-aoss-indexes.py inspect --index mcp-embeddings-default

    # Count documents in index
    python manage-aoss-indexes.py count --index mcp-servers-default

    # Search documents in index
    python manage-aoss-indexes.py search --index mcp-servers-default --size 5

    # Delete an index
    python manage-aoss-indexes.py delete --index mcp-embeddings-default --confirm
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

import boto3
from opensearchpy import AWSV4SignerAsyncAuth, AsyncOpenSearch
from opensearchpy.connection import AsyncHttpConnection


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


def _get_aws_auth(
    region: str
) -> AWSV4SignerAsyncAuth:
    """Get AWS SigV4 async auth for OpenSearch Serverless."""
    credentials = boto3.Session().get_credentials()

    if not credentials:
        raise ValueError("No AWS credentials found")

    return AWSV4SignerAsyncAuth(credentials, region, "aoss")


async def _get_client(
    host: str,
    region: str
) -> AsyncOpenSearch:
    """Create OpenSearch async client."""
    auth = _get_aws_auth(region)

    return AsyncOpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        connection_class=AsyncHttpConnection,
        use_ssl=True,
        verify_certs=True,
        timeout=30
    )


async def list_indexes(
    host: str,
    region: str
) -> int:
    """List all indexes in the OpenSearch Serverless collection."""
    try:
        client = await _get_client(host, region)

        # Get all indexes
        indices = await client.cat.indices(format="json")

        if not indices:
            logger.info("No indexes found")
            return 0

        # Sort by index name
        indices.sort(key=lambda x: x.get("index", ""))

        print("\n" + "=" * 100)
        print(f"Found {len(indices)} indexes in collection")
        print("=" * 100)

        for idx in indices:
            index_name = idx.get("index", "unknown")
            doc_count = idx.get("docs.count", "0")
            store_size = idx.get("store.size", "0b")
            health = idx.get("health", "unknown")
            status = idx.get("status", "unknown")

            print(f"\nIndex: {index_name}")
            print(f"  Health: {health}")
            print(f"  Status: {status}")
            print(f"  Documents: {doc_count}")
            print(f"  Size: {store_size}")

        print("\n" + "=" * 100)

        await client.close()
        return 0

    except Exception as e:
        logger.error(f"Failed to list indexes: {e}", exc_info=True)
        return 1


async def inspect_index(
    host: str,
    region: str,
    index_name: str
) -> int:
    """Inspect a specific index (mapping and settings)."""
    try:
        client = await _get_client(host, region)

        # Check if index exists
        exists = await client.indices.exists(index=index_name)
        if not exists:
            logger.error(f"Index '{index_name}' does not exist")
            return 1

        # Get index info
        index_info = await client.indices.get(index=index_name)

        # Get document count
        count_response = await client.count(index=index_name)
        doc_count = count_response.get("count", 0)

        print("\n" + "=" * 100)
        print(f"Index: {index_name}")
        print("=" * 100)

        print(f"\nDocument Count: {doc_count}")

        print("\n--- Mapping ---")
        print(json.dumps(index_info[index_name]["mappings"], indent=2))

        print("\n--- Settings ---")
        print(json.dumps(index_info[index_name]["settings"], indent=2))

        print("\n" + "=" * 100)

        await client.close()
        return 0

    except Exception as e:
        logger.error(f"Failed to inspect index: {e}", exc_info=True)
        return 1


async def count_documents(
    host: str,
    region: str,
    index_name: str
) -> int:
    """Count documents in an index."""
    try:
        client = await _get_client(host, region)

        # Check if index exists
        exists = await client.indices.exists(index=index_name)
        if not exists:
            logger.error(f"Index '{index_name}' does not exist")
            return 1

        # Count documents
        response = await client.count(index=index_name)
        doc_count = response.get("count", 0)

        print("\n" + "=" * 100)
        print(f"Index: {index_name}")
        print(f"Document Count: {doc_count}")
        print("=" * 100 + "\n")

        await client.close()
        return 0

    except Exception as e:
        logger.error(f"Failed to count documents: {e}", exc_info=True)
        return 1


async def search_documents(
    host: str,
    region: str,
    index_name: str,
    size: int = 10,
    query: Optional[Dict[str, Any]] = None
) -> int:
    """Search documents in an index."""
    try:
        client = await _get_client(host, region)

        # Check if index exists
        exists = await client.indices.exists(index=index_name)
        if not exists:
            logger.error(f"Index '{index_name}' does not exist")
            return 1

        # Default to match_all if no query provided
        if query is None:
            query = {"match_all": {}}

        # Search
        response = await client.search(
            index=index_name,
            body={
                "query": query,
                "size": size
            }
        )

        hits = response["hits"]["hits"]
        total = response["hits"]["total"]["value"]

        print("\n" + "=" * 100)
        print(f"Index: {index_name}")
        print(f"Total Documents: {total}")
        print(f"Showing: {len(hits)} documents")
        print("=" * 100)

        for i, hit in enumerate(hits, 1):
            print(f"\n--- Document {i} ---")
            print(f"ID: {hit['_id']}")
            print(f"Score: {hit.get('_score', 'N/A')}")
            print(f"Source:")
            print(json.dumps(hit["_source"], indent=2, default=str))

        print("\n" + "=" * 100 + "\n")

        await client.close()
        return 0

    except Exception as e:
        logger.error(f"Failed to search documents: {e}", exc_info=True)
        return 1


async def delete_index(
    host: str,
    region: str,
    index_name: str,
    confirm: bool = False
) -> int:
    """Delete an index."""
    try:
        client = await _get_client(host, region)

        # Check if index exists
        exists = await client.indices.exists(index=index_name)
        if not exists:
            logger.error(f"Index '{index_name}' does not exist")
            return 1

        # Get document count
        count_response = await client.count(index=index_name)
        doc_count = count_response.get("count", 0)

        print("\n" + "=" * 100)
        print(f"Index: {index_name}")
        print(f"Documents: {doc_count}")
        print("=" * 100)

        # Confirm deletion
        if not confirm:
            response = input(f"\nAre you sure you want to delete this index? (yes/no): ")
            if response.lower() != "yes":
                logger.info("Deletion cancelled")
                return 0

        # Delete
        logger.info(f"Deleting index: {index_name}")
        await client.indices.delete(index=index_name)
        logger.info(f"Successfully deleted index: {index_name}")

        await client.close()
        return 0

    except Exception as e:
        logger.error(f"Failed to delete index: {e}", exc_info=True)
        return 1


async def main_async(
    args: argparse.Namespace
) -> int:
    """Main async function."""
    host = args.host
    region = args.region

    if args.command == "list":
        return await list_indexes(host, region)
    elif args.command == "inspect":
        if not args.index:
            logger.error("--index is required for inspect command")
            return 1
        return await inspect_index(host, region, args.index)
    elif args.command == "count":
        if not args.index:
            logger.error("--index is required for count command")
            return 1
        return await count_documents(host, region, args.index)
    elif args.command == "search":
        if not args.index:
            logger.error("--index is required for search command")
            return 1
        return await search_documents(host, region, args.index, args.size)
    elif args.command == "delete":
        if not args.index:
            logger.error("--index is required for delete command")
            return 1
        return await delete_index(host, region, args.index, args.confirm)
    else:
        logger.error(f"Unknown command: {args.command}")
        return 1


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Manage AWS OpenSearch Serverless indexes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # List all indexes
    python manage-aoss-indexes.py list

    # Inspect specific index
    python manage-aoss-indexes.py inspect --index mcp-servers-default

    # Count documents
    python manage-aoss-indexes.py count --index mcp-agents-default

    # Search documents
    python manage-aoss-indexes.py search --index mcp-embeddings-default --size 5

    # Delete index (with confirmation)
    python manage-aoss-indexes.py delete --index old-index-name --confirm
"""
    )

    parser.add_argument(
        "command",
        choices=["list", "inspect", "count", "search", "delete"],
        help="Command to execute"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("OPENSEARCH_HOST", "qmnoselvyumijjiom050.us-east-1.aoss.amazonaws.com"),
        help="OpenSearch Serverless host"
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION", "us-east-1"),
        help="AWS region"
    )
    parser.add_argument(
        "--index",
        help="Index name (required for inspect, count, search, delete)"
    )
    parser.add_argument(
        "--size",
        type=int,
        default=10,
        help="Number of documents to return for search (default: 10)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt for delete"
    )

    args = parser.parse_args()

    # Run async main
    import asyncio
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
