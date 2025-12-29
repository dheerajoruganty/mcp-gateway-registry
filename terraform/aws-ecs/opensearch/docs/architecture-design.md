# Production OpenSearch Cluster Design

**Created**: 2025-12-26
**Context**: Design for deploying production-ready OpenSearch cluster in AWS ECS with dedicated infrastructure

## Current State Analysis

### Existing OpenSearch Deployment Issues

**Current Architecture**:
- Single-node OpenSearch container on shared ECS cluster (mcp-gateway-ecs-cluster)
- Security plugin disabled (OPENSEARCH_SECURITY_DISABLED=true)
- No authentication or authorization
- EFS-backed storage (/opensearch-data)
- Accessible via Service Connect on port 9200
- Shared compute resources with application services

**Production Concerns**:
1. **Availability**: Single point of failure, no redundancy
2. **Security**: No authentication, disabled security plugin, shared network with apps
3. **Scalability**: Single node cannot scale horizontally
4. **Performance**: Shared cluster resources, EFS not optimized for search workloads
5. **Isolation**: Application failures can impact search, no resource guarantees

## Production Architecture Design

### Overview

Deploy OpenSearch as a dedicated 3-node cluster on separate ECS infrastructure with internal ALB for load balancing and service discovery. Maintain VPC-only access with proper authentication and network isolation.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        VPC (10.0.0.0/16)                     │
│                                                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │          Application ECS Cluster                    │     │
│  │  - mcp-gateway-v2-registry                          │     │
│  │  - mcp-gateway-v2-auth                              │     │
│  │  - MCP servers (5)                                  │     │
│  │  - Agents (2)                                       │     │
│  └───────────┬────────────────────────────────────────┘     │
│              │                                                │
│              │ Internal ALB Connection                        │
│              │ (opensearch.mcp-gateway-v2.local)             │
│              ▼                                                │
│  ┌────────────────────────────────────────────────────┐     │
│  │      Internal Application Load Balancer             │     │
│  │      Scheme: internal                               │     │
│  │      DNS: opensearch.mcp-gateway-v2.local           │     │
│  │      Port: 9200 (HTTPS)                             │     │
│  └───────────┬────────────────────────────────────────┘     │
│              │                                                │
│              │ Round-robin to nodes                          │
│              ▼                                                │
│  ┌────────────────────────────────────────────────────┐     │
│  │   OpenSearch ECS Cluster (Dedicated)               │     │
│  │   ┌──────────┐  ┌──────────┐  ┌──────────┐        │     │
│  │   │ OS Node1 │  │ OS Node2 │  │ OS Node3 │        │     │
│  │   │  Master  │  │  Master  │  │  Master  │        │     │
│  │   │   Data   │  │   Data   │  │   Data   │        │     │
│  │   └────┬─────┘  └────┬─────┘  └────┬─────┘        │     │
│  │        │             │             │                │     │
│  │        └─────────────┴─────────────┘                │     │
│  │              Cluster Formation                      │     │
│  │        (discovery.seed_hosts via ECS DNS)           │     │
│  └────────────────────────────────────────────────────┘     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Component Design

#### 1. Dedicated OpenSearch ECS Cluster

**Cluster Configuration**:
- Name: `mcp-gateway-opensearch-cluster`
- Capacity Provider: AWS Fargate
- Container Insights: Enabled
- Purpose: Isolate OpenSearch workload from application services

**Benefits**:
- Independent scaling of search infrastructure
- Fault isolation (app failures don't affect search)
- Resource guarantees for OpenSearch
- Simplified capacity planning
- Independent upgrade cycles

#### 2. Multi-Node OpenSearch Deployment

**Cluster Topology**: 3 nodes (minimum for production)

**Node Configuration**:
- CPU: 2 vCPU per node (6 vCPU total)
- Memory: 4 GB per node (12 GB total)
- Storage: EFS with dedicated access point per node
- Roles: All nodes are master-eligible + data nodes

**OpenSearch Configuration**:
```yaml
cluster.name: mcp-gateway-opensearch
cluster.initial_master_nodes:
  - opensearch-node-1
  - opensearch-node-2
  - opensearch-node-3
discovery.seed_hosts:
  - opensearch-node-1.opensearch-discovery.local
  - opensearch-node-2.opensearch-discovery.local
  - opensearch-node-3.opensearch-discovery.local
node.roles: [master, data, ingest]
plugins.security.disabled: false
```

**Service Placement**:
- Each node in different Availability Zone (high availability)
- Anti-affinity rules prevent multiple nodes on same host
- Fixed task count: 3 (one per node)

#### 3. Internal Application Load Balancer

**ALB Configuration**:
- Scheme: `internal` (VPC-only access)
- Subnets: Private subnets in 3 AZs
- Security Group: Allow port 9200 from registry/auth services only
- DNS: `opensearch.mcp-gateway-v2.local` (Route 53 private hosted zone)
- Protocol: HTTPS with ACM certificate
- Health Check: `GET /_cluster/health` (expect 200)

**Target Group**:
- Protocol: HTTP (TLS termination at ALB)
- Port: 9200
- Health Check Interval: 30 seconds
- Unhealthy Threshold: 3
- Healthy Threshold: 2
- Targets: 3 OpenSearch ECS tasks (dynamic registration)

**Benefits**:
- Load distribution across 3 nodes
- Health checking and automatic failover
- Single endpoint for applications (no service discovery changes)
- TLS termination (encrypt in-transit)
- Connection draining during deployments

#### 4. Authentication & Security

**Security Plugin Configuration**:
- Enable OpenSearch Security Plugin (`plugins.security.disabled: false`)
- Internal Users Database for basic authentication
- Service accounts for registry/auth services
- TLS between ALB and nodes (mTLS optional)

**Credentials Management**:
- Store credentials in AWS Secrets Manager
- Secret: `mcp-gateway/opensearch/admin` (admin user)
- Secret: `mcp-gateway/opensearch/service` (app service account)
- Rotation policy: 90 days
- Registry service reads from Secrets Manager on startup

**Security Groups**:

```
SG: opensearch-alb-sg
- Ingress: Port 9200 from registry-sg, auth-sg
- Egress: Port 9200 to opensearch-cluster-sg

SG: opensearch-cluster-sg
- Ingress: Port 9200 from opensearch-alb-sg
- Ingress: Port 9300 from opensearch-cluster-sg (cluster transport)
- Egress: All to 0.0.0.0/0 (for AWS APIs)

SG: registry-sg (existing, update)
- Egress: Port 9200 to opensearch-alb-sg

SG: auth-sg (existing, update)
- Egress: Port 9200 to opensearch-alb-sg
```

**Network Isolation**:
- OpenSearch nodes in private subnets only
- No internet gateway access
- VPC endpoints for AWS services (ECR, Secrets Manager, CloudWatch)
- No public IPs assigned to tasks

#### 5. Storage Architecture

**EFS Configuration**:
- File System: Existing `mcp-gateway-efs`
- New Access Points (3):
  - `/opensearch-data/node-1` (UID 1000, GID 1000)
  - `/opensearch-data/node-2` (UID 1000, GID 1000)
  - `/opensearch-data/node-3` (UID 1000, GID 1000)
- Performance Mode: General Purpose
- Throughput Mode: Bursting (consider Provisioned for high load)
- Encryption: At-rest (AWS KMS)

**Considerations**:
- EFS provides shared storage but not optimized for search workloads
- For production scale, consider Amazon OpenSearch Service or EBS volumes
- Current approach acceptable for <100GB indexes

#### 6. Service Discovery

**ECS Service Connect**:
- Namespace: `opensearch-discovery` (new namespace for cluster formation)
- Service: `opensearch-node-{1,2,3}`
- Port: 9300 (cluster transport)
- Purpose: Node-to-node discovery

**Application Access**:
- DNS: `opensearch.mcp-gateway-v2.local` (Route 53 private hosted zone)
- Alias Record: Points to Internal ALB
- Applications use single endpoint, ALB handles routing

#### 7. Monitoring & Observability

**CloudWatch Metrics**:
- ECS Container Insights (cluster-level)
- Custom metrics via OpenSearch API:
  - Cluster health status
  - Node count
  - Index count and size
  - Search query latency
  - Indexing rate

**CloudWatch Alarms**:
1. Cluster Health != green (P1)
2. Available nodes < 2 (P1)
3. CPU > 80% for 5 minutes (P2)
4. Memory > 85% for 5 minutes (P2)
5. Search latency > 1s (P2)
6. Storage > 80% (P3)

**Logging**:
- Container logs to CloudWatch Logs
- Log Groups:
  - `/ecs/opensearch-cluster/node-1`
  - `/ecs/opensearch-cluster/node-2`
  - `/ecs/opensearch-cluster/node-3`
- Retention: 30 days
- OpenSearch slow logs enabled (>500ms queries)

#### 8. Backup & Disaster Recovery

**Snapshot Configuration**:
- S3 Bucket: `mcp-gateway-opensearch-snapshots-{account-id}`
- Repository: Register S3 as snapshot repository
- Schedule: Daily automated snapshots (midnight UTC)
- Retention: 7 daily, 4 weekly, 3 monthly
- IAM Role: OpenSearch tasks assume role with S3 access

**Restore Procedures**:
- Documented runbook for cluster rebuild from snapshots
- Tested quarterly
- RTO: 1 hour, RPO: 24 hours

### Configuration Changes for Existing Services

**Registry Service (registry/core/config.py)**:
```python
# Before
opensearch_url: str = "http://opensearch:9200"

# After
opensearch_url: str = "https://opensearch.mcp-gateway-v2.local:9200"
opensearch_username: str = Field(default="", env="OPENSEARCH_USERNAME")
opensearch_password: str = Field(default="", env="OPENSEARCH_PASSWORD")
```

**Environment Variables**:
- `OPENSEARCH_URL=https://opensearch.mcp-gateway-v2.local:9200`
- `OPENSEARCH_USERNAME` (from Secrets Manager)
- `OPENSEARCH_PASSWORD` (from Secrets Manager)
- `OPENSEARCH_VERIFY_CERTS=true`
- `OPENSEARCH_USE_SSL=true`

### Cost Estimation

**Monthly Costs** (us-east-1 pricing):

| Resource | Quantity | Unit Cost | Monthly Cost |
|----------|----------|-----------|--------------|
| Fargate vCPU (6 vCPU) | 4,380 hours | $0.04048/hour | $177.30 |
| Fargate Memory (12 GB) | 4,380 hours | $0.004445/GB-hour | $233.77 |
| Application Load Balancer | 1 | $16.20/month + data | ~$30.00 |
| EFS Storage (100 GB) | 100 GB | $0.30/GB-month | $30.00 |
| Data Transfer (minimal) | - | - | $5.00 |
| **Total** | | | **~$476/month** |

**Comparison**:
- Current single-node: ~$160/month
- Production 3-node: ~$476/month
- Amazon OpenSearch Service (equivalent): ~$800/month

### Migration Strategy

**Phase 1: Parallel Deployment** (Week 1)
1. Deploy new OpenSearch cluster infrastructure
2. Configure Internal ALB
3. Create new security groups and update existing
4. Deploy 3-node OpenSearch cluster
5. Verify cluster health

**Phase 2: Data Migration** (Week 2)
1. Create snapshot of existing OpenSearch data
2. Restore snapshot to new cluster
3. Verify data integrity (document counts, index health)
4. Run parallel queries to compare results

**Phase 3: Application Cutover** (Week 3)
1. Update registry/auth service environment variables
2. Deploy new registry/auth versions (blue/green)
3. Monitor logs and metrics
4. Rollback plan: Revert env vars to old endpoint

**Phase 4: Decommission** (Week 4)
1. Monitor new cluster for 1 week
2. Decommission old single-node OpenSearch service
3. Remove old EFS access point (after backup)
4. Update documentation

### Rollback Plan

If issues occur during migration:
1. Revert registry/auth env vars to old endpoint (30 seconds)
2. Restart registry/auth services (2 minutes)
3. Verify application functionality
4. Investigate issues in new cluster offline
5. Old cluster remains running until successful migration

### Success Criteria

- [ ] All 3 OpenSearch nodes healthy and clustered
- [ ] Cluster health: GREEN status
- [ ] All indexes replicated (1 primary + 1 replica per shard)
- [ ] Query latency < 500ms (p95)
- [ ] Zero data loss during migration
- [ ] Applications successfully connect via ALB
- [ ] Authentication working for all services
- [ ] CloudWatch alarms configured and tested
- [ ] Automated snapshots working
- [ ] Disaster recovery tested

### Future Enhancements

**Short-term** (3-6 months):
1. Implement auto-scaling based on CPU/memory metrics
2. Add read replicas for high query load
3. Optimize shard configuration based on index size
4. Implement query result caching

**Long-term** (6-12 months):
1. Evaluate Amazon OpenSearch Service for managed option
2. Consider dedicated master nodes (5-node cluster)
3. Implement cross-region replication for DR
4. Advanced monitoring with OpenSearch Dashboards

### References

- [OpenSearch Cluster Formation](https://opensearch.org/docs/latest/tuning-your-cluster/cluster/)
- [AWS ECS Service Discovery](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-discovery.html)
- [OpenSearch Security Plugin](https://opensearch.org/docs/latest/security/index/)
- [ECS Fargate Pricing](https://aws.amazon.com/fargate/pricing/)
