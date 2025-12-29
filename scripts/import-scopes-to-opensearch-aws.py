#!/usr/bin/env python3
"""
Import scopes from auth_server/scopes.yml into OpenSearch Serverless.

This script supports both local OpenSearch and AWS OpenSearch Serverless.

Usage:
    # For AWS OpenSearch Serverless
    python import-scopes-to-opensearch-aws.py \
        --host ecllfiaar6ayhg5s1ao8.us-east-1.aoss.amazonaws.com \
        --port 443 \
        --use-ssl \
        --auth-type aws_iam \
        --region us-east-1

    # For local OpenSearch with basic auth
    python import-scopes-to-opensearch-aws.py \
        --host localhost \
        --port 9200 \
        --auth-type basic \
        --user admin \
        --password admin

    # Recreate (delete and reimport)
    python import-scopes-to-opensearch-aws.py \
        --host ecllfiaar6ayhg5s1ao8.us-east-1.aoss.amazonaws.com \
        --port 443 \
        --use-ssl \
        --auth-type aws_iam \
        --region us-east-1 \
        --recreate
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import boto3
import yaml
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Determine scopes file location
# In container: script is at /app/import-scopes-to-opensearch-aws.py
# Locally: script is at /path/to/repo/scripts/import-scopes-to-opensearch-aws.py
script_dir = Path(__file__).parent
if (script_dir / ".." / "auth_server" / "scopes.yml").exists():
    # Running locally from scripts/ directory
    SCOPES_FILE = script_dir / ".." / "auth_server" / "scopes.yml"
elif Path("/app/auth_server/scopes.yml").exists():
    # Running in container
    SCOPES_FILE = Path("/app/auth_server/scopes.yml")
else:
    # Fallback - assume container path
    SCOPES_FILE = Path("/app/auth_server/scopes.yml")


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


def _load_scopes_yaml() -> Dict[str, Any]:
    """Load scopes from YAML file."""
    logger.info(f"Looking for scopes file at: {SCOPES_FILE}")
    logger.info(f"File exists: {SCOPES_FILE.exists()}")
    if not SCOPES_FILE.exists():
        # List what's actually in /app to help debug
        import os
        logger.error(f"Contents of /app: {os.listdir('/app') if os.path.exists('/app') else 'N/A'}")
        if os.path.exists('/app/auth_server'):
            logger.error(f"Contents of /app/auth_server: {os.listdir('/app/auth_server')}")
        raise FileNotFoundError(f"Scopes file not found: {SCOPES_FILE}")

    with open(SCOPES_FILE, "r") as f:
        scopes_data = yaml.safe_load(f)

    logger.info(f"Loaded scopes from {SCOPES_FILE}")
    return scopes_data


def _get_opensearch_client(
    host: str,
    port: int,
    use_ssl: bool,
    auth_type: str,
    region: str = None,
    user: str = None,
    password: str = None,
) -> OpenSearch:
    """Create OpenSearch client."""
    auth = None
    connection_class = None

    if auth_type == "basic":
        if not user or not password:
            raise ValueError("Username and password required for basic auth")
        auth = (user, password)
        logger.info("Using basic authentication")
    elif auth_type == "aws_iam":
        if not region:
            raise ValueError("Region required for AWS IAM auth")
        auth = _get_aws_auth(region)
        connection_class = RequestsHttpConnection
        logger.info(f"Using AWS IAM authentication (region: {region})")
    else:
        logger.info("Using no authentication")

    client_params = {
        "hosts": [{"host": host, "port": port}],
        "http_auth": auth,
        "use_ssl": use_ssl,
        "verify_certs": True,
    }

    if connection_class:
        client_params["connection_class"] = connection_class

    client = OpenSearch(**client_params)

    if auth_type == "aws_iam":
        logger.info(f"Connected to OpenSearch Serverless")
        logger.info(f"Host: {host}")
    else:
        info = client.info()
        logger.info(f"Connected to OpenSearch {info['version']['number']}")

    return client


def _clear_existing_scopes(
    client: OpenSearch,
    index_name: str,
) -> None:
    """Delete all existing scope documents from the index."""
    try:
        response = client.delete_by_query(
            index=index_name,
            body={"query": {"match_all": {}}},
        )
        deleted_count = response.get("deleted", 0)
        logger.info(f"Deleted {deleted_count} existing scope documents from {index_name}")
    except Exception as e:
        logger.warning(f"Could not clear existing scopes: {e}")


def _import_ui_scopes(
    client: OpenSearch,
    index_name: str,
    ui_scopes: Dict[str, Any],
) -> int:
    """Import UI scopes into OpenSearch."""
    imported_count = 0

    for scope_name, permissions in ui_scopes.items():
        doc = {
            "scope_type": "ui_scope",
            "scope_name": scope_name,
            "ui_permissions": permissions,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # OpenSearch Serverless doesn't support custom document IDs
        # Let OpenSearch auto-generate the ID
        client.index(
            index=index_name,
            body=doc,
        )

        logger.info(f"Imported UI scope: {scope_name}")
        imported_count += 1

    return imported_count


def _import_group_mappings(
    client: OpenSearch,
    index_name: str,
    group_mappings: Dict[str, Any],
) -> int:
    """Import group mappings into OpenSearch."""
    imported_count = 0

    for group_name, mapped_scopes in group_mappings.items():
        doc = {
            "scope_type": "group_mapping",
            "group_name": group_name,
            "group_mappings": mapped_scopes,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # OpenSearch Serverless doesn't support custom document IDs
        # Let OpenSearch auto-generate the ID
        client.index(
            index=index_name,
            body=doc,
        )

        logger.info(f"Imported group mapping: {group_name}")
        imported_count += 1

    return imported_count


def _import_server_scopes(
    client: OpenSearch,
    index_name: str,
    scopes_data: Dict[str, Any],
) -> int:
    """Import server access scopes into OpenSearch."""
    imported_count = 0

    skip_keys = {"UI-Scopes", "group_mappings"}

    for scope_name, server_access_list in scopes_data.items():
        if scope_name in skip_keys:
            continue

        if not isinstance(server_access_list, list):
            logger.warning(f"Skipping invalid server scope: {scope_name}")
            continue

        doc = {
            "scope_type": "server_scope",
            "scope_name": scope_name,
            "server_access": server_access_list,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # OpenSearch Serverless doesn't support custom document IDs
        # Let OpenSearch auto-generate the ID
        client.index(
            index=index_name,
            body=doc,
        )

        logger.info(f"Imported server scope: {scope_name}")
        imported_count += 1

    return imported_count


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import scopes from auth_server/scopes.yml to OpenSearch",
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
        help="Delete existing scopes before importing",
    )
    args = parser.parse_args()

    index_name = f"mcp-scopes-{args.namespace}"

    try:
        scopes_data = _load_scopes_yaml()

        client = _get_opensearch_client(
            host=args.host,
            port=args.port,
            use_ssl=args.use_ssl,
            auth_type=args.auth_type,
            region=args.region,
            user=args.user,
            password=args.password,
        )

        index_exists = client.indices.exists(index=index_name)
        if not index_exists:
            logger.error(
                f"Index {index_name} does not exist. "
                f"Run 'init-opensearch-aws.py' first to create indices."
            )
            sys.exit(1)

        logger.info(f"Using namespace: {args.namespace}")
        logger.info(f"Target index: {index_name}")

        if args.recreate:
            logger.info("Recreate flag set, clearing existing scopes...")
            _clear_existing_scopes(client, index_name)

        ui_scopes = scopes_data.get("UI-Scopes", {})
        ui_count = _import_ui_scopes(client, index_name, ui_scopes)

        group_mappings = scopes_data.get("group_mappings", {})
        mapping_count = _import_group_mappings(client, index_name, group_mappings)

        server_count = _import_server_scopes(client, index_name, scopes_data)

        # OpenSearch Serverless doesn't support refresh API
        # Data is available immediately after indexing
        # client.indices.refresh(index=index_name)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Scopes Import Summary:")
        logger.info(f"  UI Scopes:       {ui_count}")
        logger.info(f"  Group Mappings:  {mapping_count}")
        logger.info(f"  Server Scopes:   {server_count}")
        logger.info(f"  Total Imported:  {ui_count + mapping_count + server_count}")
        logger.info(f"  Target Index:    {index_name}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Scopes import completed successfully!")

    except FileNotFoundError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error during scopes import: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
