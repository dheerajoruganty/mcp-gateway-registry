# Database Design - MCP Gateway Registry

## Overview

The MCP Gateway Registry supports two storage backends for data persistence:

1. **File-Based Backend** (Legacy, Not Recommended)
   - JSON file storage in the local filesystem
   - Maintained for backwards compatibility only
   - Single-node deployments only
   - No support for distributed deployments

2. **OpenSearch Backend** (Default, Recommended)
   - Distributed search and analytics engine
   - Production-ready with clustering support
   - Multi-tenancy support via namespaces
   - Advanced search capabilities with hybrid BM25 + k-NN search
   - Recommended for all new deployments

The default configuration uses OpenSearch as the primary storage backend.

---

## OpenSearch Architecture

### Indexes

The OpenSearch backend maintains six indexes for different data types. All index names are suffixed with the configured namespace to support multi-tenancy.

#### 1. **mcp-servers** - Server Metadata

Stores MCP server definitions and metadata.

**Index Name Pattern:** `mcp-servers-{namespace}`
**Schema Location:** [`scripts/opensearch-schemas/mcp-servers.json`](../scripts/opensearch-schemas/mcp-servers.json)

**Document Structure:**

```json
{
  "server_name": "model-context-protocol",
  "description": "Model Context Protocol server implementation",
  "path": "/servers/mcp",
  "proxy_pass_url": "http://server-host:8080",
  "supported_transports": ["stdio", "sse"],
  "auth_type": "none",
  "tags": ["protocol", "mcp"],
  "num_tools": 42,
  "num_stars": 1250,
  "is_python": true,
  "license": "Apache-2.0",
  "tool_list": [
    {
      "name": "get_resources",
      "description": "Retrieve available resources",
      "parsed_description": {},
      "schema": {}
    }
  ],
  "is_enabled": true,
  "registered_at": "2024-12-01T10:00:00Z",
  "updated_at": "2024-12-20T15:30:00Z"
}
```

**Key Fields:**
- `server_name` (text): Server name with keyword subfield for exact matching
- `path` (keyword): Unique server path identifier
- `proxy_pass_url` (keyword): Backend proxy URL for the server
- `supported_transports` (keyword): Available transport types (stdio, sse, websocket, etc.)
- `auth_type` (keyword): Authentication method (none, oauth, api-key, etc.)
- `tags` (keyword): Searchable tags for categorization
- `num_tools` (integer): Total number of tools exposed
- `tool_list` (nested): Array of tool definitions with name and description

---

#### 2. **mcp-agents** - A2A Agent Cards

Stores Agent-to-Agent (A2A) agent cards and their capabilities.

**Index Name Pattern:** `mcp-agents-{namespace}`
**Schema Location:** [`scripts/opensearch-schemas/mcp-agents.json`](../scripts/opensearch-schemas/mcp-agents.json)

**Document Structure:**

```json
{
  "protocol_version": "1.0",
  "name": "financial-analysis-agent",
  "description": "Performs financial analysis and market research",
  "path": "/agents/finance",
  "url": "https://agent-registry.example.com/agents/finance",
  "version": "2.1.0",
  "skills": [
    {
      "id": "skill-001",
      "name": "analyze_earnings",
      "description": "Analyze company earnings reports",
      "tags": ["financial", "analysis"]
    },
    {
      "id": "skill-002",
      "name": "market_research",
      "description": "Research market trends",
      "tags": ["research", "market"]
    }
  ],
  "tags": ["finance", "analysis", "research"],
  "is_enabled": true,
  "visibility": "public",
  "trust_level": "high",
  "registered_at": "2024-11-15T09:00:00Z",
  "updated_at": "2024-12-20T14:20:00Z"
}
```

**Key Fields:**
- `name` (text): Agent name with keyword subfield
- `protocol_version` (keyword): MCP protocol version
- `path` (keyword): Unique agent path identifier
- `skills` (nested): Array of agent capabilities with id, name, description, and tags
- `visibility` (keyword): Access level (public, private, restricted)
- `trust_level` (keyword): Trust classification (low, medium, high, verified)
- `tags` (keyword): Searchable tags for discovery and filtering

---

#### 3. **mcp-scopes** - Authorization & Access Control

Stores authorization scopes, permission mappings, and UI access control configurations.

**Index Name Pattern:** `mcp-scopes-{namespace}`
**Schema Location:** [`scripts/opensearch-schemas/mcp-scopes.json`](../scripts/opensearch-schemas/mcp-scopes.json)

**Document Structure:**

The scopes index stores three separate document types, each with a distinct structure:

**Example 1: Server Scope Document**

```json
{
  "scope_type": "server_scope",
  "scope_name": "admin_access",
  "server_access": [
    {
      "server": "financial_server",
      "methods": ["GET", "POST", "PUT"],
      "tools": ["analyze_data", "generate_report"]
    },
    {
      "server": "analytics_server",
      "methods": ["GET"],
      "tools": null
    }
  ],
  "description": "Administrator access to financial and analytics servers",
  "created_at": "2024-12-01T10:00:00Z",
  "updated_at": "2024-12-20T15:30:00Z"
}
```

**Example 2: Group Mapping Document**

```json
{
  "scope_type": "group_mapping",
  "group_name": "finance_team",
  "group_mappings": ["admin_access", "read_only_access", "reporting_access"],
  "created_at": "2024-12-01T10:00:00Z",
  "updated_at": "2024-12-20T15:30:00Z"
}
```

**Example 3: UI Scope Document**

```json
{
  "scope_type": "ui_scope",
  "scope_name": "finance_team",
  "ui_permissions": {
    "list_service": ["financial_server", "analytics_server", "reporting_server"]
  },
  "created_at": "2024-12-01T10:00:00Z",
  "updated_at": "2024-12-20T15:30:00Z"
}
```

**Document Types:**
The scopes index stores three separate document types, distinguished by the `scope_type` field:

1. **server_scope**: Defines server-level access permissions
   - Fields: `scope_type`, `scope_name`, `server_access` (nested), `description`

2. **group_mapping**: Maps user groups to scopes
   - Fields: `scope_type`, `group_name`, `group_mappings` (keyword array)

3. **ui_scope**: Controls UI element visibility and access
   - Fields: `scope_type`, `scope_name`, `ui_permissions` (object)

**Key Fields:**
- `scope_type` (keyword): Type of authorization scope (server_scope, group_mapping, ui_scope)
- `scope_name` (keyword): Unique scope identifier
- `server_access` (nested): Array with server name, methods, and tools array
- `group_mappings` (keyword): User groups associated with this scope
- `ui_permissions` (object): UI feature access control flags

---

#### 4. **mcp-embeddings** - Search Vectors with k-NN

Stores vector embeddings for semantic search across servers and agents.

**Index Name Pattern:** `mcp-embeddings-{namespace}`
**Schema Location:** [`scripts/opensearch-schemas/mcp-embeddings.json`](../scripts/opensearch-schemas/mcp-embeddings.json)

**Configuration:**
- **KNN Algorithm:** HNSW (Hierarchical Navigable Small World)
- **Space Type:** Cosine Similarity
- **Engine:** Lucene
- **Dimension:** 384 (default) or 1024 (with Bedrock Titan v2)
- **ef_construction:** 128 (HNSW construction parameter)
- **m:** 16 (HNSW connection count)

**Document Structure:**

The embeddings index stores two entity types, distinguished by the `entity_type` field:

**Entity Type 1: MCP Server Embedding**

```json
{
  "entity_type": "mcp_server",
  "path": "financial_server",
  "name": "Financial Data Server",
  "description": "Provides financial data analysis and reporting tools",
  "tags": ["finance", "data", "analysis"],
  "is_enabled": true,
  "text_for_embedding": "Financial Data Server. Provides financial data analysis and reporting tools. Tools: analyze_earnings, generate_report, portfolio_analysis",
  "embedding": [0.125, -0.342, 0.098, -0.215, 0.456, ...],
  "tools": [
    {
      "name": "analyze_earnings",
      "description": "Analyze company earnings reports"
    },
    {
      "name": "generate_report",
      "description": "Generate financial summary reports"
    }
  ],
  "metadata": {
    "server_name": "Financial Data Server",
    "proxy_pass_url": "http://localhost:8000",
    "num_tools": 15
  },
  "indexed_at": "2024-12-20T15:30:00Z"
}
```

**Entity Type 2: A2A Agent Embedding**

```json
{
  "entity_type": "a2a_agent",
  "path": "agents_financial_analyst",
  "name": "Financial Analysis Agent",
  "description": "Analyzes financial data and provides insights",
  "tags": ["finance", "analysis", "agent"],
  "is_enabled": true,
  "text_for_embedding": "Financial Analysis Agent. Analyzes financial data and provides insights. Skills: earnings_analysis, market_research, risk_assessment",
  "embedding": [0.215, -0.128, 0.342, -0.098, 0.567, ...],
  "skills": [
    {
      "id": "skill-001",
      "name": "earnings_analysis",
      "description": "Analyze company earnings reports"
    },
    {
      "id": "skill-002",
      "name": "market_research",
      "description": "Research market trends and patterns"
    }
  ],
  "metadata": {
    "protocol_version": "1.0",
    "url": "https://agent.example.com/financial-analyst",
    "version": "2.1.0"
  },
  "indexed_at": "2024-12-20T15:30:00Z"
}
```

**Key Fields:**
- `embedding` (knn_vector): 384-dimensional vector for semantic search
- `entity_type` (keyword): Type of entity (mcp_server or a2a_agent)
- `text_for_embedding` (text): Combined text used to generate the embedding
- `tools` (nested): Associated tools with descriptions (for MCP servers)
- `skills` (nested): Associated agent skills with descriptions (for A2A agents)
- `metadata` (object, disabled): Flexible metadata storage

---

#### 5. **mcp-security-scans** - Security Scan Results

Stores security vulnerability scan results and risk assessments.

**Index Name Pattern:** `mcp-security-scans-{namespace}`
**Schema Location:** [`scripts/opensearch-schemas/mcp-security-scans.json`](../scripts/opensearch-schemas/mcp-security-scans.json)

**Document Structure:**

```json
{
  "server_path": "financial_server",
  "scan_timestamp": "2024-12-20T10:30:00Z",
  "scan_status": "unsafe",
  "vulnerabilities": [
    {
      "severity": "high",
      "title": "SQL Injection vulnerability in query handler",
      "description": "User input not properly sanitized in database queries",
      "cve_id": "CVE-2024-12345",
      "package_name": "db-connector",
      "package_version": "2.1.0",
      "fixed_version": "2.1.5"
    },
    {
      "severity": "medium",
      "title": "Outdated dependency with known issues",
      "description": "Package has known security vulnerabilities",
      "cve_id": "CVE-2024-67890",
      "package_name": "http-client",
      "package_version": "1.2.3",
      "fixed_version": "1.3.0"
    }
  ],
  "risk_score": 0.75,
  "total_vulnerabilities": 2,
  "critical_count": 0,
  "high_count": 1,
  "medium_count": 1,
  "low_count": 0,
  "scan_metadata": {
    "scanner": "security-analyzer-v2",
    "scan_duration_ms": 3456
  }
}
```

**Key Fields:**
- `server_path` (keyword): Path to the scanned server/agent
- `scan_status` (keyword): Status of the scan (safe, unsafe, pending, in_progress, failed)
- `vulnerabilities` (nested): Array of vulnerability findings with CVE details
- `risk_score` (float): Overall risk score (0-1 scale)
- `total_vulnerabilities` (integer): Total count of vulnerabilities found
- `*_count` (integer): Count by severity level (critical_count, high_count, medium_count, low_count)
- `scan_timestamp` (date): When the scan was executed
- `scan_metadata` (object): Additional metadata about the scan (scanner version, duration, etc.)

**Note:** The counts (`total_vulnerabilities`, `critical_count`, `high_count`, `medium_count`, `low_count`) are automatically calculated from the `vulnerabilities` array.

---

#### 6. **mcp-federation-config** - Federation Settings

Stores federation configuration for integrating with external MCP server registries (Anthropic, ASOR).

**Index Name Pattern:** `mcp-federation-config-{namespace}`
**Schema Location:** Dynamically created via repository (no static schema file)

**Document Structure:**

```json
{
  "config_id": "federation-config",
  "anthropic": {
    "enabled": true,
    "endpoint": "https://registry.modelcontextprotocol.io",
    "sync_on_startup": true,
    "servers": [
      {
        "name": "weather-service"
      },
      {
        "name": "news-aggregator"
      }
    ]
  },
  "asor": {
    "enabled": false,
    "endpoint": "https://asor-registry.example.com",
    "auth_env_var": "ASOR_AUTH_TOKEN",
    "sync_on_startup": false,
    "agents": [
      {
        "id": "agent-001"
      }
    ]
  },
  "updated_at": "2024-12-20T12:00:00Z"
}
```

**Key Fields:**
- `config_id` (keyword): Always "federation-config" - single document per namespace
- `anthropic` (object): Anthropic registry federation settings
  - `enabled` (boolean): Enable/disable federation
  - `endpoint` (keyword): Registry endpoint URL
  - `sync_on_startup` (boolean): Automatically sync on application startup
  - `servers` (array): List of server names to federate
- `asor` (object): ASOR registry federation settings (same structure for agents)
- `updated_at` (date): Last configuration update timestamp

---

## Hybrid Search Pipeline

### Configuration

The registry implements a hybrid search strategy combining:
- **BM25 (Lexical Search):** 40% weight - Traditional full-text matching
- **k-NN (Vector Search):** 60% weight - Semantic similarity search

**Pipeline File:** [`scripts/opensearch-schemas/hybrid-search-pipeline.json`](../scripts/opensearch-schemas/hybrid-search-pipeline.json)

### How It Works

1. **BM25 Scoring:** Full-text search scores documents based on term frequency and inverse document frequency
2. **k-NN Scoring:** Vector similarity search scores documents based on cosine similarity to the query embedding
3. **Normalization:** Both scores are normalized to 0-1 range using min-max normalization
4. **Combination:** Weighted average combines the scores:
   ```
   Final Score = 0.4 × BM25_Score + 0.6 × k-NN_Score
   ```

This approach ensures:
- Exact keyword matches are found reliably (BM25)
- Semantically similar content is discovered (k-NN)
- Results balance precision and recall

### Implementation

When executing a hybrid search query, OpenSearch:
1. Executes BM25 query on text fields (`description`, `name`, `text_for_embedding`)
2. Executes k-NN query on the `embedding` field
3. Normalizes and combines scores using the `hybrid-search-pipeline`
4. Returns results ranked by combined score

---

## Configuration

### Key Settings

Configuration is managed via environment variables in `/registry/core/config.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `storage_backend` | `file` | Backend selection: `file` or `opensearch` |
| `opensearch_host` | `localhost` | OpenSearch host address |
| `opensearch_port` | `9200` | OpenSearch port |
| `opensearch_user` | `None` | Optional basic auth username |
| `opensearch_password` | `None` | Optional basic auth password |
| `opensearch_use_ssl` | `false` | Enable SSL/TLS connections |
| `opensearch_verify_certs` | `false` | Verify SSL certificates |
| `opensearch_namespace` | `default` | Namespace for index names (multi-tenancy) |
| `opensearch_hybrid_bm25_weight` | `0.4` | BM25 weight in hybrid search |
| `opensearch_hybrid_knn_weight` | `0.6` | k-NN weight in hybrid search |
| `embeddings_model_name` | `all-MiniLM-L6-v2` | Sentence transformer model |
| `embeddings_model_dimensions` | `384` | Embedding vector dimensions |
| `embeddings_provider` | `sentence-transformers` | Provider: `sentence-transformers` or `litellm` |

### Namespace Support

Namespaces enable multi-tenancy by suffixing index names:

```
Base Index Name + "-" + Namespace = Final Index Name

Examples:
  - mcp-servers-default
  - mcp-servers-tenant-a
  - mcp-servers-production
```

All six indexes use the same namespace suffix. This allows:
- Multiple isolated deployments in single OpenSearch cluster
- Logical separation of production and staging data
- Per-tenant data isolation

### Connection Settings

**For Local Development:**
```bash
export OPENSEARCH_HOST=localhost
export OPENSEARCH_PORT=9200
export OPENSEARCH_USE_SSL=false
```

**For Production with Authentication:**
```bash
export OPENSEARCH_HOST=opensearch.example.com
export OPENSEARCH_PORT=9200
export OPENSEARCH_USER=registry-user
export OPENSEARCH_PASSWORD=secure-password
export OPENSEARCH_USE_SSL=true
export OPENSEARCH_VERIFY_CERTS=true
export OPENSEARCH_NAMESPACE=production
```

---

## Initialization

### Initial Setup

Initialize OpenSearch indexes and pipelines using the provided script:

```bash
# Basic initialization (uses 'default' namespace)
uv run python scripts/init-opensearch.py

# Specify custom namespace
uv run python scripts/init-opensearch.py --namespace tenant-a

# Recreate indexes if they exist (destructive)
uv run python scripts/init-opensearch.py --recreate

# Custom host and port
uv run python scripts/init-opensearch.py --host opensearch.example.com --port 9200
```

### What the Script Does

1. **Connects** to OpenSearch with provided credentials
2. **Creates** the six base indexes with namespace suffix:
   - `mcp-servers-{namespace}`
   - `mcp-agents-{namespace}`
   - `mcp-scopes-{namespace}`
   - `mcp-embeddings-{namespace}`
   - `mcp-security-scans-{namespace}`
   - `mcp-federation-config-{namespace}`
3. **Applies** schema mappings from `scripts/opensearch-schemas/` files
4. **Creates** the hybrid search pipeline (shared across all namespaces)
5. **Logs** completion status

### Namespace Management

Each namespace maintains separate indexes:

```bash
# Create separate namespaces for multi-tenancy
uv run python scripts/init-opensearch.py --namespace production
uv run python scripts/init-opensearch.py --namespace staging
uv run python scripts/init-opensearch.py --namespace testing
```

Runtime configuration selects the active namespace:
```bash
export OPENSEARCH_NAMESPACE=production
# Registry will use production-suffixed indexes
```

### Index Mapping Details

Each index is created with:
- **Shards:** 1 (adjust for production clusters)
- **Replicas:** 1 (adjust for high availability)
- **Settings:** Index-specific optimizations (e.g., KNN parameters for embeddings)
- **Mappings:** Field types and analysis configurations

For production deployments, adjust shard and replica counts:

```python
# Modify in scripts/opensearch-schemas/{index-name}.json
"settings": {
    "number_of_shards": 5,      # Increase for larger clusters
    "number_of_replicas": 2,    # Increase for HA
    "index": {
        "knn": true,
        "knn.algo_param.ef_search": 100
    }
}
```

---

## Repository Layer

All database operations go through repository interfaces defined in [`registry/repositories/interfaces.py`](../registry/repositories/interfaces.py):

- **ServerRepository:** Server CRUD operations
- **AgentRepository:** Agent card CRUD operations
- **ScopeRepository:** Authorization scope management
- **SecurityScanRepository:** Vulnerability scan storage
- **FederationConfigRepository:** Federation configuration storage
- **SearchRepository:** Hybrid search operations

The repository factory automatically selects the correct implementation (File or OpenSearch) based on the configured backend.

---

## Migration from File Backend to OpenSearch

To migrate from the file-based backend:

1. **Initialize OpenSearch indexes:**
   ```bash
   uv run python scripts/init-opensearch.py --namespace production
   ```

2. **Update configuration:**
   ```bash
   export STORAGE_BACKEND=opensearch
   export OPENSEARCH_HOST=your-opensearch-host
   export OPENSEARCH_NAMESPACE=production
   ```

3. **Migrate existing data:**
   - Load from file backend using existing file repository
   - Index documents into OpenSearch using repository operations
   - Verify data integrity

4. **Switch to OpenSearch:**
   - Update `STORAGE_BACKEND=opensearch` in environment
   - Restart the application
   - Monitor for any issues

---

## Performance Considerations

### Indexing
- Bulk operations recommended for large data sets
- Embeddings are computed at index time (can be slow)
- Consider increasing OpenSearch heap for large indexes

### Search
- BM25 search is fast and scales well
- k-NN search with HNSW algorithm efficiently handles high-dimensional vectors
- Hybrid search balances latency and quality

### Scaling
- Increase `number_of_shards` for horizontal scalability
- Use multiple namespaces to isolate tenants
- Monitor OpenSearch resource usage (CPU, memory, disk)

---

## See Also

- [Configuration Guide](./configuration.md)
- [API Documentation](./api.md)
- [OpenSearch Documentation](https://opensearch.org/docs/)
