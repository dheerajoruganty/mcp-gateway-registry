#!/usr/bin/env python3
"""
Initialize OpenSearch Serverless indices and pipelines.

Usage:
    # For AWS OpenSearch Serverless
    uv run python scripts/init-opensearch-aws.py \
        --host ecllfiaar6ayhg5s1ao8.us-east-1.aoss.amazonaws.com \
        --port 443 \
        --use-ssl \
        --auth-type aws_iam \
        --region us-east-1

    # For local OpenSearch with basic auth
    uv run python scripts/init-opensearch-aws.py \
        --host localhost \
        --port 9200 \
        --auth-type basic \
        --user admin \
        --password admin

    # Recreate indices if they exist
    uv run python scripts/init-opensearch-aws.py \
        --host ecllfiaar6ayhg5s1ao8.us-east-1.aoss.amazonaws.com \
        --port 443 \
        --use-ssl \
        --auth-type aws_iam \
        --region us-east-1 \
        --recreate
"""

import argparse
import json
import logging
import os
from pathlib import Path

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCHEMAS_DIR = Path(__file__).parent / "opensearch-schemas"
INDEX_BASE_NAMES = [
    "mcp-servers",
    "mcp-agents",
    "mcp-scopes",
    "mcp-embeddings",
    "mcp-security-scans",
    "mcp-federation-config",
]


def _get_aws_auth(
    region: str
) -> AWS4Auth:
    """Get AWS SigV4 auth for OpenSearch Serverless."""
    credentials = boto3.Session().get_credentials()

    if not credentials:
        raise ValueError("No AWS credentials found. Configure AWS credentials.")

    auth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        region,
        "aoss",
        session_token=credentials.token,
    )

    logger.info(f"Configured AWS SigV4 auth for region: {region}, service: aoss")

    return auth


def main():
    parser = argparse.ArgumentParser(
        description="Initialize OpenSearch indices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--namespace",
        default=os.getenv("OPENSEARCH_NAMESPACE", "default"),
        help="Namespace for index names (default: 'default')",
    )
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
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate indices if they exist",
    )
    args = parser.parse_args()

    # Configure authentication
    auth = None
    connection_class = None

    if args.auth_type == "basic":
        if not args.user or not args.password:
            logger.error("Username and password required for basic auth")
            return
        auth = (args.user, args.password)
        logger.info("Using basic authentication")
    elif args.auth_type == "aws_iam":
        auth = _get_aws_auth(args.region)
        connection_class = RequestsHttpConnection
        logger.info(f"Using AWS IAM authentication (region: {args.region})")
    else:
        logger.info("Using no authentication")

    # Create client
    client_params = {
        "hosts": [{"host": args.host, "port": args.port}],
        "http_auth": auth,
        "use_ssl": args.use_ssl,
        "verify_certs": True,
    }

    if connection_class:
        client_params["connection_class"] = connection_class

    client = OpenSearch(**client_params)

    # Verify connection
    # Note: OpenSearch Serverless doesn't support client.info() call
    try:
        if args.auth_type == "aws_iam":
            # For OpenSearch Serverless, skip info() call
            logger.info(f"Connected to OpenSearch Serverless")
            logger.info(f"Host: {args.host}")
            logger.info(f"Using namespace: {args.namespace}")
        else:
            # For regular OpenSearch, use info() call
            info = client.info()
            logger.info(f"Connected to OpenSearch")
            logger.info(f"Cluster name: {info.get('cluster_name', 'N/A')}")
            logger.info(f"Version: {info['version']['number']}")
            logger.info(f"Distribution: {info['version'].get('distribution', 'N/A')}")
            logger.info(f"Using namespace: {args.namespace}")
    except Exception as e:
        logger.warning(f"Connection verification failed (may be normal for Serverless): {e}")
        logger.info(f"Proceeding with index creation anyway...")
        logger.info(f"Using namespace: {args.namespace}")

    # Create indices with namespace suffix
    for base_name in INDEX_BASE_NAMES:
        index_name = f"{base_name}-{args.namespace}"

        # For OpenSearch Serverless, use serverless-specific schema for embeddings
        # (Serverless uses VECTORSEARCH collection which supports k-NN differently)
        if args.auth_type == "aws_iam" and base_name == "mcp-embeddings":
            schema_file = SCHEMAS_DIR / f"{base_name}-serverless.json"
        else:
            schema_file = SCHEMAS_DIR / f"{base_name}.json"

        if not schema_file.exists():
            logger.warning(f"Schema file not found: {schema_file}, skipping {index_name}")
            continue

        with open(schema_file) as f:
            schema = json.load(f)

        try:
            if client.indices.exists(index=index_name):
                if args.recreate:
                    logger.info(f"Deleting existing index: {index_name}")
                    client.indices.delete(index=index_name)
                else:
                    logger.info(f"Index {index_name} already exists, skipping")
                    continue

            client.indices.create(index=index_name, body=schema)
            logger.info(f"Created index: {index_name}")
        except Exception as e:
            logger.error(f"Failed to create index {index_name}: {e}")
            continue

    # Create search pipeline (shared across namespaces)
    # Note: OpenSearch Serverless may not support custom search pipelines
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
            logger.warning(f"Pipeline creation failed (may not be supported in Serverless): {e}")

    logger.info(f"OpenSearch initialization complete for namespace '{args.namespace}'")


if __name__ == "__main__":
    main()
