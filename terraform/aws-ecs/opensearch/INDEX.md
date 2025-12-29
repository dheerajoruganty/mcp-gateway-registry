# OpenSearch Production Cluster - Documentation Index

Complete documentation for the MCP Gateway Registry OpenSearch production cluster deployment.

## 📚 Documentation Structure

```
terraform/aws-ecs/opensearch/
├── INDEX.md                        ← You are here
├── README.md                       → Main overview and quick start
├── QUICK_REFERENCE.md             → Daily operations cheat sheet
└── docs/
    ├── deployment-guide.md         → Complete deployment instructions
    ├── architecture-design.md      → Technical architecture details
    └── rollback-procedures.md      → Rollback and recovery procedures
```

## 🚀 Quick Navigation

### For Operators

**Getting Started:**
1. Start with [README.md](README.md) for overview
2. Follow [deployment-guide.md](docs/deployment-guide.md) for deployment
3. Keep [QUICK_REFERENCE.md](QUICK_REFERENCE.md) bookmarked for daily tasks

**Emergency:**
- Go directly to [rollback-procedures.md](docs/rollback-procedures.md)

### For Architects

**Understanding the System:**
1. Read [architecture-design.md](docs/architecture-design.md) for technical details
2. Review [README.md](README.md) for infrastructure overview
3. Check Terraform files in `terraform/aws-ecs/opensearch-*.tf`

### For Developers

**Integration:**
1. [README.md](README.md) - Access endpoints section
2. [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Common API commands
3. ../../docs/database-design.md - Database schema
4. ../../docs/design/database-abstraction-layer.md - Application integration

## 📖 Document Summaries

### [README.md](README.md)
**Main overview document** - Start here!

- Architecture overview
- Quick start guide
- Configuration variables
- Access endpoints
- Resource list
- Monitoring overview
- Cost estimates

**Best for**: First-time readers, deployment overview

---

### [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
**Daily operations cheat sheet**

- Common commands
- Health check commands
- AWS CLI examples
- Troubleshooting quick fixes
- Monitoring commands
- Index management

**Best for**: Daily operations, quick lookups, troubleshooting

---

### [docs/deployment-guide.md](docs/deployment-guide.md)
**Complete deployment instructions** - Most comprehensive

- Executive summary
- Detailed implementation phases (1-8)
- Step-by-step deployment
- Verification checklist
- Troubleshooting guide
- Cost analysis
- Success metrics

**Best for**: Initial deployment, comprehensive reference

---

### [docs/architecture-design.md](docs/architecture-design.md)
**Technical architecture details**

- Current state analysis
- Production architecture design
- Component design (8 sections)
- Configuration details
- Migration strategy
- Future enhancements

**Best for**: Architecture reviews, design decisions, technical deep-dives

---

### [docs/rollback-procedures.md](docs/rollback-procedures.md)
**Emergency rollback guide**

- Git tag information (`pre-opensearch-cluster-refactor`)
- 4 rollback procedures
- Verification steps
- File tracking
- Emergency contacts

**Best for**: Emergency rollbacks, disaster recovery

---

## 🗂️ Related Documentation

### Application Layer
- **Database Design**: `../../docs/database-design.md`
  - OpenSearch indexes (6 types)
  - Document schemas
  - Real examples

- **Abstraction Layer**: `../../docs/design/database-abstraction-layer.md`
  - Repository pattern
  - Factory pattern
  - Code organization

### Infrastructure Layer
- **Terraform Files**: `../opensearch-*.tf` (8 files)
  - Phase 1: opensearch-cluster.tf
  - Phase 2: opensearch-security-groups.tf, opensearch-secrets.tf, opensearch-iam.tf
  - Phase 3: opensearch-alb.tf
  - Phase 4: opensearch-services.tf
  - Phase 5: opensearch-snapshots.tf
  - Phase 6: opensearch-alarms.tf

## 🎯 Common Use Cases

### "I need to deploy OpenSearch for the first time"
1. Read: [README.md](README.md) - Overview
2. Follow: [docs/deployment-guide.md](docs/deployment-guide.md) - Step by step
3. Verify: [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Health checks

### "I need to troubleshoot an issue"
1. Start: [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Quick fixes
2. If needed: [docs/deployment-guide.md](docs/deployment-guide.md) - Troubleshooting section
3. Emergency: [docs/rollback-procedures.md](docs/rollback-procedures.md)

### "I need to understand the architecture"
1. Overview: [README.md](README.md) - Architecture section
2. Deep dive: [docs/architecture-design.md](docs/architecture-design.md)
3. Code: Review Terraform files

### "I need to perform daily operations"
1. Keep open: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
2. Monitoring: [README.md](README.md) - Monitoring section

### "Something went wrong, I need to rollback"
1. Go to: [docs/rollback-procedures.md](docs/rollback-procedures.md)
2. Choose: Option 1, 2, or 3 based on situation
3. Verify: Follow verification steps

### "I need to scale the cluster"
1. Check: [README.md](README.md) - Maintenance → Scaling section
2. Variables: Update `opensearch_node_count`, `opensearch_cpu`, `opensearch_memory`
3. Deploy: `terraform plan && terraform apply`

### "I need to integrate my application"
1. Endpoint: [README.md](README.md) - Access Endpoints
2. Schema: `../../docs/database-design.md`
3. Code: `../../docs/design/database-abstraction-layer.md`

## 📋 Quick Facts

**Cluster Configuration:**
- Nodes: 3 (across 3 AZs)
- CPU: 2 vCPU per node (6 total)
- Memory: 4 GB per node (12 total)
- Storage: EFS with dedicated access points
- Version: OpenSearch 2.11.1

**Access:**
- Application: `http://opensearch.mcp-gateway-v2.local:9200`
- Cluster: `opensearch-node-{0,1,2}.opensearch-discovery.local:9300`

**Monitoring:**
- Log Group: `/ecs/opensearch-cluster`
- Alarms: 7 CloudWatch alarms
- Retention: 30 days

**Security:**
- VPC-only (no public access)
- Secrets Manager for credentials
- Dedicated security groups
- IAM roles with least-privilege

**Cost:**
- Monthly: ~$477 (us-east-1)
- 40% cheaper than managed service

**Rollback Tag:**
- `pre-opensearch-cluster-refactor`
- Commit: `50e803d8b5fa09360dca12620797ba169cd40e46`

## 🔗 External Resources

- [OpenSearch Documentation](https://opensearch.org/docs/latest/)
- [ECS Fargate Documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [Application Load Balancer Guide](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

## 📞 Support

- Infrastructure: DevOps team
- Application: Backend team
- Security: Security team
- Monitoring: SRE team

---

**Last Updated**: 2025-12-26
**Version**: 1.0
**Status**: Production Ready
**Maintained By**: Infrastructure Team
