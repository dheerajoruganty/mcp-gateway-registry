#!/bin/bash
# OpenSearch CLI helper script
# Provides easy access to OpenSearch cluster via internal ALB
#
# Usage:
#   ./scripts/opensearch-cli.sh [command] [args...]
#
# Commands:
#   health              - Check cluster health
#   nodes               - List all nodes
#   indices             - List all indices
#   index <name>        - Get details about a specific index
#   search <index>      - Search all documents in an index
#   count <index>       - Count documents in an index
#   mapping <index>     - Get mapping for an index
#   settings <index>    - Get settings for an index
#   delete-index <name> - Delete an index (use with caution!)
#   cat-indices         - Cat API for indices (formatted table)
#   raw <path>          - Make a raw GET request to OpenSearch
#
# Examples:
#   ./scripts/opensearch-cli.sh health
#   ./scripts/opensearch-cli.sh indices
#   ./scripts/opensearch-cli.sh search mcp-servers
#   ./scripts/opensearch-cli.sh count mcp-servers

set -e

# Get OpenSearch internal ALB DNS from terraform output
OPENSEARCH_URL="http://internal-mcp-gateway-opensearch-alb-1936709394.us-east-1.elb.amazonaws.com:9200"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to make OpenSearch request
os_request() {
    local method=$1
    local path=$2
    local data=$3

    if [ -n "$data" ]; then
        curl -s -X "$method" "${OPENSEARCH_URL}${path}" \
            -H "Content-Type: application/json" \
            -d "$data"
    else
        curl -s -X "$method" "${OPENSEARCH_URL}${path}"
    fi
}

# Parse command
COMMAND=${1:-health}

case "$COMMAND" in
    health)
        echo -e "${YELLOW}OpenSearch Cluster Health:${NC}"
        os_request GET "/_cluster/health?pretty"
        ;;

    nodes)
        echo -e "${YELLOW}OpenSearch Nodes:${NC}"
        os_request GET "/_cat/nodes?v"
        ;;

    indices|indexes)
        echo -e "${YELLOW}OpenSearch Indices:${NC}"
        os_request GET "/_cat/indices?v&s=index"
        ;;

    cat-indices)
        echo -e "${YELLOW}OpenSearch Indices (detailed):${NC}"
        os_request GET "/_cat/indices?v&h=index,health,status,pri,rep,docs.count,store.size&s=index"
        ;;

    index)
        INDEX_NAME=$2
        if [ -z "$INDEX_NAME" ]; then
            echo -e "${RED}Error: Index name required${NC}"
            echo "Usage: $0 index <index-name>"
            exit 1
        fi
        echo -e "${YELLOW}Index Details: $INDEX_NAME${NC}"
        os_request GET "/${INDEX_NAME}?pretty"
        ;;

    search)
        INDEX_NAME=${2:-_all}
        SIZE=${3:-10}
        echo -e "${YELLOW}Searching index: $INDEX_NAME (showing $SIZE results)${NC}"
        os_request GET "/${INDEX_NAME}/_search?pretty&size=${SIZE}"
        ;;

    count)
        INDEX_NAME=${2:-_all}
        echo -e "${YELLOW}Document count for: $INDEX_NAME${NC}"
        os_request GET "/${INDEX_NAME}/_count?pretty"
        ;;

    mapping)
        INDEX_NAME=$2
        if [ -z "$INDEX_NAME" ]; then
            echo -e "${RED}Error: Index name required${NC}"
            echo "Usage: $0 mapping <index-name>"
            exit 1
        fi
        echo -e "${YELLOW}Mapping for: $INDEX_NAME${NC}"
        os_request GET "/${INDEX_NAME}/_mapping?pretty"
        ;;

    settings)
        INDEX_NAME=$2
        if [ -z "$INDEX_NAME" ]; then
            echo -e "${RED}Error: Index name required${NC}"
            echo "Usage: $0 settings <index-name>"
            exit 1
        fi
        echo -e "${YELLOW}Settings for: $INDEX_NAME${NC}"
        os_request GET "/${INDEX_NAME}/_settings?pretty"
        ;;

    delete-index)
        INDEX_NAME=$2
        if [ -z "$INDEX_NAME" ]; then
            echo -e "${RED}Error: Index name required${NC}"
            echo "Usage: $0 delete-index <index-name>"
            exit 1
        fi
        echo -e "${YELLOW}Deleting index: $INDEX_NAME${NC}"
        read -p "Are you sure you want to delete this index? (yes/no): " confirmation
        if [ "$confirmation" = "yes" ]; then
            os_request DELETE "/${INDEX_NAME}?pretty"
            echo -e "${GREEN}Index deleted${NC}"
        else
            echo -e "${YELLOW}Deletion cancelled${NC}"
        fi
        ;;

    raw)
        PATH_ARG=$2
        if [ -z "$PATH_ARG" ]; then
            echo -e "${RED}Error: Path required${NC}"
            echo "Usage: $0 raw <path>"
            echo "Example: $0 raw '/_cluster/stats?pretty'"
            exit 1
        fi
        os_request GET "$PATH_ARG"
        ;;

    stats)
        echo -e "${YELLOW}Cluster Statistics:${NC}"
        os_request GET "/_cluster/stats?pretty"
        ;;

    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        echo "Available commands:"
        echo "  health              - Check cluster health"
        echo "  nodes               - List all nodes"
        echo "  indices             - List all indices"
        echo "  cat-indices         - Cat API for indices (formatted table)"
        echo "  index <name>        - Get details about a specific index"
        echo "  search <index>      - Search all documents in an index"
        echo "  count <index>       - Count documents in an index"
        echo "  mapping <index>     - Get mapping for an index"
        echo "  settings <index>    - Get settings for an index"
        echo "  delete-index <name> - Delete an index (use with caution!)"
        echo "  stats               - Cluster statistics"
        echo "  raw <path>          - Make a raw GET request to OpenSearch"
        exit 1
        ;;
esac
