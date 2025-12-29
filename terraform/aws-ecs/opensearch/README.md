# OpenSearch Production Cluster Infrastructure

This directory contains documentation for the production-ready 3-node OpenSearch cluster deployment for the MCP Gateway Registry.

## Overview

The OpenSearch cluster provides distributed search capabilities with high availability, security, and scalability. It replaces the single-node development deployment with a production-grade architecture.

### Key Features

- **High Availability**: 3-node cluster across 3 Availability Zones
- **Security**: VPC-only access, Secrets Manager, dedicated security groups
- **Scalability**: Configurable resources, EFS-backed storage, S3 snapshots
- **Monitoring**: CloudWatch alarms for health, CPU, and memory
- **Load Balancing**: Internal ALB with DNS-based access

### Architecture

```
Application Services
    ↓
opensearch.mcp-gateway-v2.local:9200
    ↓
Internal Application Load Balancer
    ↓
3 OpenSearch Nodes (Fargate)
    ├─ Node 0 (us-east-1a)
    ├─ Node 1 (us-east-1b)
    └─ Node 2 (us-east-1c)
```

## Documentation

### Core Documents

1. **[Deployment Guide](docs/deployment-guide.md)**
   - Complete deployment instructions
   - Prerequisites and setup
   - Verification checklist
   - Troubleshooting guide
   - Cost analysis

2. **[Architecture Design](docs/architecture-design.md)**
   - Production architecture overview
   - Component design details
   - DNS and networking strategy
   - Security implementation
   - Migration strategy

3. **[Rollback Procedures](docs/rollback-procedures.md)**
   - Git tag reference for rollback
   - Rollback procedures (3 options)
   - Verification steps
   - Emergency contact information

## Terraform Files

The OpenSearch infrastructure is implemented across 8 Terraform files in the parent directory (`terraform/aws-ecs/`):

### Phase 1: Foundation
- **opensearch-cluster.tf**
  - Dedicated ECS cluster
  - Service discovery namespace (`opensearch-discovery.local`)
  - EFS access points (3)
  - CloudWatch log group

### Phase 2: Security & Networking
- **opensearch-security-groups.tf**
  - ALB security group
  - Cluster security group
  - Integration with registry/auth services

- **opensearch-secrets.tf**
  - Admin credentials (Secrets Manager)
  - Service account credentials
  - Random password generators

- **opensearch-iam.tf**
  - Task execution role
  - Task role (S3 snapshot access)
  - Policies for secrets and logging

### Phase 3: Load Balancing
- **opensearch-alb.tf**
  - Internal Application Load Balancer
  - Target group with health checks
  - HTTP listener (port 9200)
  - Route53 DNS record

### Phase 4: Services
- **opensearch-services.tf**
  - 3 task definitions (one per node)
  - 3 ECS services
  - Container configuration
  - Environment variables for cluster formation

### Phase 5: Backups
- **opensearch-snapshots.tf**
  - S3 bucket for snapshots
  - Versioning and encryption
  - Lifecycle policies
  - Bucket policies

### Phase 6: Monitoring
- **opensearch-alarms.tf**
  - SNS topic for alerts
  - Unhealthy targets alarm
  - CPU and memory alarms (per node)

## Quick Start

### Prerequisites

1. AWS credentials configured
2. Terraform 1.0+ installed
3. Existing VPC and EFS infrastructure
4. AWS_REGION set to us-east-1

### Deploy

```bash
# Set environment
export AWS_REGION=us-east-1
export TF_VAR_alarm_email="your-email@example.com"  # Optional

# Navigate to terraform directory
cd terraform/aws-ecs

# Review plan
terraform plan

# Deploy
terraform apply
```

### Verify

```bash
# Wait 3-5 minutes for cluster formation, then:

# Check cluster health
curl http://opensearch.mcp-gateway-v2.local:9200/_cluster/health

# Expected output:
# {
#   "cluster_name": "mcp-gateway-opensearch",
#   "status": "green",
#   "number_of_nodes": 3
# }

# List nodes
curl http://opensearch.mcp-gateway-v2.local:9200/_cat/nodes?v
```

## Configuration Variables

The following variables can be customized in `terraform.tfvars`:

```hcl
# Number of OpenSearch nodes (default: 3)
opensearch_node_count = 3

# CPU per node in vCPU units (default: 2048 = 2 vCPU)
opensearch_cpu = 2048

# Memory per node in MB (default: 4096 = 4 GB)
opensearch_memory = 4096

# OpenSearch version (default: "2.11.1")
opensearch_version = "2.11.1"

# Optional: Email for alarm notifications
alarm_email = "team@example.com"
```

## Access Endpoints

### Application Access (via ALB)
- **Endpoint**: `http://opensearch.mcp-gateway-v2.local:9200`
- **Purpose**: Application queries and writes
- **Used by**: Registry service, Auth service
- **Protocol**: HTTP (internal VPC only)

### Cluster Discovery (internal)
- **Endpoints**:
  - `opensearch-node-0.opensearch-discovery.local:9300`
  - `opensearch-node-1.opensearch-discovery.local:9300`
  - `opensearch-node-2.opensearch-discovery.local:9300`
- **Purpose**: Node-to-node cluster formation
- **Protocol**: OpenSearch transport protocol

## Resources Created

- 1 dedicated ECS cluster
- 3 ECS services (one per node)
- 3 task definitions
- 1 Internal Application Load Balancer
- 1 target group
- 2 security groups
- 3 EFS access points
- 1 S3 bucket (snapshots)
- 2 Secrets Manager secrets
- 2 IAM roles
- 7 CloudWatch alarms
- 1 SNS topic
- Multiple security group rules

## Cost Estimate

**Monthly cost (us-east-1)**: ~$477

| Resource | Cost |
|----------|------|
| Fargate compute (6 vCPU) | $177 |
| Fargate memory (12 GB) | $234 |
| Internal ALB | $30 |
| EFS storage (100 GB) | $30 |
| Other (S3, logs) | $6 |

**Comparison**:
- Single-node development: ~$160/month
- **3-node production: ~$477/month** ← Current implementation
- Managed OpenSearch Service: ~$800/month

## Rollback

If issues occur during deployment:

```bash
# Option 1: Revert to tagged version
git checkout pre-opensearch-cluster-refactor

# Option 2: Destroy new cluster resources
terraform destroy \
  -target=aws_ecs_cluster.opensearch \
  -target=aws_ecs_service.opensearch_node

# Option 3: Keep cluster, revert application config
# Update registry OPENSEARCH_URL to old endpoint
```

See [Rollback Procedures](docs/rollback-procedures.md) for detailed instructions.

## Monitoring

### CloudWatch Alarms

The deployment creates 7 alarms:

1. **Unhealthy Targets** - ALB target health
2. **CPU High (Node 0)** - CPU > 80% for node 0
3. **CPU High (Node 1)** - CPU > 80% for node 1
4. **CPU High (Node 2)** - CPU > 80% for node 2
5. **Memory High (Node 0)** - Memory > 85% for node 0
6. **Memory High (Node 1)** - Memory > 85% for node 1
7. **Memory High (Node 2)** - Memory > 85% for node 2

### CloudWatch Logs

All container logs are sent to:
- **Log Group**: `/ecs/opensearch-cluster`
- **Retention**: 30 days

View logs:
```bash
aws logs tail /ecs/opensearch-cluster --follow
```

## Security

### Network Security
- **VPC-only access**: No public internet exposure
- **Internal ALB**: Private subnets only
- **Security groups**: Least-privilege access rules

### Secrets Management
- **Admin credentials**: Stored in Secrets Manager
- **Service credentials**: Stored in Secrets Manager
- **Password rotation**: 90-day policy recommended

### IAM Roles
- **Task execution role**: Pull images, read secrets, write logs
- **Task role**: S3 snapshot access

## Troubleshooting

### Common Issues

**Cluster health is RED**
- Wait 3-5 minutes for cluster formation
- Check CloudWatch logs for errors
- Verify all 3 services are running

**Health checks failing**
- Initial startup takes 2-3 minutes
- Check security group allows ALB → cluster on port 9200
- Verify target group health check path: `/_cluster/health`

**Can't connect from application**
- Verify DNS resolves: `nslookup opensearch.mcp-gateway-v2.local`
- Check security groups allow registry/auth → ALB
- Verify secrets are readable by registry service

See [Deployment Guide](docs/deployment-guide.md) for comprehensive troubleshooting.

## Maintenance

### Regular Tasks

**Daily**:
- Monitor CloudWatch alarms
- Check cluster health status

**Weekly**:
- Review CloudWatch metrics
- Check disk usage on EFS
- Verify snapshots are being created

**Monthly**:
- Review and rotate secrets
- Update OpenSearch version if needed
- Review and optimize index settings
- Cost analysis and optimization

### Scaling

To scale the cluster:

1. Update `opensearch_node_count` variable
2. Adjust CPU/memory if needed
3. Run `terraform plan` and `terraform apply`
4. Wait for new nodes to join cluster
5. Rebalance shards if necessary

## Support

For issues or questions:
- Infrastructure: DevOps team
- Application integration: Backend team
- Security: Security team
- Monitoring: SRE team

## References

- [OpenSearch Documentation](https://opensearch.org/docs/latest/)
- [ECS Fargate Guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [Database Design](../../docs/database-design.md)
- [Abstraction Layer](../../docs/design/database-abstraction-layer.md)

---

**Last Updated**: 2025-12-26
**Version**: 1.0
**Status**: Production Ready
