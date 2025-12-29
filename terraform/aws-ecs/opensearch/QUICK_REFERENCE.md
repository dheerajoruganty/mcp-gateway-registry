# OpenSearch Cluster - Quick Reference

Quick commands and endpoints for daily operations.

## Access Information

### Application Endpoint
```
http://opensearch.mcp-gateway-v2.local:9200
```

### Cluster Discovery (Internal)
```
opensearch-node-0.opensearch-discovery.local:9300
opensearch-node-1.opensearch-discovery.local:9300
opensearch-node-2.opensearch-discovery.local:9300
```

## Common Commands

### Health Checks

```bash
# Cluster health
curl http://opensearch.mcp-gateway-v2.local:9200/_cluster/health

# Cluster health (pretty print)
curl http://opensearch.mcp-gateway-v2.local:9200/_cluster/health?pretty

# List nodes
curl http://opensearch.mcp-gateway-v2.local:9200/_cat/nodes?v

# List indices
curl http://opensearch.mcp-gateway-v2.local:9200/_cat/indices?v

# Cluster stats
curl http://opensearch.mcp-gateway-v2.local:9200/_cluster/stats?pretty
```

### AWS CLI Commands

```bash
# Set region
export AWS_REGION=us-east-1

# Check ECS services
aws ecs describe-services \
  --cluster mcp-gateway-opensearch-cluster \
  --services opensearch-node-0 opensearch-node-1 opensearch-node-2

# Check service status (running tasks)
aws ecs list-tasks \
  --cluster mcp-gateway-opensearch-cluster \
  --service-name opensearch-node-0

# View logs
aws logs tail /ecs/opensearch-cluster --follow

# Check ALB target health
aws elbv2 describe-target-health \
  --target-group-arn $(terraform output -raw opensearch_target_group_arn)

# Get secrets (admin password)
aws secretsmanager get-secret-value \
  --secret-id $(terraform output -raw opensearch_admin_secret_arn) \
  --query SecretString \
  --output text | jq -r '.password'
```

### Terraform Commands

```bash
cd terraform/aws-ecs

# Show current state
terraform show

# List all OpenSearch resources
terraform state list | grep opensearch

# Show specific resource
terraform state show aws_ecs_cluster.opensearch

# Show outputs
terraform output

# Specific output
terraform output opensearch_service_endpoint
```

## Monitoring

### CloudWatch Logs

```bash
# Tail all logs
aws logs tail /ecs/opensearch-cluster --follow

# Filter for errors
aws logs tail /ecs/opensearch-cluster --follow --filter-pattern "ERROR"

# Filter for specific node
aws logs tail /ecs/opensearch-cluster --follow --filter-pattern "opensearch-node-0"
```

### CloudWatch Metrics

```bash
# CPU utilization for node 0
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=opensearch-node-0 Name=ClusterName,Value=mcp-gateway-opensearch-cluster \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average

# Memory utilization for node 0
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ServiceName,Value=opensearch-node-0 Name=ClusterName,Value=mcp-gateway-opensearch-cluster \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

## Troubleshooting

### Check if cluster is healthy

```bash
# Should return: "status": "green", "number_of_nodes": 3
curl http://opensearch.mcp-gateway-v2.local:9200/_cluster/health?pretty
```

### Check node roles

```bash
# Should show 3 nodes with role "dim" (data, ingest, master)
curl http://opensearch.mcp-gateway-v2.local:9200/_cat/nodes?v
```

### Check task status

```bash
# All 3 services should show 1/1 running
aws ecs describe-services \
  --cluster mcp-gateway-opensearch-cluster \
  --services opensearch-node-0 opensearch-node-1 opensearch-node-2 \
  --query 'services[*].[serviceName,desiredCount,runningCount]' \
  --output table
```

### Check ALB targets

```bash
# All 3 targets should be "healthy"
aws elbv2 describe-target-health \
  --target-group-arn $(terraform output -raw opensearch_target_group_arn) \
  --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
  --output table
```

### View recent errors

```bash
aws logs tail /ecs/opensearch-cluster --since 10m --filter-pattern "ERROR"
```

## Quick Fixes

### Restart a node

```bash
# Force new deployment (will restart tasks)
aws ecs update-service \
  --cluster mcp-gateway-opensearch-cluster \
  --service opensearch-node-0 \
  --force-new-deployment
```

### Scale cluster (emergency)

```bash
# Increase CPU/memory temporarily
cd terraform/aws-ecs
terraform apply -var="opensearch_cpu=4096" -var="opensearch_memory=8192"
```

### Check DNS resolution

```bash
# From within VPC (e.g., via bastion or ECS exec)
nslookup opensearch.mcp-gateway-v2.local
nslookup opensearch-node-0.opensearch-discovery.local
```

## Index Management

### List all indices

```bash
curl http://opensearch.mcp-gateway-v2.local:9200/_cat/indices?v
```

### Check index health

```bash
# Should show all indices as "green"
curl http://opensearch.mcp-gateway-v2.local:9200/_cat/indices?v&h=index,health,status,docs.count
```

### Get index stats

```bash
curl http://opensearch.mcp-gateway-v2.local:9200/_stats?pretty
```

### Get specific index info

```bash
# Example for mcp-servers-default index
curl http://opensearch.mcp-gateway-v2.local:9200/mcp-servers-default?pretty
```

## Snapshot Management

### Register S3 repository (one-time setup)

```bash
# From within OpenSearch (via API or OpenSearch Dashboards)
PUT _snapshot/s3-snapshots
{
  "type": "s3",
  "settings": {
    "bucket": "mcp-gateway-opensearch-snapshots-{account-id}",
    "region": "us-east-1",
    "role_arn": "{opensearch_task_role_arn}"
  }
}
```

### Create manual snapshot

```bash
PUT _snapshot/s3-snapshots/snapshot-$(date +%Y%m%d-%H%M%S)
{
  "indices": "*",
  "include_global_state": true
}
```

### List snapshots

```bash
GET _snapshot/s3-snapshots/_all
```

## Performance Tuning

### Check cluster performance

```bash
# Node stats
curl http://opensearch.mcp-gateway-v2.local:9200/_nodes/stats?pretty

# Thread pool stats
curl http://opensearch.mcp-gateway-v2.local:9200/_cat/thread_pool?v

# Pending tasks
curl http://opensearch.mcp-gateway-v2.local:9200/_cat/pending_tasks?v
```

### Check slow queries

```bash
# From CloudWatch Logs (if slow log enabled)
aws logs tail /ecs/opensearch-cluster --filter-pattern "took_millis"
```

## Security

### Rotate admin password

```bash
# 1. Generate new password
NEW_PASSWORD=$(openssl rand -base64 32)

# 2. Update secret
aws secretsmanager update-secret \
  --secret-id $(terraform output -raw opensearch_admin_secret_arn) \
  --secret-string "{\"username\":\"admin\",\"password\":\"$NEW_PASSWORD\"}"

# 3. Force new deployment to pick up new password
aws ecs update-service \
  --cluster mcp-gateway-opensearch-cluster \
  --service opensearch-node-0 \
  --force-new-deployment
```

### Check security group rules

```bash
# OpenSearch cluster security group
aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=*opensearch-cluster*" \
  --query 'SecurityGroups[*].[GroupId,GroupName,IpPermissions]' \
  --output table
```

## Alarms

### List all OpenSearch alarms

```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix mcp-gateway-opensearch \
  --query 'MetricAlarms[*].[AlarmName,StateValue]' \
  --output table
```

### Check alarm history

```bash
aws cloudwatch describe-alarm-history \
  --alarm-name mcp-gateway-opensearch-unhealthy-targets \
  --max-records 10
```

## Resource Information

### Get all Terraform outputs

```bash
cd terraform/aws-ecs
terraform output -json | jq
```

### Key outputs

```bash
# Service endpoint
terraform output opensearch_service_endpoint

# Cluster name
terraform output opensearch_cluster_name

# ALB DNS
terraform output opensearch_alb_dns_name

# S3 bucket
terraform output opensearch_snapshots_bucket_name
```

## Emergency Contacts

### Escalation

1. **Level 1**: DevOps on-call
2. **Level 2**: Backend team lead
3. **Level 3**: Infrastructure architect

### Incident Response

1. Check cluster health
2. Review CloudWatch logs for errors
3. Check ECS service status
4. Verify ALB target health
5. If critical: Trigger rollback (see rollback-procedures.md)

---

**Quick Links**:
- [Full Deployment Guide](docs/deployment-guide.md)
- [Architecture Design](docs/architecture-design.md)
- [Rollback Procedures](docs/rollback-procedures.md)
- [Main README](README.md)
