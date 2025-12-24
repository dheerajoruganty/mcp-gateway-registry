#!/usr/bin/env python3
"""
Import security scan results from ~/mcp-gateway/security_scans/*.json into OpenSearch.

This script is meant to be run ONCE during first-time installation to migrate
existing security scan data from JSON files into OpenSearch indices.

Usage:
    # Default namespace
    uv run python scripts/import-security-scans-to-opensearch.py

    # Custom namespace
    uv run python scripts/import-security-scans-to-opensearch.py --namespace tenant-a

    # Custom scan directory
    uv run python scripts/import-security-scans-to-opensearch.py --scan-dir /path/to/scans

    # Recreate (delete and reimport)
    uv run python scripts/import-security-scans-to-opensearch.py --recreate

Requires:
    - OpenSearch running on localhost:9200 (or specified host/port)
    - Security scan JSON files in ~/mcp-gateway/security_scans/ directory
    - OpenSearch indices already created (run scripts/init-opensearch.py first)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

from opensearchpy import AsyncOpenSearch


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


DEFAULT_SCAN_DIR = Path.home() / "mcp-gateway" / "security_scans"


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


async def _clear_existing_scans(
    client: AsyncOpenSearch,
    index_name: str,
) -> None:
    """Delete all existing security scan documents from the index."""
    try:
        response = await client.delete_by_query(
            index=index_name,
            body={"query": {"match_all": {}}},
        )
        deleted_count = response.get("deleted", 0)
        logger.info(f"Deleted {deleted_count} existing scan documents from {index_name}")
    except Exception as e:
        logger.warning(f"Could not clear existing scans: {e}")


async def _load_scan_files(
    scan_dir: Path,
) -> list[Dict[str, Any]]:
    """Load all security scan JSON files from directory."""
    if not scan_dir.exists():
        logger.warning(f"Security scans directory does not exist: {scan_dir}")
        return []

    scan_files = list(scan_dir.glob("*.json"))
    if not scan_files:
        logger.warning(f"No JSON files found in {scan_dir}")
        return []

    scans = []
    for scan_file in scan_files:
        try:
            with open(scan_file, "r") as f:
                scan_data = json.load(f)
                scans.append(scan_data)
                logger.debug(f"Loaded scan from {scan_file.name}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {scan_file}: {e}")
        except Exception as e:
            logger.error(f"Error loading {scan_file}: {e}")

    logger.info(f"Loaded {len(scans)} security scan files from {scan_dir}")
    return scans


async def _import_security_scans(
    client: AsyncOpenSearch,
    index_name: str,
    scans: list[Dict[str, Any]],
) -> int:
    """Import security scans into OpenSearch."""
    imported_count = 0

    for scan_data in scans:
        server_path = scan_data.get("server_path")
        scan_timestamp = scan_data.get("scan_timestamp") or scan_data.get("scanned_at")

        if not server_path:
            logger.warning(f"Skipping scan without server_path: {scan_data}")
            continue

        doc_id = f"{server_path}:{scan_timestamp}"

        await client.index(
            index=index_name,
            id=doc_id,
            body=scan_data,
        )

        logger.info(f"Imported security scan: {server_path} at {scan_timestamp}")
        imported_count += 1

    return imported_count


async def _main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Import security scans from JSON files to OpenSearch"
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
        "--scan-dir",
        type=Path,
        default=DEFAULT_SCAN_DIR,
        help=f"Directory containing security scan JSON files (default: {DEFAULT_SCAN_DIR})",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete existing scans before importing",
    )
    args = parser.parse_args()

    index_name = f"mcp-security-scans-{args.namespace}"

    try:
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
            logger.info("Recreate flag set, clearing existing scans...")
            await _clear_existing_scans(client, index_name)

        scans = await _load_scan_files(args.scan_dir)

        if not scans:
            logger.warning("No security scans to import.")
            logger.info(f"Checked directory: {args.scan_dir}")
            await client.close()
            sys.exit(0)

        imported_count = await _import_security_scans(client, index_name, scans)

        await client.indices.refresh(index=index_name)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Import Summary:")
        logger.info(f"  Security Scans Imported: {imported_count}")
        logger.info(f"  Source Directory:        {args.scan_dir}")
        logger.info(f"  Target Index:            {index_name}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Security scans import completed successfully!")

        await client.close()

    except Exception as e:
        logger.exception(f"Unexpected error during security scans import: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
