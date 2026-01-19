#!/bin/bash
# Deploy registry service to ECS
# Usage: ./scripts/deploy-registry.sh [NO_CACHE=true]
# Example: ./scripts/deploy-registry.sh
# Example: NO_CACHE=true ./scripts/deploy-registry.sh

# Exit on error
set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECS_CLUSTER="mcp-gateway-ecs-cluster"
ECS_SERVICE="mcp-gateway-v2-registry"

echo "=========================================="
echo "Registry Deployment Script"
echo "=========================================="
echo ""

# Step 1: Build and push Docker image
echo "Step 1/3: Building and pushing Docker image..."
echo "----------------------------------------"
if [[ "${NO_CACHE:-}" == "true" ]]; then
    echo "Building without cache (NO_CACHE=true)"
    cd "$REPO_ROOT"
    NO_CACHE=true make build-push IMAGE=registry
else
    cd "$REPO_ROOT"
    make build-push IMAGE=registry
fi

if [ $? -ne 0 ]; then
    echo "Error: Docker build and push failed"
    exit 1
fi

echo ""
echo "Step 2/3: Forcing new deployment..."
echo "----------------------------------------"
aws ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$ECS_SERVICE" \
    --force-new-deployment \
    --region "$AWS_REGION" \
    --output json | jq '{service: .service.serviceName, status: .service.status, desiredCount: .service.desiredCount}'

if [ $? -ne 0 ]; then
    echo "Error: Force new deployment failed"
    exit 1
fi

echo ""
echo "Step 3/3: Monitoring deployment status..."
echo "----------------------------------------"
echo "Press Ctrl+C to exit monitoring"
echo ""
sleep 2

# Monitor deployment with watch
watch -n 5 'aws ecs describe-services \
  --cluster '"$ECS_CLUSTER"' \
  --service '"$ECS_SERVICE"' \
  --region '"$AWS_REGION"' \
  --query "services[0].{Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Deployments:deployments[*].{Status:status,Running:runningCount,Desired:desiredCount,RolloutState:rolloutState}}" \
  --output table'
