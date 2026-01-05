# MCP Gateway ECS Deployment Scripts

This directory contains scripts for deploying and managing the MCP Gateway services on AWS ECS.

## Registry Service Operations

### Build and Push Registry Image

Build the registry Docker image and push to ECR:

```bash
# From repository root
make build-push IMAGE=registry
```

This command:
- Builds the registry Docker image from the Dockerfile
- Tags it with the ECR repository URL
- Pushes to Amazon ECR
- The image will be available for ECS to pull

### Force Redeploy Registry Tasks

Force ECS to pull the latest image and redeploy registry tasks:

```bash
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --force-new-deployment \
  --region us-east-1
```

This command:
- Triggers a new deployment without changing task definition
- ECS will pull the latest image from ECR
- Old tasks are gracefully drained and replaced with new ones

### Monitor Deployment Status

Watch deployment progress in real-time:

```bash
watch -n 5 'aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --region us-east-1 \
  --query "services[0].{Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Deployments:deployments[*].{Status:status,Running:runningCount,Desired:desiredCount,RolloutState:rolloutState}}" \
  --output table'
```

This command:
- Refreshes every 5 seconds
- Shows deployment status in table format
- Displays:
  - Service status
  - Desired vs running task counts
  - Pending tasks
  - Deployment rollout state

**Example Output:**
```
----------------------------------------------------------
|                   DescribeServices                     |
+----------+----------+---------+----------+--------------+
| Desired  | Pending  | Running | Status   |              |
+----------+----------+---------+----------+--------------+
|  2       |  0       |  2      |  ACTIVE  |              |
+----------+----------+---------+----------+--------------+
||                     Deployments                       ||
|+----------+----------+---------+-------------------+   ||
|| Desired  | Running  | Status  | RolloutState      |   ||
|+----------+----------+---------+-------------------+   ||
||  2       |  2       | PRIMARY | COMPLETED         |   ||
|+----------+----------+---------+-------------------+   ||
```

Press `Ctrl+C` to exit the watch command.

### Complete Deployment Workflow

Full workflow to deploy registry code changes:

```bash
# 1. Build and push new image
make build-push IMAGE=registry

# 2. Force redeploy (in separate terminal or after build completes)
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --force-new-deployment \
  --region us-east-1

# 3. Monitor deployment status
watch -n 5 'aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --region us-east-1 \
  --query "services[0].{Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Deployments:deployments[*].{Status:status,Running:runningCount,Desired:desiredCount,RolloutState:rolloutState}}" \
  --output table'
```

## Other Services

The same commands can be used for other services by replacing `registry` with the service name:

- `mcp-gateway-v2-auth` - Authentication server
- `mcp-gateway-v2-mcpgw` - MCP Gateway
- `mcp-gateway-v2-currenttime` - Current Time MCP Server
- `mcp-gateway-v2-realserverfaketools` - Test MCP Server
- `mcp-gateway-v2-flight-booking-agent` - Flight Booking Agent
- `mcp-gateway-v2-travel-assistant-agent` - Travel Assistant Agent

### Examples for Other Services

**Auth Server:**
```bash
# Build and push
make build-push IMAGE=auth

# Force redeploy
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-auth \
  --force-new-deployment \
  --region us-east-1

# Monitor
watch -n 5 'aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-auth \
  --region us-east-1 \
  --query "services[0].{Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount}" \
  --output table'
```

**MCP Gateway:**
```bash
# Build and push
make build-push IMAGE=mcpgw

# Force redeploy
aws ecs update-service \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-mcpgw \
  --force-new-deployment \
  --region us-east-1
```

## Deployment States

Understanding deployment status:

- **PENDING**: Tasks are being provisioned but not yet running
- **RUNNING**: Tasks are actively running
- **DRAINING**: Old tasks are being gracefully shut down
- **IN_PROGRESS**: Deployment is ongoing
- **COMPLETED**: Deployment finished successfully
- **FAILED**: Deployment encountered errors

## Troubleshooting

### Deployment Stuck

If deployment appears stuck:

```bash
# Check service events
aws ecs describe-services \
  --cluster mcp-gateway-ecs-cluster \
  --service mcp-gateway-v2-registry \
  --region us-east-1 \
  --query 'services[0].events[:10]' \
  --output table

# Check task failures
aws ecs list-tasks \
  --cluster mcp-gateway-ecs-cluster \
  --service-name mcp-gateway-v2-registry \
  --region us-east-1 \
  --desired-status STOPPED \
  --query 'taskArns[:5]' \
  --output text | xargs -I {} aws ecs describe-tasks \
    --cluster mcp-gateway-ecs-cluster \
    --tasks {} \
    --region us-east-1
```

### View Logs

View CloudWatch logs for the registry service:

```bash
./view-cloudwatch-logs.sh mcp-gateway-v2-registry 50
```

Or using AWS CLI directly:

```bash
aws logs tail /ecs/mcp-gateway-v2-registry \
  --follow \
  --format short \
  --region us-east-1
```

## Related Scripts

- `view-cloudwatch-logs.sh` - View ECS service CloudWatch logs
- `run-aoss-cli.sh` - Run OpenSearch Serverless CLI operations
- `get-m2m-token.sh` - Get machine-to-machine authentication token
