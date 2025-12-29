#!/bin/bash
# Run AOSS index management commands via ECS task
#
# This script runs the manage-aoss-indexes.py script inside an ECS task
# with proper IAM permissions to access OpenSearch Serverless.
#
# Usage:
#   ./terraform/aws-ecs/scripts/run-aoss-cli.sh list
#   ./terraform/aws-ecs/scripts/run-aoss-cli.sh inspect mcp-servers-default
#   ./terraform/aws-ecs/scripts/run-aoss-cli.sh count mcp-embeddings-default
#   ./terraform/aws-ecs/scripts/run-aoss-cli.sh search mcp-servers-default 5
#   ./terraform/aws-ecs/scripts/run-aoss-cli.sh delete old-index --confirm

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TERRAFORM_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$TERRAFORM_DIR")")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse command
COMMAND=${1:-list}
shift || true

# Build command arguments as JSON array
case "$COMMAND" in
    list)
        # No additional args needed
        COMMAND_JSON="\"$COMMAND\""
        ;;

    inspect|count|delete)
        INDEX_NAME=${1:-}
        if [ -z "$INDEX_NAME" ]; then
            echo -e "${RED}Error: Index name required for $COMMAND command${NC}"
            echo "Usage: $0 $COMMAND <index-name>"
            exit 1
        fi
        shift || true

        # Check for --confirm flag for delete
        if [ "$COMMAND" = "delete" ] && [ "$1" = "--confirm" ]; then
            COMMAND_JSON="\"$COMMAND\", \"--index\", \"$INDEX_NAME\", \"--confirm\""
        else
            COMMAND_JSON="\"$COMMAND\", \"--index\", \"$INDEX_NAME\""
        fi
        ;;

    search)
        INDEX_NAME=${1:-}
        SIZE=${2:-10}
        if [ -z "$INDEX_NAME" ]; then
            echo -e "${RED}Error: Index name required for search command${NC}"
            echo "Usage: $0 search <index-name> [size]"
            exit 1
        fi
        COMMAND_JSON="\"$COMMAND\", \"--index\", \"$INDEX_NAME\", \"--size\", \"$SIZE\""
        ;;

    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        echo "Available commands:"
        echo "  list                           - List all indexes"
        echo "  inspect <index>                - Inspect index mapping and settings"
        echo "  count <index>                  - Count documents in index"
        echo "  search <index> [size]          - Search documents (default size: 10)"
        echo "  delete <index> [--confirm]     - Delete index"
        exit 1
        ;;
esac

# Get AWS account and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="${AWS_REGION:-us-east-1}"

# ECS configuration
CLUSTER_NAME="mcp-gateway-ecs-cluster"
TASK_FAMILY="mcp-gateway-opensearch-cli"
CONTAINER_NAME="opensearch-cli"

# Get OpenSearch host from environment or default
OPENSEARCH_HOST="${OPENSEARCH_HOST:-qmnoselvyumijjiom050.us-east-1.aoss.amazonaws.com}"

# Get VPC configuration from registry service
echo -e "${YELLOW}Getting VPC configuration from registry service...${NC}"
VPC_CONFIG=$(aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services mcp-gateway-v2-registry \
    --region "$AWS_REGION" \
    --query 'services[0].networkConfiguration.awsvpcConfiguration' \
    --output json)

SUBNETS=$(echo "$VPC_CONFIG" | jq -r '.subnets | join(",")')
SECURITY_GROUPS=$(echo "$VPC_CONFIG" | jq -r '.securityGroups | join(",")')

echo -e "${BLUE}Configuration:${NC}"
echo "  Cluster: $CLUSTER_NAME"
echo "  Task: $TASK_FAMILY"
echo "  OpenSearch Host: $OPENSEARCH_HOST"
echo "  Command: $COMMAND"
echo ""

# Check if task definition exists
TASK_DEF_ARN=$(aws ecs describe-task-definition \
    --task-definition "$TASK_FAMILY" \
    --region "$AWS_REGION" \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text 2>/dev/null || echo "")

if [ -z "$TASK_DEF_ARN" ] || [ "$TASK_DEF_ARN" = "None" ]; then
    echo -e "${RED}Error: Task definition '$TASK_FAMILY' not found${NC}"
    echo ""
    echo "You need to create the task definition first."
    echo "Run: cd terraform/aws-ecs && terraform apply"
    exit 1
fi

echo -e "${GREEN}Task definition found: $TASK_DEF_ARN${NC}"
echo ""

# Run the ECS task
echo -e "${YELLOW}Starting ECS task...${NC}"
TASK_ARN=$(aws ecs run-task \
    --cluster "$CLUSTER_NAME" \
    --task-definition "$TASK_FAMILY" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SECURITY_GROUPS],assignPublicIp=DISABLED}" \
    --overrides "{
        \"containerOverrides\": [{
            \"name\": \"$CONTAINER_NAME\",
            \"command\": [\"python\", \"scripts/manage-aoss-indexes.py\", $COMMAND_JSON],
            \"environment\": [
                {\"name\": \"OPENSEARCH_HOST\", \"value\": \"$OPENSEARCH_HOST\"},
                {\"name\": \"AWS_REGION\", \"value\": \"$AWS_REGION\"}
            ]
        }]
    }" \
    --region "$AWS_REGION" \
    --query 'tasks[0].taskArn' \
    --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
    echo -e "${RED}Failed to start ECS task${NC}"
    exit 1
fi

TASK_ID=$(basename "$TASK_ARN")
echo -e "${GREEN}Task started: $TASK_ID${NC}"
echo ""

# Wait for task to complete
echo -e "${YELLOW}Waiting for task to complete...${NC}"
for i in {1..60}; do
    sleep 2

    STATUS=$(aws ecs describe-tasks \
        --cluster "$CLUSTER_NAME" \
        --tasks "$TASK_ARN" \
        --region "$AWS_REGION" \
        --query 'tasks[0].lastStatus' \
        --output text)

    if [ "$STATUS" = "STOPPED" ]; then
        echo -e "${GREEN}Task completed${NC}"
        break
    fi

    echo "  [$i] Status: $STATUS"
done

# Get exit code
EXIT_CODE=$(aws ecs describe-tasks \
    --cluster "$CLUSTER_NAME" \
    --tasks "$TASK_ARN" \
    --region "$AWS_REGION" \
    --query 'tasks[0].containers[0].exitCode' \
    --output text)

echo ""
echo -e "${BLUE}Task exit code: $EXIT_CODE${NC}"

# Get CloudWatch log stream name
LOG_STREAM=$(aws ecs describe-tasks \
    --cluster "$CLUSTER_NAME" \
    --tasks "$TASK_ARN" \
    --region "$AWS_REGION" \
    --query 'tasks[0].containers[0].name' \
    --output text 2>/dev/null || echo "")

# Get logs (wait a bit for logs to be available)
echo ""
echo -e "${YELLOW}Retrieving task logs...${NC}"
sleep 3

# Get the actual log stream name
TASK_ID=$(basename "$TASK_ARN")
LOG_STREAM_NAME="opensearch-cli/opensearch-cli/$TASK_ID"

echo ""
printf '=%.0s' {1..100}
echo ""

# Try to get logs
LOGS=$(aws logs get-log-events \
    --log-group-name "/ecs/mcp-gateway-opensearch-cli" \
    --log-stream-name "$LOG_STREAM_NAME" \
    --region "$AWS_REGION" \
    --query 'events[*].message' \
    --output json 2>/dev/null)

if [ $? -eq 0 ] && [ -n "$LOGS" ] && [ "$LOGS" != "[]" ]; then
    # Parse JSON array and print each message on a new line
    echo "$LOGS" | jq -r '.[]' 2>/dev/null || echo "$LOGS"
else
    echo "No logs found in stream: $LOG_STREAM_NAME"
    echo ""
    echo "Available log streams:"
    aws logs describe-log-streams \
        --log-group-name "/ecs/mcp-gateway-opensearch-cli" \
        --order-by LastEventTime \
        --descending \
        --max-items 5 \
        --region "$AWS_REGION" \
        --query 'logStreams[*].logStreamName' \
        --output text 2>/dev/null || echo "Could not retrieve log streams"
fi

echo ""
printf '=%.0s' {1..100}
echo ""

# Exit with same code as task
exit "${EXIT_CODE:-1}"
