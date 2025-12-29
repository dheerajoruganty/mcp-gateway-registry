# Rollback Tag for OpenSearch Production Cluster Migration

**Created**: 2025-12-26
**Purpose**: Store git tag reference for rollback if production OpenSearch cluster migration encounters issues

## Tag Information

**Tag Name**: `pre-opensearch-cluster-refactor`

**Commit SHA**: `50e803d8b5fa09360dca12620797ba169cd40e46`

**Tag SHA**: `16f337a07846713a64477708bed764f79d821edf`

**Date**: 2025-12-26 21:52:25 +0000

**Last Commit**: "Add OpenSearch backend to What's New section with doc links"

**Author**: Amit Arora <aroraai@amazon.com>

**Tag Message**:
```
State before migrating to production 3-node OpenSearch cluster with
dedicated ECS infrastructure and Internal ALB
```

## State at This Tag

This tag represents the codebase state with:

### OpenSearch Backend Features (Implemented)
- ✅ OpenSearch backend with hybrid BM25 + k-NN search
- ✅ Repository abstraction layer (file vs OpenSearch backends)
- ✅ 6 OpenSearch indexes: servers, agents, scopes, embeddings, security-scans, federation-config
- ✅ Namespace support for multi-tenancy (OPENSEARCH_NAMESPACE)
- ✅ Documentation: database-design.md and database-abstraction-layer.md
- ✅ Single-node OpenSearch deployment in docker-compose and AWS ECS

### Infrastructure at This Tag
- Single-node OpenSearch container
- Shared ECS cluster (mcp-gateway-ecs-cluster)
- Service Connect for discovery (port 9200)
- EFS-backed storage
- Security plugin disabled
- No authentication

## What's Changing After This Tag

The migration will implement:
- Dedicated 3-node OpenSearch ECS cluster
- Internal Application Load Balancer
- Multi-AZ deployment with high availability
- OpenSearch Security Plugin enabled with authentication
- Separate security groups and network isolation
- S3-backed automated snapshots
- CloudWatch monitoring and alarms

## Rollback Procedures

### Option 1: Rollback to This Tag (Complete Revert)

```bash
# Check current status
git status

# Stash any uncommitted changes
git stash save "Work in progress before rollback"

# Checkout the tag
git checkout pre-opensearch-cluster-refactor

# Create a new branch from this tag
git checkout -b rollback-opensearch-cluster

# Push to remote
git push origin rollback-opensearch-cluster
```

### Option 2: Rollback Specific Files

```bash
# Rollback specific Terraform files
git checkout pre-opensearch-cluster-refactor -- terraform/aws-ecs/opensearch.tf
git checkout pre-opensearch-cluster-refactor -- terraform/aws-ecs/opensearch-cluster.tf
git checkout pre-opensearch-cluster-refactor -- terraform/aws-ecs/opensearch-alb.tf

# Rollback application configuration
git checkout pre-opensearch-cluster-refactor -- registry/core/config.py
git checkout pre-opensearch-cluster-refactor -- .env.example
```

### Option 3: Cherry-pick Fixes Forward

```bash
# If you need to fix specific issues without full rollback
git checkout main
git cherry-pick <commit-sha-of-fix>
```

### Option 4: Terraform Rollback

If Terraform state needs rollback:

```bash
# Destroy new OpenSearch cluster resources
cd terraform/aws-ecs
terraform destroy -target=aws_ecs_cluster.opensearch
terraform destroy -target=aws_lb.opensearch
terraform destroy -target=aws_ecs_service.opensearch_node

# Or restore entire state from backup
terraform state pull > backup-state.json
# ... make fixes ...
terraform state push fixed-state.json
```

## Verification After Rollback

```bash
# Verify tag checkout
git log --oneline -1
# Should show: 50e803d Add OpenSearch backend to What's New section with doc links

# Verify branch
git branch
# Should show current branch or detached HEAD state

# Check Terraform plan
cd terraform/aws-ecs
terraform plan
# Should show single-node OpenSearch, no ALB or dedicated cluster

# Verify application works
cd /home/ubuntu/repos/mcp-gateway-registry
./build_and_run.sh
# Should start with single-node OpenSearch
```

## Files to Watch During Migration

Critical files that will change:
- `terraform/aws-ecs/opensearch-cluster.tf` (NEW)
- `terraform/aws-ecs/opensearch-alb.tf` (NEW)
- `terraform/aws-ecs/opensearch-snapshots.tf` (NEW)
- `terraform/aws-ecs/opensearch-alarms.tf` (NEW)
- `terraform/aws-ecs/security-groups.tf` (UPDATE)
- `terraform/aws-ecs/secrets.tf` (UPDATE)
- `terraform/aws-ecs/iam.tf` (UPDATE)
- `terraform/aws-ecs/outputs.tf` (UPDATE)
- `terraform/aws-ecs/variables.tf` (UPDATE)
- `terraform/aws-ecs/modules/mcp-gateway/registry.tf` (UPDATE)
- `registry/core/config.py` (UPDATE - OpenSearch auth)
- `.env.example` (UPDATE - New env vars)

## Testing Before Final Commit

Before committing migration changes, test:
1. Terraform plan succeeds
2. All 3 OpenSearch nodes start
3. Cluster health is GREEN
4. ALB health checks pass
5. Registry connects via ALB
6. Authentication works
7. Sample queries succeed
8. Snapshots to S3 work

## Emergency Contact

If critical issues arise during production deployment:
- Rollback immediately to this tag
- Document the issue in `.scratchpad/migration-issues.md`
- Review logs: `docker compose logs -f opensearch`
- Check AWS CloudWatch logs
- Review Terraform state: `terraform show`

## Notes

- This tag is LOCAL only - push to remote if needed: `git push origin pre-opensearch-cluster-refactor`
- Keep this tag for at least 90 days after successful migration
- Delete tag only after production cluster is stable for 1 month
- Backup Terraform state before major infrastructure changes

## Related Documents

- [Production Design](.scratchpad/opensearch-production-design.md)
- [Terraform TODO List](.scratchpad/opensearch-terraform-todo.md)
- [Database Design](../docs/database-design.md)
- [Abstraction Layer Design](../docs/design/database-abstraction-layer.md)
