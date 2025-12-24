#!/usr/bin/env python3
"""
Import scopes from auth_server/scopes.yml into OpenSearch.

This script is meant to be run ONCE during first-time installation to migrate
existing scopes data from the YAML file into OpenSearch indices.

Usage:
    # Default namespace
    uv run python scripts/import-scopes-to-opensearch.py

    # Custom namespace
    uv run python scripts/import-scopes-to-opensearch.py --namespace tenant-a

    # Recreate (delete and reimport)
    uv run python scripts/import-scopes-to-opensearch.py --recreate

Requires:
    - OpenSearch running on localhost:9200 (or specified host/port)
    - auth_server/scopes.yml file exists
    - OpenSearch indices already created (run scripts/init-opensearch.py first)
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml
from opensearchpy import AsyncOpenSearch


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


SCOPES_FILE = Path(__file__).parent.parent / "auth_server" / "scopes.yml"


async def _load_scopes_yaml() -> Dict[str, Any]:
    """Load scopes from YAML file."""
    if not SCOPES_FILE.exists():
        raise FileNotFoundError(f"Scopes file not found: {SCOPES_FILE}")

    with open(SCOPES_FILE, "r") as f:
        scopes_data = yaml.safe_load(f)

    logger.info(f"Loaded scopes from {SCOPES_FILE}")
    return scopes_data


async def _get_opensearch_client(
    host: str,
    port: int,
) -> AsyncOpenSearch:
    """Create OpenSearch async client."""
    client = AsyncOpenSearch(
        hosts=[{"host": host, "port": port}],
        use_ssl=False,
        verify_certs=False,
    )

    info = await client.info()
    logger.info(f"Connected to OpenSearch {info['version']['number']}")
    return client


async def _clear_existing_scopes(
    client: AsyncOpenSearch,
    index_name: str,
) -> None:
    """Delete all existing scope documents from the index."""
    try:
        response = await client.delete_by_query(
            index=index_name,
            body={"query": {"match_all": {}}},
        )
        deleted_count = response.get("deleted", 0)
        logger.info(f"Deleted {deleted_count} existing scope documents from {index_name}")
    except Exception as e:
        logger.warning(f"Could not clear existing scopes: {e}")


async def _import_ui_scopes(
    client: AsyncOpenSearch,
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

        doc_id = f"ui_scope:{scope_name}"

        await client.index(
            index=index_name,
            id=doc_id,
            body=doc,
        )

        logger.info(f"Imported UI scope: {scope_name}")
        imported_count += 1

    return imported_count


async def _import_group_mappings(
    client: AsyncOpenSearch,
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

        doc_id = f"group_mapping:{group_name}"

        await client.index(
            index=index_name,
            id=doc_id,
            body=doc,
        )

        logger.info(f"Imported group mapping: {group_name}")
        imported_count += 1

    return imported_count


async def _import_server_scopes(
    client: AsyncOpenSearch,
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

        doc_id = f"server_scope:{scope_name}"

        await client.index(
            index=index_name,
            id=doc_id,
            body=doc,
        )

        logger.info(f"Imported server scope: {scope_name}")
        imported_count += 1

    return imported_count


async def _main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import scopes from auth_server/scopes.yml to OpenSearch"
    )
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
        help="Delete existing scopes before importing",
    )
    args = parser.parse_args()

    index_name = f"mcp-scopes-{args.namespace}"

    try:
        scopes_data = await _load_scopes_yaml()

        client = await _get_opensearch_client(
            host=args.host,
            port=args.port,
        )

        index_exists = await client.indices.exists(index=index_name)
        if not index_exists:
            logger.error(
                f"Index {index_name} does not exist. "
                f"Run 'uv run python scripts/init-opensearch.py' first."
            )
            sys.exit(1)

        if args.recreate:
            logger.info("Recreate flag set, clearing existing scopes...")
            await _clear_existing_scopes(client, index_name)

        ui_scopes = scopes_data.get("UI-Scopes", {})
        ui_count = await _import_ui_scopes(client, index_name, ui_scopes)

        group_mappings = scopes_data.get("group_mappings", {})
        mapping_count = await _import_group_mappings(client, index_name, group_mappings)

        server_count = await _import_server_scopes(client, index_name, scopes_data)

        await client.indices.refresh(index=index_name)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Import Summary:")
        logger.info(f"  UI Scopes:       {ui_count}")
        logger.info(f"  Group Mappings:  {mapping_count}")
        logger.info(f"  Server Scopes:   {server_count}")
        logger.info(f"  Total Imported:  {ui_count + mapping_count + server_count}")
        logger.info(f"  Target Index:    {index_name}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Scopes import completed successfully!")

        await client.close()

    except FileNotFoundError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error during scopes import: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
