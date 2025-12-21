#!/bin/bash
# Test script for Phase 2 OpenSearch implementation

set -e

echo "=========================================="
echo "Phase 2 OpenSearch Integration Test"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check if OpenSearch schemas exist
echo "Test 1: Checking OpenSearch schema files..."
SCHEMA_FILES=(
    "scripts/opensearch-schemas/mcp-servers.json"
    "scripts/opensearch-schemas/mcp-agents.json"
    "scripts/opensearch-schemas/mcp-scopes.json"
    "scripts/opensearch-schemas/mcp-embeddings.json"
    "scripts/opensearch-schemas/hybrid-search-pipeline.json"
)

for file in "${SCHEMA_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} Found: $file"
    else
        echo -e "${RED}✗${NC} Missing: $file"
        exit 1
    fi
done
echo ""

# Test 2: Check if init script exists and compiles
echo "Test 2: Checking init script..."
if [ -f "scripts/init-opensearch.py" ]; then
    echo -e "${GREEN}✓${NC} Found: scripts/init-opensearch.py"
    if uv run python -m py_compile scripts/init-opensearch.py 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Script compiles successfully"
    else
        echo -e "${RED}✗${NC} Script has syntax errors"
        exit 1
    fi
else
    echo -e "${RED}✗${NC} Missing: scripts/init-opensearch.py"
    exit 1
fi
echo ""

# Test 3: Check if OpenSearch repository files exist and compile
echo "Test 3: Checking OpenSearch repository files..."
REPO_FILES=(
    "registry/repositories/opensearch/client.py"
    "registry/repositories/opensearch/server_repository.py"
    "registry/repositories/opensearch/agent_repository.py"
    "registry/repositories/opensearch/search_repository.py"
)

for file in "${REPO_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} Found: $file"
        if uv run python -m py_compile "$file" 2>/dev/null; then
            echo -e "${GREEN}✓${NC} $file compiles successfully"
        else
            echo -e "${RED}✗${NC} $file has syntax errors"
            exit 1
        fi
    else
        echo -e "${RED}✗${NC} Missing: $file"
        exit 1
    fi
done
echo ""

# Test 4: Check docker-compose.yml for OpenSearch service
echo "Test 4: Checking docker-compose.yml..."
if grep -q "opensearch:" docker-compose.yml; then
    echo -e "${GREEN}✓${NC} OpenSearch service found in docker-compose.yml"
else
    echo -e "${RED}✗${NC} OpenSearch service not found in docker-compose.yml"
    exit 1
fi

if grep -q "opensearch-data:" docker-compose.yml; then
    echo -e "${GREEN}✓${NC} OpenSearch volume found in docker-compose.yml"
else
    echo -e "${RED}✗${NC} OpenSearch volume not found in docker-compose.yml"
    exit 1
fi
echo ""

# Test 5: Check if OpenSearch is running (optional)
echo "Test 5: Checking if OpenSearch is running..."
if curl -s http://localhost:9200/_cluster/health >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} OpenSearch is running and accessible"
    
    # Check cluster health
    HEALTH=$(curl -s http://localhost:9200/_cluster/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    if [ "$HEALTH" = "green" ] || [ "$HEALTH" = "yellow" ]; then
        echo -e "${GREEN}✓${NC} Cluster health: $HEALTH"
    else
        echo -e "${YELLOW}⚠${NC} Cluster health: $HEALTH (may need attention)"
    fi
else
    echo -e "${YELLOW}⚠${NC} OpenSearch is not running (start with: docker compose up opensearch -d)"
fi
echo ""

# Test 6: Check if indices exist (if OpenSearch is running)
if curl -s http://localhost:9200/_cluster/health >/dev/null 2>&1; then
    echo "Test 6: Checking OpenSearch indices..."
    INDICES=$(curl -s http://localhost:9200/_cat/indices?h=index | grep "mcp-" || true)
    if [ -n "$INDICES" ]; then
        echo -e "${GREEN}✓${NC} Found OpenSearch indices:"
        echo "$INDICES" | while read -r index; do
            echo "  - $index"
        done
    else
        echo -e "${YELLOW}⚠${NC} No indices found (run: uv run python scripts/init-opensearch.py)"
    fi
    echo ""
fi

echo "=========================================="
echo -e "${GREEN}Phase 2 Implementation Complete!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Start OpenSearch: docker compose up opensearch -d"
echo "2. Initialize indices: uv run python scripts/init-opensearch.py"
echo "3. Test with file backend: STORAGE_BACKEND=file docker compose up registry -d"
echo "4. Test with OpenSearch: STORAGE_BACKEND=opensearch docker compose restart registry"
echo ""
