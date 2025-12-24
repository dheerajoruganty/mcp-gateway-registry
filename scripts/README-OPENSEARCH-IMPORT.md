# OpenSearch Data Import Scripts

This directory contains scripts for initializing OpenSearch indices and importing existing data from file-based storage into OpenSearch.

## Overview

The MCP Gateway Registry supports two storage backends:
- **File Backend**: Legacy storage using JSON files and YAML (backward compatible)
- **OpenSearch Backend**: Production-ready distributed storage with search capabilities

These scripts help migrate from file-based storage to OpenSearch during first-time installation.

## Scripts

### 1. init-opensearch.py

**Purpose**: Create OpenSearch indices with proper schemas

**Usage**:
```bash
# Create indices with default namespace
uv run python scripts/init-opensearch.py

# Create indices with custom namespace
uv run python scripts/init-opensearch.py --namespace tenant-a

# Recreate indices (delete and create)
uv run python scripts/init-opensearch.py --recreate
```

**What it does**:
- Creates 5 OpenSearch indices:
  - `mcp-servers-{namespace}` - MCP server registrations
  - `mcp-agents-{namespace}` - A2A agent registrations
  - `mcp-scopes-{namespace}` - Authorization scopes
  - `mcp-embeddings-{namespace}` - Vector embeddings for hybrid search
  - `mcp-security-scans-{namespace}` - Security scan results
- Creates hybrid search pipeline for BM25 + k-NN search
- Uses schema definitions from `opensearch-schemas/` directory

**Requirements**:
- OpenSearch running on localhost:9200 (or specified host/port)

### 2. import-scopes-to-opensearch.py

**Purpose**: Import authorization scopes from `auth_server/scopes.yml` into OpenSearch

**Usage**:
```bash
# Import scopes with default namespace
uv run python scripts/import-scopes-to-opensearch.py

# Import scopes with custom namespace
uv run python scripts/import-scopes-to-opensearch.py --namespace tenant-a

# Reimport (delete existing and import fresh)
uv run python scripts/import-scopes-to-opensearch.py --recreate
```

**What it does**:
- Reads `auth_server/scopes.yml`
- Imports three types of scope documents:
  - **UI Scopes**: Agent registry permissions (list, get, publish, modify, delete)
  - **Group Mappings**: Maps Keycloak groups to scope names
  - **Server Scopes**: MCP server method/tool access permissions
- Creates properly structured documents in `mcp-scopes-{namespace}` index
- Adds timestamps to all documents

**Requirements**:
- OpenSearch running and indices created (run `init-opensearch.py` first)
- `auth_server/scopes.yml` file exists

**Output Example**:
```
Imported UI scope: mcp-registry-admin
Imported UI scope: registry-admins
Imported UI scope: registry-users-lob1
Imported UI scope: registry-users-lob2
Imported group mapping: mcp-registry-admin
Imported group mapping: registry-admins
Imported server scope: mcp-servers-unrestricted/read
Imported server scope: mcp-servers-unrestricted/execute

Import Summary:
  UI Scopes:       4
  Group Mappings:  2
  Server Scopes:   10
  Total Imported:  16
  Target Index:    mcp-scopes-default
```

### 3. import-security-scans-to-opensearch.py

**Purpose**: Import security scan results from JSON files into OpenSearch

**Usage**:
```bash
# Import scans from default directory (~/mcp-gateway/security_scans/)
uv run python scripts/import-security-scans-to-opensearch.py

# Import scans from custom directory
uv run python scripts/import-security-scans-to-opensearch.py --scan-dir /path/to/scans

# Import with custom namespace
uv run python scripts/import-security-scans-to-opensearch.py --namespace tenant-a

# Reimport (delete existing and import fresh)
uv run python scripts/import-security-scans-to-opensearch.py --recreate
```

**What it does**:
- Scans `~/mcp-gateway/security_scans/` for `*.json` files
- Imports each security scan result into OpenSearch
- Creates document IDs based on server path and timestamp
- Handles missing or invalid JSON files gracefully

**Requirements**:
- OpenSearch running and indices created (run `init-opensearch.py` first)
- Security scan JSON files in `~/mcp-gateway/security_scans/` directory (optional)

**Output Example**:
```
Loaded 3 security scan files from /home/user/mcp-gateway/security_scans
Imported security scan: /cloudflare-docs at 2025-12-22T10:30:00
Imported security scan: /context7 at 2025-12-22T10:31:00
Imported security scan: /currenttime at 2025-12-22T10:32:00

Import Summary:
  Security Scans Imported: 3
  Source Directory:        /home/user/mcp-gateway/security_scans
  Target Index:            mcp-security-scans-default
```

## First-Time Installation Workflow

**Complete procedure for migrating to OpenSearch backend:**

```bash
# Step 1: Start OpenSearch
docker-compose up -d opensearch
sleep 10  # Wait for OpenSearch to be ready

# Step 2: Create all indices
uv run python scripts/init-opensearch.py

# Verify indices created
curl "http://localhost:9200/_cat/indices?v" | grep mcp-

# Step 3: Import scopes from YAML to OpenSearch
uv run python scripts/import-scopes-to-opensearch.py

# Verify scopes imported
curl "http://localhost:9200/mcp-scopes-default/_count?pretty"

# Step 4: Import security scans (if they exist)
uv run python scripts/import-security-scans-to-opensearch.py

# Verify scans imported
curl "http://localhost:9200/mcp-security-scans-default/_count?pretty"

# Step 5: Configure registry to use OpenSearch backend
export STORAGE_BACKEND=opensearch

# Step 6: Start registry service
docker-compose up -d registry

# Step 7: Verify registry is using OpenSearch
docker-compose logs registry | grep "Creating.*repository with backend: opensearch"
```

## Verification Commands

### Check All Indices
```bash
curl "http://localhost:9200/_cat/indices?v"
```

Expected output:
```
health status index                        uuid                   pri rep docs.count docs.deleted store.size pri.store.size
yellow open   mcp-servers-default          xxxxxxxxxxx            1   1          0            0       208b           208b
yellow open   mcp-agents-default           xxxxxxxxxxx            1   1          0            0       208b           208b
yellow open   mcp-scopes-default           xxxxxxxxxxx            1   1         16            0      4.5kb          4.5kb
yellow open   mcp-embeddings-default       xxxxxxxxxxx            1   1          0            0       208b           208b
yellow open   mcp-security-scans-default   xxxxxxxxxxx            1   1          3            0      2.1kb          2.1kb
```

### Check Scopes Import
```bash
# Count documents
curl "http://localhost:9200/mcp-scopes-default/_count?pretty"

# Search for specific scope
curl "http://localhost:9200/mcp-scopes-default/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "term": {
      "scope_name": "mcp-registry-admin"
    }
  }
}'

# List all UI scopes
curl "http://localhost:9200/mcp-scopes-default/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "term": {
      "scope_type": "ui_scope"
    }
  }
}'
```

### Check Security Scans Import
```bash
# Count documents
curl "http://localhost:9200/mcp-security-scans-default/_count?pretty"

# Search for specific server scan
curl "http://localhost:9200/mcp-security-scans-default/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "term": {
      "server_path": "/cloudflare-docs"
    }
  }
}'
```

## Environment Variables

All scripts support environment variables for configuration:

```bash
# OpenSearch connection
export OPENSEARCH_HOST=localhost
export OPENSEARCH_PORT=9200
export OPENSEARCH_NAMESPACE=default

# Run scripts with environment variables
uv run python scripts/init-opensearch.py
uv run python scripts/import-scopes-to-opensearch.py
uv run python scripts/import-security-scans-to-opensearch.py
```

## Troubleshooting

### Index Already Exists
```bash
# Use --recreate flag to delete and recreate
uv run python scripts/init-opensearch.py --recreate
```

### Scopes Already Imported
```bash
# Use --recreate flag to delete existing and reimport
uv run python scripts/import-scopes-to-opensearch.py --recreate
```

### OpenSearch Not Running
```bash
# Check OpenSearch status
curl "http://localhost:9200"

# Start OpenSearch
docker-compose up -d opensearch

# Check logs
docker-compose logs opensearch
```

### Import Failed
```bash
# Check index exists
curl "http://localhost:9200/_cat/indices?v" | grep mcp-

# If index missing, create it first
uv run python scripts/init-opensearch.py
```

## File Storage vs OpenSearch Storage

### File Backend Mode (`STORAGE_BACKEND=file`)
- Scopes read from `auth_server/scopes.yml`
- Security scans read from `~/mcp-gateway/security_scans/*.json`
- Servers/agents stored in JSON files
- No OpenSearch required

### OpenSearch Backend Mode (`STORAGE_BACKEND=opensearch`)
- All data stored in OpenSearch indices
- Requires initial import from files
- Enables hybrid search (BM25 + k-NN)
- Production-ready scalability
- Multi-tenancy via namespaces

## Notes

1. **First-Time Installation Only**: These import scripts are meant to be run ONCE during initial migration from file-based storage to OpenSearch.

2. **Backward Compatibility**: The file-based backend remains functional. You can switch between backends by changing `STORAGE_BACKEND` environment variable.

3. **Data Consistency**: After importing, the OpenSearch indices become the source of truth when using `STORAGE_BACKEND=opensearch`. Changes to YAML/JSON files will NOT automatically sync.

4. **Namespaces**: Use namespaces for multi-tenancy. Each namespace gets its own set of indices (e.g., `mcp-scopes-tenant-a`, `mcp-scopes-tenant-b`).

5. **Security Scans**: If you don't have existing security scan files, the import script will complete gracefully with a warning.
