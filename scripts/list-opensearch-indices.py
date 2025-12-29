#!/usr/bin/env python3
"""
List OpenSearch indices and basic cluster information.

Usage:
    # For local OpenSearch
    uv run python scripts/list-opensearch-indices.py

    # For AWS OpenSearch Serverless
    uv run python scripts/list-opensearch-indices.py \
        --host ecllfiaar6ayhg5s1ao8.us-east-1.aoss.amazonaws.com \
        --port 443 \
        --use-ssl \
        --auth-type aws_iam \
        --region us-east-1
"""

import argparse
import json
import logging
import os
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_aws_auth(
    region: str
) -> AWS4Auth:
    """Get AWS SigV4 auth for OpenSearch Serverless."""
    credentials = boto3.Session().get_credentials()
    return AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        "aoss",
        session_token=credentials.token,
    )


def main():
    parser = argparse.ArgumentParser(description="List OpenSearch indices")
    parser.add_argument(
        "--host",
        default=os.getenv("OPENSEARCH_HOST", "localhost"),
        help="OpenSearch host (without https://)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("OPENSEARCH_PORT", "9200")),
        help="OpenSearch port",
    )
    parser.add_argument(
        "--use-ssl",
        action="store_true",
        help="Use SSL/TLS",
    )
    parser.add_argument(
        "--auth-type",
        choices=["none", "basic", "aws_iam"],
        default="none",
        help="Authentication type",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION", "us-east-1"),
        help="AWS region (for aws_iam auth)",
    )
    parser.add_argument(
        "--user",
        default=os.getenv("OPENSEARCH_USER"),
        help="Username (for basic auth)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("OPENSEARCH_PASSWORD"),
        help="Password (for basic auth)",
    )
    args = parser.parse_args()

    # Configure authentication
    auth = None
    if args.auth_type == "basic":
        if not args.user or not args.password:
            logger.error("Username and password required for basic auth")
            return
        auth = (args.user, args.password)
    elif args.auth_type == "aws_iam":
        auth = _get_aws_auth(args.region)

    # Create client
    client = OpenSearch(
        hosts=[{"host": args.host, "port": args.port}],
        http_auth=auth,
        use_ssl=args.use_ssl,
        verify_certs=True,
        connection_class=RequestsHttpConnection if args.auth_type == "aws_iam" else None,
    )

    # Get cluster info
    try:
        info = client.info()
        logger.info(f"Connected to OpenSearch")
        logger.info(f"Cluster name: {info.get('cluster_name', 'N/A')}")
        logger.info(f"Version: {info['version']['number']}")
        logger.info(f"Distribution: {info['version'].get('distribution', 'N/A')}")
    except Exception as e:
        logger.error(f"Failed to connect to OpenSearch: {e}")
        return

    # List all indices
    try:
        indices = client.cat.indices(format="json")

        print("\n" + "=" * 80)
        print(f"Found {len(indices)} indices:")
        print("=" * 80)

        if indices:
            # Sort by index name
            indices.sort(key=lambda x: x.get("index", ""))

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
        else:
            print("\nNo indices found.")

        print("\n" + "=" * 80)

    except Exception as e:
        logger.error(f"Failed to list indices: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
