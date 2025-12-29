# Docker Build Variants

The MCP Gateway Registry supports two Docker build variants to optimize for different deployment scenarios.

## Build Variants

| Variant | Default | Use Case | Image Size |
|---------|---------|----------|------------|
| `lite` | Yes | Production with API embeddings (Bedrock, OpenAI) + OpenSearch | ~650MB |
| `full` | No | Development/offline with local ML models (PyTorch, FAISS) | ~2.5GB |

## Quick Reference

### Lite Variant (Recommended for Production)

Uses API-based embeddings and OpenSearch Serverless for vector search.

```bash
# Docker Compose
docker compose build registry

# Direct Docker build
docker build --build-arg VARIANT=lite -f docker/Dockerfile.registry .
```

**Required Environment:**
```env
STORAGE_BACKEND=opensearch
EMBEDDINGS_PROVIDER=litellm
EMBEDDINGS_MODEL_NAME=bedrock/amazon.titan-embed-text-v1
EMBEDDINGS_MODEL_DIMENSIONS=1024
```

### Full Variant (Local ML)

Includes PyTorch, FAISS, and sentence-transformers for offline operation.

```bash
# Docker Compose with environment variable
REGISTRY_VARIANT=full docker compose build registry

# Docker Compose with override file
docker compose -f docker-compose.yml -f docker-compose.full.yml build registry

# Direct Docker build
docker build --build-arg VARIANT=full -f docker/Dockerfile.registry .
```

**Required Environment:**
```env
STORAGE_BACKEND=file
EMBEDDINGS_PROVIDER=sentence-transformers
EMBEDDINGS_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDINGS_MODEL_DIMENSIONS=384
```

## Dependency Comparison

| Dependency | lite | full | Size Impact |
|------------|------|------|-------------|
| torch | No | Yes | ~500MB |
| sentence-transformers | No | Yes | ~200MB |
| faiss-cpu | No | Yes | ~50MB |
| scikit-learn | No | Yes | ~100MB |
| litellm | Yes | Yes | ~10MB |
| opensearch-py | Yes | Yes | ~5MB |

## MCP Server Variants

MCP servers also support variants:

| Server | Lite Image | Full Image | Notes |
|--------|------------|------------|-------|
| currenttime | ~90MB | N/A | Alpine-based, no ML needed |
| fininfo | ~110MB | N/A | Alpine-based, no ML needed |
| realserverfaketools | ~110MB | N/A | Alpine-based, no ML needed |
| mcpgw | N/A | ~2.1GB | Requires PyTorch for local embeddings |

```bash
# Lite servers use Alpine (target: runtime-lite)
docker compose build currenttime-server fininfo-server realserverfaketools-server

# Full server uses Debian slim (target: runtime-full)
docker compose build mcpgw-server
```

## ECS Deployment

Add to your `terraform.tfvars`:

```hcl
# Lite variant (recommended)
registry_variant         = "lite"
embeddings_provider      = "litellm"
embeddings_model_name    = "bedrock/amazon.titan-embed-text-v1"
embeddings_model_dimensions = 1024

# Or full variant
# registry_variant         = "full"
# embeddings_provider      = "sentence-transformers"
# embeddings_model_name    = "all-MiniLM-L6-v2"
# embeddings_model_dimensions = 384
```

The ECS module defaults to lite variant with OpenSearch Serverless and Bedrock embeddings.

## Helm Deployment

Add to your `values.yaml`:

```yaml
registry:
  app:
    variant: lite  # or "full"
    storageBackend: opensearch  # or "file" for full
    embeddings:
      provider: litellm  # or "sentence-transformers"
      modelName: bedrock/amazon.titan-embed-text-v1
      modelDimensions: 1024
```

## Troubleshooting

### Error: sentence-transformers not installed

You're using `EMBEDDINGS_PROVIDER=sentence-transformers` with a `lite` build.

**Fix:** Either rebuild with `VARIANT=full` or switch to API embeddings:
```env
EMBEDDINGS_PROVIDER=litellm
EMBEDDINGS_MODEL_NAME=bedrock/amazon.titan-embed-text-v1
```

### Error: FAISS search service is not initialized

You're using `STORAGE_BACKEND=file` with a `lite` build.

**Fix:** Either rebuild with `VARIANT=full` or switch to OpenSearch:
```env
STORAGE_BACKEND=opensearch
```

### Slow startup with full variant

The full variant downloads ML models on first startup (~90MB for MiniLM). This is normal.

**Tip:** Pre-warm containers or use a persistent volume for the model cache at `/app/registry/models`.
