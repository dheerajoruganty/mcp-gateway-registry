#!/bin/bash
# View CloudWatch logs for MCP Gateway services
# Usage: ./scripts/view-logs.sh [service-name] [minutes]
#
# Examples:
#   ./scripts/view-logs.sh auth 5
#   ./scripts/view-logs.sh registry 10
#   ./scripts/view-logs.sh keycloak 15
#   ./scripts/view-logs.sh opensearch 5

set -e

SERVICE=${1:-registry}
MINUTES=${2:-5}

case "$SERVICE" in
  auth|auth-server)
    LOG_GROUP="/ecs/mcp-gateway-v2-auth-server"
    ;;
  registry)
    LOG_GROUP="/ecs/mcp-gateway-v2-registry"
    ;;
  keycloak|kc)
    LOG_GROUP="/ecs/keycloak"
    ;;
  opensearch|os)
    LOG_GROUP="/ecs/opensearch-cluster"
    ;;
  mcpgw|gateway)
    LOG_GROUP="/ecs/mcp-gateway-v2-mcpgw"
    ;;
  currenttime|ct)
    LOG_GROUP="/ecs/mcp-gateway-v2-currenttime"
    ;;
  realserver|rs|realserverfaketools)
    LOG_GROUP="/ecs/mcp-gateway-v2-realserverfaketools"
    ;;
  flight|flight-booking)
    LOG_GROUP="/ecs/mcp-gateway-v2-flight-booking-agent"
    ;;
  travel|travel-assistant)
    LOG_GROUP="/ecs/mcp-gateway-v2-travel-assistant-agent"
    ;;
  *)
    echo "Unknown service: $SERVICE"
    echo ""
    echo "Available services:"
    echo "  auth, registry, keycloak, opensearch"
    echo "  mcpgw, currenttime, realserver, flight, travel"
    exit 1
    ;;
esac

echo "Viewing logs for $SERVICE (last $MINUTES minutes)..."
echo "Log group: $LOG_GROUP"
echo ""

aws logs tail "$LOG_GROUP" --since "${MINUTES}m" --format short --follow
