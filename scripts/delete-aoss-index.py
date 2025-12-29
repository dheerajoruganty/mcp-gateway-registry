#!/usr/bin/env python3
"""
Delete an index from AWS OpenSearch Serverless.

Usage:
    uv run python scripts/delete-aoss-index.py --index mcp-embeddings-default
"""

import argparse
import logging
import sys
from opensearchpy import OpenSearch, AWSV4SignerAuth
import boto3


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_aws_auth(
    region: str
) -> AWSV4SignerAuth:
    """Get AWS SigV4 auth for OpenSearch Serverless."""
    credentials = boto3.Session().get_credentials()

    if not credentials:
        raise ValueError("No AWS credentials found")

    return AWSV4SignerAuth(credentials, region, "aoss")


def main():
    parser = argparse.ArgumentParser(description="Delete index from OpenSearch Serverless")
    parser.add_argument(
        "--host",
        default="qmnoselvyumijjiom050.us-east-1.aoss.amazonaws.com",
        help="OpenSearch Serverless host",
    )
    parser.add_argument(
        "--index",
        required=True,
        help="Index name to delete",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()

    # Create client with AWS SigV4 auth
    auth = _get_aws_auth(args.region)

    client = OpenSearch(
        hosts=[{"host": args.host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        timeout=30
    )

    # Check if index exists
    try:
        if not client.indices.exists(index=args.index):
            logger.error(f"Index '{args.index}' does not exist")
            return 1
    except Exception as e:
        logger.error(f"Failed to check if index exists: {e}")
        return 1

    # Get index info
    try:
        index_info = client.indices.get(index=args.index)
        logger.info(f"Index: {args.index}")

        # Count documents
        count_response = client.count(index=args.index)
        doc_count = count_response.get("count", 0)
        logger.info(f"Documents: {doc_count}")
    except Exception as e:
        logger.warning(f"Could not get index details: {e}")

    # Confirm deletion
    if not args.confirm:
        response = input(f"\nAre you sure you want to delete index '{args.index}'? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Deletion cancelled")
            return 0

    # Delete the index
    try:
        logger.info(f"Deleting index: {args.index}")
        client.indices.delete(index=args.index)
        logger.info(f"Successfully deleted index: {args.index}")
        return 0
    except Exception as e:
        logger.error(f"Failed to delete index: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
