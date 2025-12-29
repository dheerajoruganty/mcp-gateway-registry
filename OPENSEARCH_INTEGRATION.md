# OpenSearch Integration

## Overview

The MCP Gateway Registry implements a **repository pattern** to support multiple storage backends. This enables seamless switching between file-based storage (JSON files) and OpenSearch without changing application code.

**Key Features:**
- Repository abstraction layer with clean interfaces
- File backend (default) - backward compatible with existing deployments
- OpenSearch backend - scalable, distributed storage with hybrid search
- Configuration-based backend switching via environment variables
- Hybrid search combining BM25 (keyword) and k-NN (vector/semantic) search
- Multi-tenancy support via namespace isolation
- Production-ready AWS ECS deployment with Terraform

## Architecture

### Layer Separation

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                        │
│  Files: registry/api/*.py, auth_server/*.py                │
│  Imports: Services only                                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER                            │
│  Files: registry/services/*.py                              │
│  Imports: Repository interfaces via factory                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    REPOSITORY FACTORY                       │
│  File: registry/repositories/factory.py                     │
│  Returns: File or OpenSearch implementation based on config │
└─────────────────────────────────────────────────────────────┘
                ↓                           ↓
┌───────────────────────────┐   ┌───────────────────────────┐
│   FILE REPOSITORIES       │   │  OPENSEARCH REPOSITORIES  │
│   registry/repositories/  │   │  registry/repositories/   │
│   file/                   │   │  opensearch/              │
│   - JSON files            │   │  - OpenSearch cluster     │
│   - FAISS index           │   │  - Hybrid search          │
└───────────────────────────┘   └───────────────────────────┘
```

### Repository Interfaces

Three base classes define the contract for all storage backends:

1. **ServerRepositoryBase** - MCP server CRUD operations
2. **AgentRepositoryBase** - Agent CRUD operations  
3. **SearchRepositoryBase** - Search and indexing operations

## Implementation Details

### File Structure

```
registry/
├── repositories/
│   ├── interfaces.py              # Abstract base classes
│   ├── factory.py                 # Singleton factory pattern
│   ├── file/                      # File backend implementation
│   │   ├── server_repository.py  # JSON file operations for servers
│   │   ├── agent_repository.py   # JSON file operations for agents
│   │   └── search_repository.py  # FAISS wrapper
│   └── opensearch/                # OpenSearch backend implementation
│       ├── client.py              # OpenSearch client singleton
│       ├── server_repository.py  # Server operations in OpenSearch
│       ├── agent_repository.py   # Agent operations in OpenSearch
│       └── search_repository.py  # Hybrid search implementation
│
scripts/
├── opensearch-schemas/            # Index mappings and settings
│   ├── mcp-servers.json          # Server index schema
│   ├── mcp-agents.json           # Agent index schema
│   ├── mcp-scopes.json           # Scopes index schema
│   ├── mcp-embeddings.json       # Embeddings with k-NN vectors (384 dims)
│   └── hybrid-search-pipeline.json # Search pipeline configuration
└── init-opensearch.py            # Index initialization script
```

### OpenSearch Indices

| Index | Purpose | Key Fields |
|-------|---------|------------|
| `mcp-servers-{namespace}` | MCP server metadata | path, server_name, description, tools, resources |
| `mcp-agents-{namespace}` | Agent configurations | path, name, description, servers, enabled |
| `mcp-scopes-{namespace}` | OAuth scopes | scope_name, description, group_mappings |
| `mcp-embeddings-{namespace}` | Search embeddings | entity_id, entity_type, text, embedding (384-dim vector) |

### Hybrid Search

Combines two search strategies:

1. **BM25 (Keyword Search)** - Traditional full-text search with term frequency
2. **k-NN (Vector Search)** - Semantic similarity using sentence embeddings

**Configuration:**
- Embedding model: `all-MiniLM-L6-v2` (384 dimensions)
- Default weights: BM25 (0.4) + k-NN (0.6)
- Configurable via `OPENSEARCH_HYBRID_BM25_WEIGHT` and `OPENSEARCH_HYBRID_KNN_WEIGHT`

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_BACKEND` | `file` | Backend type: `file` or `opensearch` |
| `OPENSEARCH_HOST` | `localhost` | OpenSearch hostname |
| `OPENSEARCH_PORT` | `9200` | OpenSearch port |
| `OPENSEARCH_USER` | - | Basic auth username (optional) |
| `OPENSEARCH_PASSWORD` | - | Basic auth password (optional) |
| `OPENSEARCH_USE_SSL` | `false` | Enable HTTPS |
| `OPENSEARCH_VERIFY_CERTS` | `false` | Verify SSL certificates |
| `OPENSEARCH_NAMESPACE` | `default` | Index namespace for multi-tenancy |
| `OPENSEARCH_HYBRID_BM25_WEIGHT` | `0.4` | Keyword search weight (0-1) |
| `OPENSEARCH_HYBRID_KNN_WEIGHT` | `0.6` | Vector search weight (0-1) |

### Switching Backends

**File Backend (Default):**
```bash
export STORAGE_BACKEND=file
# Data stored in: registry/servers/*.json, registry/agents/*.json
```

**OpenSearch Backend:**
```bash
export STORAGE_BACKEND=opensearch
export OPENSEARCH_HOST=opensearch.mcp-gateway.local
export OPENSEARCH_PORT=9200
# Data stored in: OpenSearch indices
```

## Local Development

### 1. Start OpenSearch

```bash
# Start OpenSearch container
docker compose up opensearch -d

# Wait for healthy status (30-60 seconds)
docker compose ps | grep opensearch

# Verify connection
curl http://localhost:9200/_cluster/health
```

### 2. Initialize Indices

```bash
# Create all indices and search pipeline
uv run python scripts/init-opensearch.py

# Verify indices created
curl http://localhost:9200/_cat/indices?v
# Should show: mcp-servers-default, mcp-agents-default, mcp-scopes-default, mcp-embeddings-default
```

### 3. Test File Backend

```bash
# Use file backend (default)
export STORAGE_BACKEND=file
cd registry
uv run uvicorn main:app --reload

# Test API
curl http://localhost:7860/api/servers
```

### 4. Test OpenSearch Backend

```bash
# Switch to OpenSearch
export STORAGE_BACKEND=opensearch
export OPENSEARCH_HOST=localhost
export OPENSEARCH_PORT=9200

# Restart registry
cd registry
uv run uvicorn main:app --reload

# Test API (should work identically)
curl http://localhost:7860/api/servers

# Create test server
curl -X POST http://localhost:7860/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/test",
    "server_name": "Test Server",
    "description": "Testing OpenSearch backend"
  }'

# Verify in OpenSearch
curl http://localhost:9200/mcp-servers-default/_search?pretty
```

### 5. Test Search

```bash
# Index test data
curl -X POST http://localhost:7860/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/weather",
    "server_name": "Weather Server",
    "description": "Get current weather and forecasts"
  }'

# Search (hybrid BM25 + k-NN)
curl "http://localhost:7860/api/search?q=weather&top_k=5"
```

## AWS Deployment

### Infrastructure Components

The Terraform configuration deploys:

1. **OpenSearch ECS Service**
   - OpenSearch 2.11.0 on Fargate (1 vCPU, 2GB RAM)
   - EFS volume for persistent data storage
   - Service discovery: `opensearch.mcp-gateway.local:9200`
   - Security plugin disabled for testing (enable with SSL certs for production)

2. **Security Groups**
   - OpenSearch ingress from Registry and Auth Server on port 9200
   - OpenSearch egress to EFS on port 2049 (NFS)
   - EFS ingress from OpenSearch on port 2049

3. **EFS Configuration**
   - Access point: `/opensearch-data`
   - POSIX user: UID 1000, GID 1000
   - Permissions: 755

### Deployment Steps

```bash
cd terraform/aws-ecs

# 1. Configure variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# 2. Build and push images to ECR (avoid Docker Hub rate limits)
./build-and-push-all.sh

# 3. Deploy infrastructure
terraform init
terraform plan
terraform apply

# 4. Verify OpenSearch is healthy
aws ecs describe-services \
  --cluster mcp-gateway-cluster \
  --services opensearch \
  --query 'services[0].deployments[0].runningCount'
# Should return: 1

# 5. Initialize OpenSearch indices (from within VPC)
# Option A: ECS Exec into registry container
aws ecs execute-command \
  --cluster mcp-gateway-cluster \
  --task <task-id> \
  --container registry \
  --interactive \
  --command "/bin/bash"

# Then run:
python scripts/init-opensearch.py

# Option B: Use SageMaker notebook in same VPC
# Upload init-opensearch.py and run from notebook
```

### Registry Configuration for AWS

Update registry environment variables in `terraform/aws-ecs/ecs.tf`:

```hcl
environment = [
  { name = "STORAGE_BACKEND", value = "opensearch" },
  { name = "OPENSEARCH_HOST", value = "opensearch.mcp-gateway.local" },
  { name = "OPENSEARCH_PORT", value = "9200" },
  { name = "OPENSEARCH_NAMESPACE", value = "production" }
]
```

## Multi-Tenancy

Use namespaces to isolate data for different tenants:

```bash
# Tenant A
export OPENSEARCH_NAMESPACE=tenant-a
uv run python scripts/init-opensearch.py --namespace tenant-a
# Creates: mcp-servers-tenant-a, mcp-agents-tenant-a, etc.

# Tenant B
export OPENSEARCH_NAMESPACE=tenant-b
uv run python scripts/init-opensearch.py --namespace tenant-b
# Creates: mcp-servers-tenant-b, mcp-agents-tenant-b, etc.
```

Each tenant's data is completely isolated in separate indices.

## Testing

### Unit Tests

```bash
# Test repository implementations
cd registry
uv run pytest tests/unit/repositories/ -v
```

### Integration Tests

```bash
# Test with file backend
export STORAGE_BACKEND=file
uv run pytest tests/integration/ -v

# Test with OpenSearch backend
export STORAGE_BACKEND=opensearch
docker compose up opensearch -d
uv run python scripts/init-opensearch.py
uv run pytest tests/integration/ -v
```

### Manual Verification

## Troubleshooting

### OpenSearch won't start

```bash
# Check logs
docker compose logs opensearch

# Common fix: increase vm.max_map_count
sudo sysctl -w vm.max_map_count=262144

# Make permanent (Linux)
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Connection refused

```bash
# Verify OpenSearch is running
docker compose ps opensearch

# Check health
curl http://localhost:9200/_cluster/health

# Check from registry container
docker compose exec registry curl http://opensearch:9200/_cluster/health
```

### Indices not created

```bash
# Recreate indices
uv run python scripts/init-opensearch.py --recreate

# Verify
curl http://localhost:9200/_cat/indices?v
```

### EFS mount timeout (AWS)

Ensure security groups allow NFS traffic:
- OpenSearch security group: egress to EFS on port 2049
- EFS security group: ingress from OpenSearch on port 2049

### Search returns no results

```bash
# Check if embeddings are indexed
curl http://localhost:9200/mcp-embeddings-default/_count

# Rebuild search index
curl -X POST http://localhost:7860/api/search/rebuild
```

## Performance Considerations

- **In-Memory Cache**: Both file and OpenSearch repositories maintain in-memory caches
- **Refresh Policy**: `refresh=True` on writes for immediate consistency (adjust for high-write scenarios)
- **Batch Size**: Query size set to 10,000 documents (configurable)
- **Connection Pooling**: Singleton client reuses connections
- **Embedding Generation**: Cached per unique text to avoid redundant computation

## Security Best Practices

### Development
- Security plugin disabled (`DISABLE_SECURITY_PLUGIN=true`)
- No authentication required
- HTTP only (no SSL)

### Production
- Enable security plugin
- Configure SSL/TLS certificates
- Use AWS Secrets Manager for credentials
- Enable VPC endpoints for private connectivity
- Implement IAM-based authentication
- Enable audit logging
- Configure index lifecycle policies

## Migration

### File to OpenSearch

```python
# Example migration script
import asyncio
from registry.repositories.factory import get_server_repository
from registry.core.config import settings

async def migrate():
    # Read from file backend
    settings.storage_backend = "file"
    file_repo = get_server_repository()
    servers = await file_repo.get_all()
    
    # Write to OpenSearch backend
    settings.storage_backend = "opensearch"
    os_repo = get_server_repository()
    for path, server in servers.items():
        await os_repo.save(server)
    
    print(f"Migrated {len(servers)} servers")

asyncio.run(migrate())
```

### OpenSearch to File

```python
# Reverse migration
async def migrate_back():
    # Read from OpenSearch
    settings.storage_backend = "opensearch"
    os_repo = get_server_repository()
    servers = await os_repo.get_all()
    
    # Write to file backend
    settings.storage_backend = "file"
    file_repo = get_server_repository()
    for path, server in servers.items():
        await file_repo.save(server)
    
    print(f"Migrated {len(servers)} servers back to files")

asyncio.run(migrate_back())
```

## Monitoring

### Health Checks

```bash
# OpenSearch cluster health
curl http://localhost:9200/_cluster/health

# Index statistics
curl http://localhost:9200/_cat/indices?v

# Node statistics
curl http://localhost:9200/_nodes/stats?pretty
```

### Metrics

Key metrics to monitor:
- Cluster status (green/yellow/red)
- Index size and document count
- Search latency (p50, p95, p99)
- Indexing rate
- JVM heap usage
- Disk space

### CloudWatch (AWS)

OpenSearch ECS service logs to CloudWatch:
- Log group: `/ecs/opensearch`
- Metrics: CPU, memory, network
- Alarms: Service health, task failures

## References

- [OpenSearch Documentation](https://opensearch.org/docs/latest/)
- [OpenSearch Python Client](https://opensearch.org/docs/latest/clients/python/)
- [k-NN Plugin](https://opensearch.org/docs/latest/search-plugins/knn/)
- [Hybrid Search](https://opensearch.org/docs/latest/search-plugins/hybrid-search/)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)

## Support

For issues or questions:
1. Check logs: `docker compose logs opensearch` or CloudWatch
2. Verify configuration: Environment variables and index mappings
3. Test connectivity: `curl http://opensearch:9200/_cluster/health`
4. Review security groups (AWS): Ensure proper ingress/egress rules
5. Check EFS mount (AWS): Verify NFS traffic allowed on port 2049
