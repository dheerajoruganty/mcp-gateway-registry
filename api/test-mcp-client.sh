#!/bin/bash

# Simple MCP client for testing MCP servers
# Usage: ./test-mcp-client.sh [method] [server-url]

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Default values
METHOD="${1:-ping}"
SERVER_URL="${2:-https://mcpgateway.ddns.net/currenttime/mcp}"
#"https://mcpgateway.ddns.net/cloudflare-docs/mcp
TOKEN_FILE="${TOKEN_FILE:-${SCRIPT_DIR}/.token}"
SESSION_FILE="${SCRIPT_DIR}/.mcp-session"

# Check if token file exists
if [ ! -f "$TOKEN_FILE" ]; then
    echo "Error: Token file not found at $TOKEN_FILE"
    echo "Run get-m2m-token.sh first to generate a token"
    exit 1
fi

# Read token
ACCESS_TOKEN=$(cat "$TOKEN_FILE")

# Read session ID if exists
SESSION_ID=""
if [ -f "$SESSION_FILE" ]; then
    SESSION_ID=$(cat "$SESSION_FILE")
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Calling MCP server...${NC}"
echo "  Method: $METHOD"
echo "  Server: $SERVER_URL"
if [ -n "$SESSION_ID" ]; then
    echo "  Session: $SESSION_ID"
fi
echo ""

# Build the request based on method
case "$METHOD" in
    ping)
        REQUEST_DATA='{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "ping"
        }'
        ;;
    initialize)
        REQUEST_DATA='{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }'
        ;;
    tools/list)
        REQUEST_DATA='{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list"
        }'
        ;;
    resources/list)
        REQUEST_DATA='{
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/list"
        }'
        ;;
    current_time)
        TIMEZONE="${3:-America/New_York}"
        REQUEST_DATA="{
            \"jsonrpc\": \"2.0\",
            \"id\": 1,
            \"method\": \"tools/call\",
            \"params\": {
                \"name\": \"current_time_by_timezone\",
                \"arguments\": {
                    \"timezone\": \"$TIMEZONE\"
                }
            }
        }"
        ;;
    *)
        echo "Unknown method: $METHOD"
        echo ""
        echo "Available methods:"
        echo "  ping              - Test server connectivity"
        echo "  initialize        - Initialize MCP connection"
        echo "  tools/list        - List available tools"
        echo "  resources/list    - List available resources"
        echo "  current_time [tz] - Get current time (optional timezone)"
        exit 1
        ;;
esac

# Make the request with proper headers for SSE support
# Include session ID in mcp-session-id header if available
# Use temporary file to capture response headers
HEADERS_FILE=$(mktemp)
RESPONSE=""
if [ -n "$SESSION_ID" ]; then
    RESPONSE=$(curl -D "$HEADERS_FILE" -s -X POST "$SERVER_URL" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -H "mcp-session-id: ${SESSION_ID}" \
        -d "$REQUEST_DATA")
else
    RESPONSE=$(curl -D "$HEADERS_FILE" -s -X POST "$SERVER_URL" \
        -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$REQUEST_DATA")
fi

# Parse SSE response - extract JSON from "data:" lines
# SSE format is: "event: message\ndata: {json}"
JSON_RESPONSE=$(echo "$RESPONSE" | grep "^data: " | sed 's/^data: //' | head -1)

if [ -z "$JSON_RESPONSE" ]; then
    # No SSE format, assume plain JSON
    JSON_RESPONSE="$RESPONSE"
fi

# Display response
echo "$JSON_RESPONSE" | jq .

# Extract session ID from response headers (mcp-session-id header)
NEW_SESSION_ID=$(grep -i "^mcp-session-id:" "$HEADERS_FILE" | sed 's/^mcp-session-id: *//i' | tr -d '\r\n')

# Save session ID if present
if [ -n "$NEW_SESSION_ID" ]; then
    echo "$NEW_SESSION_ID" > "$SESSION_FILE"
    echo -e "${GREEN}Session ID saved to $SESSION_FILE: $NEW_SESSION_ID${NC}"
fi

# Clean up temporary headers file
rm -f "$HEADERS_FILE"

echo ""
echo -e "${GREEN}Done!${NC}"
