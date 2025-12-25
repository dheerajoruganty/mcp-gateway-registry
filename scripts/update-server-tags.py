#!/usr/bin/env python3
"""Update server tags in OpenSearch mcp-servers index."""

import json
from opensearchpy import OpenSearch

# Server tags mapping from JSON config files
SERVER_TAGS = {
    "/currenttime/": ["time", "timezone", "datetime", "api", "utility"],
    "/cloudflare-docs": ["documentation", "cloudflare", "cdn", "workers", "pages", "migration-guide"],
    "/mcpgw/": ["registry", "management", "admin", "gateway", "mcp-tools", "server-management"],
    "/context7": ["documentation", "search", "libraries", "packages", "api-reference", "code-examples"],
}

# Connect to OpenSearch
client = OpenSearch(
    hosts=[{"host": "localhost", "port": 9200}],
    http_auth=("admin", "admin"),
    use_ssl=False,
    verify_certs=False
)

# Update each server
for path, tags in SERVER_TAGS.items():
    # Convert path to document ID
    doc_id = path.replace("/", "").rstrip("/") or path.replace("/", "_").strip("_")

    # Get possible IDs
    possible_ids = [
        path.replace("/", "").rstrip("/"),
        path.replace("/", "_").strip("_"),
        path.rstrip("/").lstrip("/"),
    ]

    # Try each ID
    updated = False
    for doc_id in possible_ids:
        try:
            response = client.update(
                index="mcp-servers-default",
                id=doc_id,
                body={
                    "doc": {"tags": tags}
                },
                refresh=True
            )
            print(f"Updated {path} (id: {doc_id}) with tags: {tags}")
            updated = True
            break
        except Exception as e:
            continue

    if not updated:
        print(f"FAILED to update {path}")

print("\nDone updating server tags in mcp-servers index")
