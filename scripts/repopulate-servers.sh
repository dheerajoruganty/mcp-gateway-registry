#!/bin/bash

# Script to remove all servers and re-register them to populate embeddings index
# This ensures all servers get indexed in the OpenSearch embeddings index

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CLI_DIR="$REPO_ROOT/api"
EXAMPLES_DIR="$REPO_ROOT/cli/examples"

# Registry URL
REGISTRY_URL="${REGISTRY_URL:-http://localhost}"

# Token file
TOKEN_FILE="${TOKEN_FILE:-.oauth-tokens/ingress.json}"

echo -e "${YELLOW}=== MCP Gateway Registry Re-population Script ===${NC}"
echo ""

# Step 1: Get current list of servers
echo -e "${YELLOW}Step 1: Getting current list of servers...${NC}"
SERVERS=$(curl -s -X GET "http://localhost:9200/mcp-servers-default/_search?pretty" \
  -u admin:admin \
  -H 'Content-Type: application/json' \
  -d '{"query": {"match_all": {}}, "size": 100}' | \
  jq -r '.hits.hits[]._source.path')

if [ -z "$SERVERS" ]; then
  echo -e "${GREEN}No servers found in registry${NC}"
else
  echo -e "${GREEN}Found servers:${NC}"
  echo "$SERVERS"
fi

# Step 2: Remove all servers
echo ""
echo -e "${YELLOW}Step 2: Removing all servers...${NC}"
for server_path in $SERVERS; do
  echo -e "  Removing: ${server_path}"
  cd "$CLI_DIR"
  uv run python registry_management.py \
    --registry-url "$REGISTRY_URL" \
    --token-file "$TOKEN_FILE" \
    remove --path "$server_path" || echo -e "    ${RED}Failed to remove ${server_path}${NC}"
done

# Step 3: Re-register servers from JSON files
echo ""
echo -e "${YELLOW}Step 3: Re-registering servers from JSON files...${NC}"

# List of server config files (not agents)
SERVER_CONFIGS=(
  "context7-server-config.json"
  "currenttime.json"
  "cloudflare-docs-server-config.json"
  "mcpgw.json"
  "server-config.json"
  "minimal-server-config.json"
)

for config_file in "${SERVER_CONFIGS[@]}"; do
  config_path="$EXAMPLES_DIR/$config_file"
  if [ -f "$config_path" ]; then
    echo -e "  Registering: ${config_file}"
    cd "$CLI_DIR"
    uv run python registry_management.py \
      --registry-url "$REGISTRY_URL" \
      --token-file "$TOKEN_FILE" \
      register --config "$config_path" || echo -e "    ${RED}Failed to register ${config_file}${NC}"
  else
    echo -e "    ${RED}File not found: ${config_path}${NC}"
  fi
done

# Step 4: Verify embeddings index
echo ""
echo -e "${YELLOW}Step 4: Verifying embeddings index...${NC}"
sleep 2  # Give OpenSearch time to index

EMBEDDING_COUNT=$(curl -s -X GET "http://localhost:9200/mcp-embeddings-default/_count?pretty" \
  -u admin:admin | jq -r '.count')

echo -e "${GREEN}Embeddings index count: ${EMBEDDING_COUNT}${NC}"

# Step 5: Show indexed servers
echo ""
echo -e "${YELLOW}Step 5: Listing registered servers...${NC}"
cd "$CLI_DIR"
uv run python registry_management.py \
  --registry-url "$REGISTRY_URL" \
  --token-file "$TOKEN_FILE" \
  list

echo ""
echo -e "${GREEN}=== Re-population Complete ===${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. Check embeddings index: curl -X GET 'http://localhost:9200/mcp-embeddings-default/_search?pretty' -u admin:admin"
echo -e "  2. Test semantic search: See api/test-semantic-search.sh"
echo ""
