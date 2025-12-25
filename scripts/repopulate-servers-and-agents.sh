#!/bin/bash

# Script to remove all servers and agents, then re-register them to populate embeddings index
# This ensures all entities get indexed in the OpenSearch embeddings index

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

# Token file (absolute path from repo root)
TOKEN_FILE="$REPO_ROOT/.oauth-tokens/ingress.json"

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

# Step 2: Get current list of agents
echo ""
echo -e "${YELLOW}Step 2: Getting current list of agents...${NC}"
AGENTS=$(curl -s -X GET "http://localhost:9200/mcp-agents-default/_search?pretty" \
  -u admin:admin \
  -H 'Content-Type: application/json' \
  -d '{"query": {"match_all": {}}, "size": 100}' | \
  jq -r '.hits.hits[]._source.path')

if [ -z "$AGENTS" ]; then
  echo -e "${GREEN}No agents found in registry${NC}"
else
  echo -e "${GREEN}Found agents:${NC}"
  echo "$AGENTS"
fi

# Step 3: Remove all servers
echo ""
echo -e "${YELLOW}Step 3: Removing all servers...${NC}"
for server_path in $SERVERS; do
  echo -e "  Removing: ${server_path}"
  cd "$CLI_DIR"
  echo "yes" | uv run python registry_management.py \
    --registry-url "$REGISTRY_URL" \
    --token-file "$TOKEN_FILE" \
    remove --path "$server_path" 2>&1 | grep -v "^2025-" || true
done

# Step 4: Remove all agents
echo ""
echo -e "${YELLOW}Step 4: Removing all agents...${NC}"
for agent_path in $AGENTS; do
  echo -e "  Removing: ${agent_path}"
  cd "$CLI_DIR"
  echo "yes" | uv run python registry_management.py \
    --registry-url "$REGISTRY_URL" \
    --token-file "$TOKEN_FILE" \
    agent-delete --path "$agent_path" 2>&1 | grep -v "^2025-" || true
done

# Step 5: Re-register servers from JSON files
echo ""
echo -e "${YELLOW}Step 5: Re-registering servers from JSON files...${NC}"

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
      register --config "$config_path" 2>&1 | grep -v "^2025-" || echo -e "    ${RED}Failed to register ${config_file}${NC}"
  else
    echo -e "    ${RED}File not found: ${config_path}${NC}"
  fi
done

# Step 6: Re-register agents from JSON files
echo ""
echo -e "${YELLOW}Step 6: Re-registering agents from JSON files...${NC}"

# List of agent config files
AGENT_CONFIGS=(
  "flight_booking_agent_card.json"
  "travel_assistant_agent_card.json"
)

for config_file in "${AGENT_CONFIGS[@]}"; do
  config_path="$EXAMPLES_DIR/$config_file"
  if [ -f "$config_path" ]; then
    echo -e "  Registering: ${config_file}"
    cd "$CLI_DIR"
    uv run python registry_management.py \
      --registry-url "$REGISTRY_URL" \
      --token-file "$TOKEN_FILE" \
      agent-register --config "$config_path" 2>&1 | grep -v "^2025-" || echo -e "    ${RED}Failed to register ${config_file}${NC}"
  else
    echo -e "    ${RED}File not found: ${config_path}${NC}"
  fi
done

# Step 7: Verify embeddings index
echo ""
echo -e "${YELLOW}Step 7: Verifying embeddings index...${NC}"
sleep 2  # Give OpenSearch time to index

EMBEDDING_COUNT=$(curl -s -X GET "http://localhost:9200/mcp-embeddings-default/_count?pretty" \
  -u admin:admin | jq -r '.count')

echo -e "${GREEN}Embeddings index count: ${EMBEDDING_COUNT}${NC}"

# Step 8: Show sample embeddings
echo ""
echo -e "${YELLOW}Step 8: Sample embeddings from index...${NC}"
curl -s -X GET "http://localhost:9200/mcp-embeddings-default/_search?pretty" \
  -u admin:admin \
  -H 'Content-Type: application/json' \
  -d '{"query": {"match_all": {}}, "size": 3, "_source": ["entity_type", "path", "name"]}' | \
  jq -r '.hits.hits[]._source | "\(.entity_type): \(.path) - \(.name)"'

# Step 9: Show indexed servers
echo ""
echo -e "${YELLOW}Step 9: Listing registered servers...${NC}"
cd "$CLI_DIR"
uv run python registry_management.py \
  --registry-url "$REGISTRY_URL" \
  --token-file "$TOKEN_FILE" \
  list 2>&1 | grep -v "^2025-" || true

echo ""
echo -e "${GREEN}=== Re-population Complete ===${NC}"
echo ""
echo -e "Summary:"
echo -e "  - Total embeddings: ${EMBEDDING_COUNT}"
echo ""
echo -e "Next steps:"
echo -e "  1. Check embeddings index: curl -X GET 'http://localhost:9200/mcp-embeddings-default/_search?pretty' -u admin:admin"
echo -e "  2. Test semantic search: cd api && bash test-semantic-search.sh"
echo ""
