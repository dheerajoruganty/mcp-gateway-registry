# Database Abstraction Layer Design

**Status:** Current Implementation
**Last Updated:** December 26, 2024
**Target Audience:** Senior/Staff Engineers, Architecture Review

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Design Patterns](#design-patterns)
3. [Abstract Base Classes](#abstract-base-classes)
4. [Implementations](#implementations)
5. [Factory Pattern](#factory-pattern)
6. [Design Rationale](#design-rationale)
7. [Code Organization](#code-organization)
8. [Migration Strategy](#migration-strategy)

## Architecture Overview

The MCP Gateway Registry implements a **repository pattern with abstract base classes** to provide a clean separation between business logic and data storage. This design enables seamless switching between file-based storage (legacy, backwards compatible) and OpenSearch (recommended, production-ready) without modifying application code.

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       Application Layer                          │
│  (Services, API Endpoints, Business Logic)                      │
└────────────────────┬────────────────────────────────────────────┘
                     │ depends on
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              Repository Factory Layer                            │
│  get_server_repository()                                        │
│  get_agent_repository()                                         │
│  get_scope_repository()                                         │
│  get_security_scan_repository()                                 │
│  get_search_repository()                                        │
│  get_federation_config_repository()                             │
└────────┬──────────────────────────────┬────────────────────────┘
         │                              │
         │ creates (based on           │ creates (based on
         │ STORAGE_BACKEND)             │ STORAGE_BACKEND)
         ▼                              ▼
┌──────────────────────┐      ┌──────────────────────────┐
│ File-Based Impl      │      │ OpenSearch Impl          │
├──────────────────────┤      ├──────────────────────────┤
│ FileServerRepo       │      │ OpenSearchServerRepo     │
│ FileAgentRepo        │      │ OpenSearchAgentRepo      │
│ FileScopeRepo        │      │ OpenSearchScopeRepo      │
│ FileSecurityScanRepo │      │ OpenSearchSecurityRepo   │
│ FaissSearchRepo      │      │ OpenSearchSearchRepo     │
│ FileFederationRepo   │      │ OpenSearchFederationRepo │
└──────────┬───────────┘      └──────────┬───────────────┘
           │                             │
           ▼                             ▼
    Local File System              OpenSearch Cluster
    (JSON files, FAISS)            (Indexes, Mappings)
```

### Key Principles

1. **Abstraction**: All repositories implement abstract base classes defining strict contracts
2. **Polymorphism**: Multiple storage backend implementations (file, OpenSearch)
3. **Dependency Injection**: Factory pattern provides single point of repository creation
4. **Consistency**: All implementations provide identical behavior regardless of backend
5. **Testability**: Mock implementations easy to create; reset_repositories() enables test isolation

## Design Patterns

### Repository Pattern

The repository pattern provides a **data access abstraction** layer that:

- Isolates business logic from storage implementation details
- Defines clear, intent-driven interfaces (e.g., `get()`, `create()`, `update()`, `delete()`)
- Makes switching storage backends transparent to consuming code
- Enables comprehensive testing without actual storage dependencies

### Factory Pattern

The factory pattern manages **repository instantiation** by:

- Creating repositories lazily on first access (singleton pattern)
- Selecting implementation based on environment configuration (`STORAGE_BACKEND` setting)
- Centralizing backend selection logic in one place (`factory.py`)
- Providing `reset_repositories()` for test isolation

### Strategy Pattern

Different storage backends are **strategies** implementing the same interface:

- **File Strategy**: YAML/JSON files + FAISS for search
- **OpenSearch Strategy**: Distributed search index with hybrid search (BM25 + k-NN)

## Abstract Base Classes

All repository implementations inherit from abstract base classes defined in [`registry/repositories/interfaces.py`](../../registry/repositories/interfaces.py). These define the contract that ALL implementations must follow.

### ServerRepositoryBase

**Location:** [`registry/repositories/interfaces.py` (lines 14-76)](../../registry/repositories/interfaces.py#L14-L76)

**Purpose:** Data access for MCP server definitions and lifecycle management

**Key Methods:**

```python
# Lifecycle operations
async def get(path: str) -> Optional[Dict[str, Any]]
async def list_all() -> Dict[str, Dict[str, Any]]
async def create(server_info: Dict[str, Any]) -> bool
async def update(path: str, server_info: Dict[str, Any]) -> bool
async def delete(path: str) -> bool

# State management (enabled/disabled)
async def get_state(path: str) -> bool
async def set_state(path: str, enabled: bool) -> bool

# Lifecycle
async def load_all() -> None  # Load/reload from storage at startup
```

**Implementations:**
- [`registry/repositories/file/server_repository.py`](../../registry/repositories/file/server_repository.py) - File-based
- [`registry/repositories/opensearch/server_repository.py`](../../registry/repositories/opensearch/server_repository.py) - OpenSearch

---

### AgentRepositoryBase

**Location:** [`registry/repositories/interfaces.py` (lines 78-140)](../../registry/repositories/interfaces.py#L78-L140)

**Purpose:** Data access for A2A (Agent-to-Agent) agent definitions

**Key Methods:**

```python
async def get(path: str) -> Optional[AgentCard]
async def list_all() -> List[AgentCard]
async def create(agent: AgentCard) -> AgentCard
async def update(path: str, updates: Dict[str, Any]) -> AgentCard
async def delete(path: str) -> bool

async def get_state(path: str) -> bool
async def set_state(path: str, enabled: bool) -> bool

async def load_all() -> None  # Load/reload from storage
```

**Implementations:**
- [`registry/repositories/file/agent_repository.py`](../../registry/repositories/file/agent_repository.py) - File-based
- [`registry/repositories/opensearch/agent_repository.py`](../../registry/repositories/opensearch/agent_repository.py) - OpenSearch

---

### ScopeRepositoryBase

**Location:** [`registry/repositories/interfaces.py` (lines 142-506)](../../registry/repositories/interfaces.py#L142-L506)

**Purpose:** Data access for authorization scopes (RBAC - Role-Based Access Control)

**Overview:**

The Scope Repository manages a complex authorization model with three primary data structures:

1. **UI-Scopes** - Permissions for UI features grouped by Keycloak group
2. **Server Scopes** - Server access rules (which servers, methods, tools)
3. **Group Mappings** - Mapping between Keycloak groups and scopes

**Key Methods:**

```python
# UI permission queries
async def get_ui_scopes(group_name: str) -> Dict[str, Any]
async def get_group_mappings(keycloak_group: str) -> List[str]

# Server access rules
async def get_server_scopes(scope_name: str) -> List[Dict[str, Any]]

# Group management
async def get_group(group_name: str) -> Dict[str, Any]
async def list_groups() -> Dict[str, Any]
async def group_exists(group_name: str) -> bool
async def create_group(group_name: str, description: str = "") -> bool
async def delete_group(group_name: str, remove_from_mappings: bool = True) -> bool

# Server scope assignment
async def add_server_scope(
    server_path: str,
    scope_name: str,
    methods: List[str],
    tools: Optional[List[str]] = None
) -> bool
async def remove_server_scope(server_path: str, scope_name: str) -> bool
async def remove_server_from_all_scopes(server_path: str) -> bool

# UI visibility management
async def add_server_to_ui_scopes(group_name: str, server_name: str) -> bool
async def remove_server_from_ui_scopes(group_name: str, server_name: str) -> bool

# Scope mapping management
async def add_group_mapping(group_name: str, scope_name: str) -> bool
async def remove_group_mapping(group_name: str, scope_name: str) -> bool
async def get_all_group_mappings() -> Dict[str, List[str]]

# Bulk operations
async def add_server_to_multiple_scopes(
    server_path: str,
    scope_names: List[str],
    methods: List[str],
    tools: List[str]
) -> bool

async def load_all() -> None  # Load/reload from storage
```

**Implementations:**
- [`registry/repositories/file/scope_repository.py`](../../registry/repositories/file/scope_repository.py) - File-based (YAML)
- [`registry/repositories/opensearch/scope_repository.py`](../../registry/repositories/opensearch/scope_repository.py) - OpenSearch

---

### SecurityScanRepositoryBase

**Location:** [`registry/repositories/interfaces.py` (lines 508-598)](../../registry/repositories/interfaces.py#L508-L598)

**Purpose:** Data access for security scanning results (both MCP servers and agents)

**Key Methods:**

```python
# CRUD operations
async def get(server_path: str) -> Optional[Dict[str, Any]]
async def list_all() -> List[Dict[str, Any]]
async def create(scan_result: Dict[str, Any]) -> bool

# Querying
async def get_latest(server_path: str) -> Optional[Dict[str, Any]]
async def query_by_status(status: str) -> List[Dict[str, Any]]

async def load_all() -> None  # Load/reload from storage
```

**Implementations:**
- [`registry/repositories/file/security_scan_repository.py`](../../registry/repositories/file/security_scan_repository.py) - File-based
- [`registry/repositories/opensearch/security_scan_repository.py`](../../registry/repositories/opensearch/security_scan_repository.py) - OpenSearch

---

### SearchRepositoryBase

**Location:** [`registry/repositories/interfaces.py` (lines 600-645)](../../registry/repositories/interfaces.py#L600-L645)

**Purpose:** Data access for semantic/hybrid search functionality

**Key Methods:**

```python
async def initialize() -> None  # Initialize search service

# Indexing
async def index_server(
    path: str,
    server_info: Dict[str, Any],
    is_enabled: bool = False
) -> None

async def index_agent(
    path: str,
    agent_card: AgentCard,
    is_enabled: bool = False
) -> None

# Query
async def search(
    query: str,
    entity_types: Optional[List[str]] = None,
    max_results: int = 10
) -> Dict[str, List[Dict[str, Any]]]

async def remove_entity(path: str) -> None
```

**Implementations:**
- [`registry/repositories/file/search_repository.py`](../../registry/repositories/file/search_repository.py) - FAISS (Facebook AI Similarity Search)
- [`registry/repositories/opensearch/search_repository.py`](../../registry/repositories/opensearch/search_repository.py) - OpenSearch Hybrid Search (BM25 + k-NN)

---

### FederationConfigRepositoryBase

**Location:** [`registry/repositories/interfaces.py` (lines 647-709)](../../registry/repositories/interfaces.py#L647-L709)

**Purpose:** Data access for federation configuration (multi-registry federation)

**Key Methods:**

```python
# CRUD operations
async def get_config(config_id: str = "default") -> Optional[FederationConfig]
async def save_config(
    config: FederationConfig,
    config_id: str = "default"
) -> FederationConfig

async def delete_config(config_id: str = "default") -> bool
async def list_configs() -> List[Dict[str, Any]]
```

**Implementations:**
- [`registry/repositories/file/federation_config_repository.py`](../../registry/repositories/file/federation_config_repository.py) - File-based (JSON)
- [`registry/repositories/opensearch/federation_config_repository.py`](../../registry/repositories/opensearch/federation_config_repository.py) - OpenSearch

---

## Implementations

### File-Based Backend (Legacy, Backwards Compatible)

**Purpose:** Local file system storage for development, testing, and backwards compatibility

**Characteristics:**
- **Simplicity**: JSON/YAML files, no external dependencies (except FAISS for search)
- **Isolation**: No network calls required
- **State Management**: Separate state files for enabled/disabled status
- **Search**: FAISS (Facebook AI Similarity Search) for vector similarity

**Storage Structure:**
```
registry/
├── servers/
│   ├── server1.json
│   ├── server2.json
│   └── server_state.json          # Persistence for enabled/disabled state
├── agents/
│   ├── agent1_agent.json
│   ├── agent2_agent.json
│   └── agent_state.json
├── config/
│   ├── scopes.yml                 # Authorization scopes configuration
│   └── federation/
│       └── default.json           # Federation configuration
├── security_scans/
│   ├── scan_result_1.json
│   └── scan_result_2.json
├── models/
│   └── all-MiniLM-L6-v2/          # Embedding model weights
└── service_index.faiss            # FAISS vector index
```

**Implementation Classes:**
- [`FileServerRepository`](../../registry/repositories/file/server_repository.py)
- [`FileAgentRepository`](../../registry/repositories/file/agent_repository.py)
- [`FileScopeRepository`](../../registry/repositories/file/scope_repository.py)
- [`FileSecurityScanRepository`](../../registry/repositories/file/security_scan_repository.py)
- [`FaissSearchRepository`](../../registry/repositories/file/search_repository.py)
- [`FileFederationConfigRepository`](../../registry/repositories/file/federation_config_repository.py)

**Advantages:**
- No infrastructure setup needed
- Good for development and testing
- Human-readable file formats
- Git-friendly for version control

**Limitations:**
- Single-node only (no distributed deployment)
- Limited query capabilities
- File locking issues in concurrent scenarios
- Not suitable for production at scale
- FAISS requires model file storage

---

### OpenSearch Backend (Recommended for Production)

**Purpose:** Distributed search and storage backend for production deployments

**Characteristics:**
- **Scalability**: Clustered deployment for high availability
- **Query Capabilities**: Rich query DSL, complex filtering, aggregations
- **Hybrid Search**: Combines BM25 (full-text) + k-NN (semantic) search
- **Index Management**: Automatic index creation with proper mappings
- **Async Support**: Full async/await implementation for non-blocking I/O

**Index Structure:**
```
OpenSearch Cluster
├── mcp-servers-{namespace}         # Server definitions
├── mcp-agents-{namespace}          # Agent definitions
├── mcp-scopes-{namespace}          # Authorization scopes
├── mcp-security-scans-{namespace}  # Security scan results
├── mcp-embeddings-{namespace}      # Vector embeddings
└── mcp-federation-config-{namespace} # Federation configurations
```

**Implementation Classes:**
- [`OpenSearchServerRepository`](../../registry/repositories/opensearch/server_repository.py)
- [`OpenSearchAgentRepository`](../../registry/repositories/opensearch/agent_repository.py)
- [`OpenSearchScopeRepository`](../../registry/repositories/opensearch/scope_repository.py)
- [`OpenSearchSecurityScanRepository`](../../registry/repositories/opensearch/security_scan_repository.py)
- [`OpenSearchSearchRepository`](../../registry/repositories/opensearch/search_repository.py)
- [`OpenSearchFederationConfigRepository`](../../registry/repositories/opensearch/federation_config_repository.py)

**OpenSearch Client:** [`registry/repositories/opensearch/client.py`](../../registry/repositories/opensearch/client.py)

Provides:
- Async OpenSearch client singleton
- Connection pooling and authentication
- Index name management with namespace support
- Client lifecycle management (initialization and cleanup)

**Advantages:**
- Distributed, highly available
- Rich query capabilities
- Hybrid search (BM25 + k-NN) for semantic understanding
- Native vector support for embeddings
- Scales to millions of documents
- Production-ready

**Limitations:**
- Requires separate OpenSearch infrastructure
- Higher operational complexity
- More network I/O
- Requires proper index tuning for performance

**Hybrid Search Explanation:**

OpenSearch's hybrid search combines two approaches:

1. **BM25 (Best Matching 25)**: Full-text relevance scoring based on term frequency
   - Good for exact keyword matches
   - Fast and traditional IR approach
   - Default web search behavior

2. **k-NN (k-Nearest Neighbors)**: Vector similarity search
   - Semantic understanding
   - Captures meaning, not just keywords
   - Uses neural embeddings (sentence-transformers or Bedrock Titan)

**Default Weighting:**
```python
opensearch_hybrid_bm25_weight: float = 0.4
opensearch_hybrid_knn_weight: float = 0.6
```

This gives 60% weight to semantic search (vector similarity) and 40% to keyword matching, optimized for finding semantically relevant servers/agents.

---

## Factory Pattern

### Factory Implementation

**Location:** [`registry/repositories/factory.py`](../../registry/repositories/factory.py)

The factory provides singleton repository instances with lazy initialization:

```python
def get_server_repository() -> ServerRepositoryBase:
    """Get server repository singleton."""
    global _server_repo

    if _server_repo is not None:
        return _server_repo

    backend = settings.storage_backend
    logger.info(f"Creating server repository with backend: {backend}")

    if backend == "opensearch":
        from .opensearch.server_repository import OpenSearchServerRepository
        _server_repo = OpenSearchServerRepository()
    else:
        from .file.server_repository import FileServerRepository
        _server_repo = FileServerRepository()

    return _server_repo
```

**Similar factory functions exist for:**
- `get_agent_repository()`
- `get_scope_repository()`
- `get_security_scan_repository()`
- `get_search_repository()`
- `get_federation_config_repository()`

### Backend Selection Logic

Backend selection is controlled by the `storage_backend` setting in [`registry/core/config.py`](../../registry/core/config.py):

```python
storage_backend: str = "file"  # Options: "file", "opensearch"
```

**How it works:**

1. **At startup**: Application reads `STORAGE_BACKEND` environment variable (or defaults to "file")
2. **On first access**: Factory function checks backend setting
3. **Instance creation**: Creates appropriate implementation (file vs OpenSearch)
4. **Caching**: Returns cached singleton on subsequent calls

### Dependency Injection Pattern

Services consume repositories through factory functions:

```python
# In any service module
from registry.repositories.factory import get_server_repository

async def list_servers():
    repo = get_server_repository()  # Gets file or OpenSearch impl
    servers = await repo.list_all()
    return servers
```

**Benefits:**
- No hardcoded dependencies
- Easy to swap implementations
- Test isolation via `reset_repositories()`

### Test Isolation

For testing, repositories can be reset:

```python
from registry.repositories.factory import reset_repositories

async def test_server_creation():
    reset_repositories()  # Clear all singletons
    # Now fresh repositories are created
    repo = get_server_repository()
    # ... test code ...
```

---

## Design Rationale

### Why Repository Pattern?

The repository pattern addresses several critical concerns:

1. **Separation of Concerns**: Business logic doesn't know about storage details
   - Controllers/services call `repo.get()`, not filesystem or database directly
   - Easier to test services in isolation

2. **Multiple Storage Backends**: Single interface, multiple implementations
   - Same code works with file or OpenSearch backend
   - Switching backends requires only env var change
   - No code changes needed

3. **Consistency**: All implementations follow same contract
   - Same method signatures and behavior
   - Predictable error handling
   - Consistent data transformations

4. **Abstraction**: Storage complexity hidden behind simple interface
   - `repo.get(path)` is simple whether backed by files or OpenSearch
   - Consumers don't care about implementation details

### Benefits of Repository Abstraction

**For Development:**
- Develop with file backend (fast, no setup)
- Test with mocks (no I/O overhead)
- Easy to add new storage backends

**For Deployment:**
- Production uses OpenSearch (scalable)
- Backwards compatible with file storage
- Can migrate gradually

**For Testing:**
- Mock repositories easily
- Test services without actual storage
- Test data isolation via `reset_repositories()`

**For Maintenance:**
- Storage logic centralized in repository classes
- Changes to storage don't affect business logic
- Clear interfaces make code changes safer

### Interface Consistency

All repositories implement abstract base classes with:

```python
# All repos have these patterns
async def load_all() -> None          # Startup initialization
async def get(id: str) -> Optional    # Single entity retrieval
async def list_all() -> List/Dict     # Bulk retrieval
async def create(entity) -> bool/Entity  # Create new entity
async def update(id, updates) -> bool/Entity  # Modify existing
async def delete(id) -> bool          # Remove entity
```

This consistent interface means:
- Easier onboarding for engineers
- Less mental overhead switching between repositories
- Standardized error handling

### Data Consistency Strategy

**File Backend:**
- Atomic file operations
- Separate state file for enabled/disabled status
- No transactions (file-by-file consistency)
- Best effort on concurrent writes

**OpenSearch Backend:**
- Document-level consistency
- Index operations with refresh flags
- No distributed transactions
- Eventual consistency model
- Suitable for high concurrency

---

## Code Organization

### Directory Structure

```
registry/repositories/
├── __init__.py                          # Package initialization
├── interfaces.py                        # Abstract base classes (6 repos)
├── factory.py                           # Repository factory
│
├── file/                                # File-based implementations
│   ├── __init__.py
│   ├── server_repository.py
│   ├── agent_repository.py
│   ├── scope_repository.py
│   ├── security_scan_repository.py
│   ├── search_repository.py             # FAISS-based
│   └── federation_config_repository.py
│
└── opensearch/                          # OpenSearch implementations
    ├── __init__.py
    ├── client.py                        # OpenSearch client management
    ├── server_repository.py
    ├── agent_repository.py
    ├── scope_repository.py
    ├── security_scan_repository.py
    ├── search_repository.py             # Hybrid search (BM25 + k-NN)
    └── federation_config_repository.py
```

### Naming Conventions

**Abstract Base Classes** (in `interfaces.py`):
- `ServerRepositoryBase`
- `AgentRepositoryBase`
- `ScopeRepositoryBase`
- `SecurityScanRepositoryBase`
- `SearchRepositoryBase`
- `FederationConfigRepositoryBase`

**File Implementations** (in `file/`):
- `FileServerRepository`
- `FileAgentRepository`
- `FileScopeRepository`
- `FileSecurityScanRepository`
- `FaissSearchRepository` (special: uses FAISS, not files)
- `FileFederationConfigRepository`

**OpenSearch Implementations** (in `opensearch/`):
- `OpenSearchServerRepository`
- `OpenSearchAgentRepository`
- `OpenSearchScopeRepository`
- `OpenSearchSecurityScanRepository`
- `OpenSearchSearchRepository`
- `OpenSearchFederationConfigRepository`

### Configuration

Backend selection and OpenSearch settings in [`registry/core/config.py`](../../registry/core/config.py):

```python
# Backend selection
storage_backend: str = "file"  # "file" or "opensearch"

# OpenSearch connection
opensearch_host: str = "localhost"
opensearch_port: int = 9200
opensearch_user: Optional[str] = None
opensearch_password: Optional[str] = None
opensearch_use_ssl: bool = False
opensearch_verify_certs: bool = False

# Multi-tenancy support
opensearch_namespace: str = "default"

# Index names (with namespace suffix)
opensearch_index_servers: str = "mcp-servers"
opensearch_index_agents: str = "mcp-agents"
opensearch_index_scopes: str = "mcp-scopes"
opensearch_index_embeddings: str = "mcp-embeddings"
opensearch_index_security_scans: str = "mcp-security-scans"
opensearch_index_federation_config: str = "mcp-federation-config"

# Hybrid search weights
opensearch_hybrid_bm25_weight: float = 0.4
opensearch_hybrid_knn_weight: float = 0.6
```

---

## Migration Strategy

### From File to OpenSearch

The repository pattern enables **zero-downtime migration** from file-based to OpenSearch backend:

#### Phase 1: Parallel Writes (Optional)
Create a "dual-write" repository wrapper that writes to both backends:

```python
class DualWriteRepository:
    """Dual-write wrapper for gradual migration."""

    def __init__(self, file_repo, opensearch_repo):
        self.file_repo = file_repo
        self.opensearch_repo = opensearch_repo

    async def create(self, entity):
        # Write to both backends
        await self.file_repo.create(entity)
        await self.opensearch_repo.create(entity)
```

**Benefits:**
- Builds OpenSearch index while keeping file system as fallback
- Can verify data consistency between backends
- Easy rollback if issues arise

#### Phase 2: Migration
1. Set up OpenSearch cluster
2. Enable dual-write mode
3. Bulk load existing data into OpenSearch
4. Verify data integrity
5. Switch `STORAGE_BACKEND` to "opensearch"
6. Disable dual-write mode
7. Keep file backup for X days before cleanup

#### Phase 3: File System Cleanup
After successful OpenSearch operation:
- Archive or delete file-based storage
- Decommission FAISS indexes
- Document migration for future reference

### Backwards Compatibility

File-based backend is maintained for:
- Development environments
- Testing (no external dependencies)
- Backwards compatibility
- Emergency fallback

The factory pattern ensures no code changes needed when switching backends.

---

## Advanced Topics

### Namespace Support (Multi-Tenancy)

OpenSearch implementation supports multi-tenancy via namespaces:

```python
# In config.py
opensearch_namespace: str = "default"

# Index names are automatically namespaced
# mcp-servers-{namespace}
# mcp-agents-{namespace}
# etc.
```

**Use Cases:**
- Multiple registry instances on shared OpenSearch cluster
- Isolated test environments
- Customer separation in SaaS deployments

**Implementation:** [`registry/repositories/opensearch/client.py`](../../registry/repositories/opensearch/client.py)

```python
def get_index_name(base_name: str) -> str:
    """Get full index name with namespace."""
    return f"{base_name}-{settings.opensearch_namespace}"
```

### Error Handling

Both implementations handle errors gracefully:

**File Backend:**
- Missing files → return None or empty list
- Parse errors → log and skip
- I/O errors → raised to caller

**OpenSearch Backend:**
- Connection errors → log and attempt retry
- Index not found → initialize index
- Query errors → log and raise

### Performance Considerations

**File Backend:**
- Fast for small datasets (<1000 entities)
- No network latency
- FAISS search: O(n) linear scan (not scalable)
- Not suitable for high concurrency

**OpenSearch Backend:**
- Scalable to millions of entities
- Network latency (typically <100ms)
- BM25 + k-NN: O(log n) with proper indexing
- Built for high concurrency (lock-free reads)

**Recommendations:**
- Use file backend for development only
- Use OpenSearch for production
- Monitor OpenSearch query latency
- Tune index refresh intervals for throughput vs. latency tradeoff

---

## Testing Strategy

### Unit Tests

Mock repositories for unit testing:

```python
class MockServerRepository(ServerRepositoryBase):
    """Mock implementation for testing."""

    def __init__(self):
        self.servers = {}

    async def get(self, path: str) -> Optional[Dict]:
        return self.servers.get(path)

    async def list_all(self) -> Dict:
        return self.servers.copy()

    # ... implement other methods ...
```

### Integration Tests

Use file backend for integration tests:

```python
@pytest.fixture
def reset_repos():
    """Reset repositories between tests."""
    yield
    reset_repositories()

async def test_server_lifecycle(reset_repos):
    repo = get_server_repository()

    # File backend used by default
    server = {"path": "/test", "name": "test_server"}
    await repo.create(server)

    result = await repo.get("/test")
    assert result is not None
```

### End-to-End Tests

Test against OpenSearch in Docker:

```yaml
# docker-compose.yml
services:
  opensearch:
    image: opensearchproject/opensearch:2.x
    environment:
      OPENSEARCH_JAVA_OPTS: "-Xms512m -Xmx512m"
      DISABLE_SECURITY_PLUGIN: "true"
```

Set `STORAGE_BACKEND=opensearch` and run full integration tests.

---

## Summary

The database abstraction layer provides a **clean, extensible architecture** for data storage in the MCP Gateway Registry:

| Aspect | File | OpenSearch |
|--------|------|-----------|
| **Use Case** | Development, testing | Production |
| **Scalability** | ~1000 entities | Millions |
| **Dependencies** | None (+ FAISS) | OpenSearch cluster |
| **Query Power** | Basic | Advanced (full DSL) |
| **Concurrency** | Limited | High |
| **Setup Complexity** | None | Moderate |
| **Cost** | Free | Infrastructure cost |

The **repository pattern** with factory ensures:
- Clean separation of concerns
- Easy backend switching
- Comprehensive testability
- Consistent interfaces
- Future extensibility

All implementations maintain **identical behavior**, making backend selection purely an operational decision rather than a code architecture choice.

