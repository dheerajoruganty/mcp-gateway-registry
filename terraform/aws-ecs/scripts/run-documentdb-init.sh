#!/bin/bash
# Run DocumentDB initialization via ECS task
#
# This script runs the init-documentdb-indexes.py script inside an ECS task
# with proper network access to the DocumentDB cluster in the VPC.
#
# Usage:
#   ./terraform/aws-ecs/scripts/run-documentdb-init.sh

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TERRAFORM_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Show help function
show_help() {
    cat << EOF
DocumentDB Initialization Script

Usage: $0 [options]

This script runs the DocumentDB index initialization inside an ECS task
with proper network access to the DocumentDB cluster.

Options:
  -h, --help                     Show this help message

Environment Variables:
  DOCUMENTDB_HOST                Override DocumentDB endpoint (optional)
  AWS_REGION                     AWS region (default: us-east-1)

The script automatically reads the DocumentDB endpoint from SSM Parameter Store
if available, otherwise falls back to DOCUMENTDB_HOST environment variable.
EOF
    exit 0
}

# Check for help flag
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_help
fi

# Get AWS account and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="${AWS_REGION:-us-west-2}"

# ECS configuration
CLUSTER_NAME="mcp-gateway-ecs-cluster"
TASK_FAMILY="mcp-gateway-v2-registry"
CONTAINER_NAME="registry"

# Terraform outputs file location
OUTPUTS_FILE="$SCRIPT_DIR/terraform-outputs.json"

# Get DocumentDB host - check sources in order of priority:
# 1. Environment variable (explicit override)
# 2. Terraform outputs file
# 3. SSM Parameter Store
if [ -z "$DOCUMENTDB_HOST" ]; then
    # Try terraform outputs first
    if [ -f "$OUTPUTS_FILE" ]; then
        echo -e "${YELLOW}Checking terraform outputs for DocumentDB endpoint...${NC}"
        DOCUMENTDB_HOST=$(jq -r '.documentdb_cluster_endpoint.value // empty' "$OUTPUTS_FILE" 2>/dev/null || echo "")
        if [ -n "$DOCUMENTDB_HOST" ] && [ "$DOCUMENTDB_HOST" != "null" ]; then
            echo -e "${GREEN}Found DocumentDB endpoint in terraform outputs${NC}"
        else
            DOCUMENTDB_HOST=""
        fi
    fi

    # Fall back to SSM Parameter Store
    if [ -z "$DOCUMENTDB_HOST" ]; then
        echo -e "${YELLOW}Fetching DocumentDB endpoint from SSM Parameter Store...${NC}"
        DOCUMENTDB_HOST=$(aws ssm get-parameter \
            --name "/mcp-gateway/documentdb/endpoint" \
            --query 'Parameter.Value' \
            --output text \
            --region "$AWS_REGION" 2>/dev/null || echo "")

        if [ -n "$DOCUMENTDB_HOST" ] && [ "$DOCUMENTDB_HOST" != "None" ]; then
            echo -e "${GREEN}Found DocumentDB endpoint in SSM${NC}"
        else
            DOCUMENTDB_HOST=""
        fi
    fi
fi

# Validate DocumentDB host
if [ -z "$DOCUMENTDB_HOST" ]; then
    echo -e "${RED}Error: DocumentDB endpoint not found${NC}"
    echo ""
    echo "Checked the following sources:"
    echo "  1. DOCUMENTDB_HOST environment variable"
    echo "  2. Terraform outputs file: $OUTPUTS_FILE"
    echo "  3. SSM Parameter Store: /mcp-gateway/documentdb/endpoint"
    echo ""
    echo "Make sure you have run 'terraform apply' and saved outputs,"
    echo "or set DOCUMENTDB_HOST environment variable."
    exit 1
fi

# Get credentials from Secrets Manager
echo -e "${YELLOW}Fetching DocumentDB credentials from Secrets Manager...${NC}"
SECRET_ARN=$(aws secretsmanager list-secrets \
    --filters Key=name,Values=mcp-gateway/documentdb/credentials \
    --query 'SecretList[0].ARN' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "")

DOCUMENTDB_USERNAME=""
DOCUMENTDB_PASSWORD=""

if [ -n "$SECRET_ARN" ] && [ "$SECRET_ARN" != "None" ]; then
    SECRET_JSON=$(aws secretsmanager get-secret-value \
        --secret-id "$SECRET_ARN" \
        --query 'SecretString' \
        --output text \
        --region "$AWS_REGION" 2>/dev/null || echo "")

    if [ -n "$SECRET_JSON" ]; then
        DOCUMENTDB_USERNAME=$(echo "$SECRET_JSON" | jq -r '.username // ""')
        DOCUMENTDB_PASSWORD=$(echo "$SECRET_JSON" | jq -r '.password // ""')
        echo -e "${GREEN}Found credentials in Secrets Manager${NC}"
    fi
fi

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
echo "  DocumentDB Host: $DOCUMENTDB_HOST"
echo "  DocumentDB Username: ${DOCUMENTDB_USERNAME:-<not set>}"
echo ""

# Create simple command to run Python initialization and scopes loading
echo -e "${YELLOW}Preparing initialization command...${NC}"
INIT_COMMAND="source /app/.venv/bin/activate && cd /app/scripts && python init-documentdb-indexes.py && python load-scopes.py --scopes-file /app/config/scopes.yml"

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
    --overrides "$(jq -n \
        --arg container "$CONTAINER_NAME" \
        --arg cmd "$INIT_COMMAND" \
        --arg host "$DOCUMENTDB_HOST" \
        --arg user "$DOCUMENTDB_USERNAME" \
        --arg pass "$DOCUMENTDB_PASSWORD" \
        '{
            "containerOverrides": [{
                "name": $container,
                "command": ["/bin/bash", "-c", $cmd],
                "environment": [
                    {"name": "RUN_INIT_SCRIPTS", "value": "true"},
                    {"name": "DOCUMENTDB_HOST", "value": $host},
                    {"name": "DOCUMENTDB_PORT", "value": "27017"},
                    {"name": "DOCUMENTDB_USERNAME", "value": $user},
                    {"name": "DOCUMENTDB_PASSWORD", "value": $pass},
                    {"name": "DOCUMENTDB_DATABASE", "value": "mcp_registry"},
                    {"name": "DOCUMENTDB_NAMESPACE", "value": "default"},
                    {"name": "DOCUMENTDB_USE_TLS", "value": "true"},
                    {"name": "DOCUMENTDB_USE_IAM", "value": "false"},
                    {"name": "DOCUMENTDB_TLS_CA_FILE", "value": "/app/global-bundle.pem"}
                ]
            }]
        }')" \
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
echo -e "${YELLOW}Waiting for task to complete (this may take 2-3 minutes)...${NC}"
for i in {1..90}; do
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

# Get logs (wait a bit for logs to be available)
echo ""
echo -e "${YELLOW}Retrieving task logs...${NC}"
sleep 3

# Get the actual log stream name
LOG_STREAM_NAME="ecs/registry/$TASK_ID"

echo ""
printf '=%.0s' {1..100}
echo ""

# Try to get logs
LOGS=$(aws logs get-log-events \
    --log-group-name "/ecs/mcp-gateway-v2-registry" \
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
        --log-group-name "/ecs/mcp-gateway-v2-registry" \
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
if [ "$EXIT_CODE" = "0" ]; then
    echo -e "${GREEN}SUCCESS: DocumentDB initialization completed${NC}"
else
    echo -e "${RED}ERROR: DocumentDB initialization failed${NC}"
fi

exit "${EXIT_CODE:-1}"
