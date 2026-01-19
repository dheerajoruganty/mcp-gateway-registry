# MCP Gateway Registry EKS Deployment Guide

This guide documents the steps to deploy MCP Gateway Registry on Amazon EKS using the ai-on-eks blueprints.

## Prerequisites

- AWS CLI configured with appropriate permissions
- Terraform installed
- Route53 hosted zone for your domain

## Step 1: Clone AI on EKS Repository

```bash
cd /home/ubuntu
git clone https://github.com/awslabs/ai-on-eks.git
cd ai-on-eks
```

## Step 2: Configure Custom Blueprint

Create the custom terraform directory:

```bash
cd infra/custom
mkdir -p ./terraform/_LOCAL
cp -r ../base/terraform/* ./terraform/_LOCAL
```

Create `blueprint.tfvars` in `/home/ubuntu/ai-on-eks/infra/custom/`:

```hcl
# MCP Gateway Registry EKS Configuration
name                  = "mcp-gateway"
region                = "us-east-1"
eks_cluster_version   = "1.32"

# VPC Configuration
vpc_cidr                 = "10.1.0.0"
availability_zones_count = 2
single_nat_gateway       = true

# Disable GPU/AI-specific addons (not needed for MCP Gateway)
enable_nvidia_device_plugin  = false
enable_nvidia_dcgm_exporter  = false
enable_nvidia_gpu_operator   = false

# Enable AWS Load Balancer Controller (required for ALB Ingress)
enable_aws_load_balancer_controller = true

# Disable other addons not needed
enable_aws_efs_csi_driver           = false
enable_aws_fsx_csi_driver           = false
enable_amazon_prometheus            = false
enable_kube_prometheus_stack        = false
enable_jupyterhub                   = false
enable_mlflow_tracking              = false
enable_kuberay_operator             = false
enable_argo_workflows               = false
enable_argo_events                  = false
```

## Step 3: Deploy EKS Cluster

Initialize and apply terraform modules in sequence:

```bash
cd /home/ubuntu/ai-on-eks/infra/custom/terraform/_LOCAL

# Initialize terraform
terraform init -upgrade

# Apply VPC module
terraform apply -auto-approve -var-file=../../blueprint.tfvars -target="module.vpc"

# Apply EKS module
terraform apply -auto-approve -var-file=../../blueprint.tfvars -target="module.eks"

# Apply Karpenter module
terraform apply -auto-approve -var-file=../../blueprint.tfvars -target="module.karpenter"

# Apply ArgoCD module
terraform apply -auto-approve -var-file=../../blueprint.tfvars -target="module.argocd"

# Final apply for remaining resources
terraform apply -auto-approve -var-file=../../blueprint.tfvars
```

## Step 4: Install kubectl and Helm

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/v1.32.0/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/kubectl

# Install helm
curl -fsSL https://get.helm.sh/helm-v3.16.4-linux-amd64.tar.gz | tar -xzf - linux-amd64/helm
sudo mv linux-amd64/helm /usr/local/bin/helm
rm -rf linux-amd64
```

## Step 5: Configure kubectl

```bash
aws eks --region us-east-1 update-kubeconfig --name mcp-gateway
```

Verify cluster access:

```bash
kubectl get nodes
```

## Step 6: Request ACM Certificate

Replace `YOUR_DOMAIN` with your actual domain:

```bash
# Request wildcard certificate
aws acm request-certificate \
  --domain-name "*.YOUR_DOMAIN" \
  --validation-method DNS \
  --region us-east-1
```

Get the validation DNS record:

```bash
CERT_ARN="<certificate-arn-from-previous-command>"
aws acm describe-certificate \
  --certificate-arn "$CERT_ARN" \
  --region us-east-1 \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord'
```

Create the DNS validation record in Route53:

```bash
HOSTED_ZONE_ID="<your-hosted-zone-id>"

cat > /tmp/acm-validation.json << EOF
{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "<validation-record-name>",
      "Type": "CNAME",
      "TTL": 300,
      "ResourceRecords": [{"Value": "<validation-record-value>"}]
    }
  }]
}
EOF

aws route53 change-resource-record-sets \
  --hosted-zone-id $HOSTED_ZONE_ID \
  --change-batch file:///tmp/acm-validation.json
```

Wait for certificate validation:

```bash
aws acm wait certificate-validated --certificate-arn "$CERT_ARN" --region us-east-1
```

## Step 7: Deploy MCP Gateway Registry Stack

Update helm dependencies:

```bash
cd /home/ubuntu/mcp-gateway-registry-MAIN
helm dependency update charts/mcp-gateway-registry-stack
```

Install the helm chart:

```bash
helm install mcp-stack charts/mcp-gateway-registry-stack \
  --set global.domain=YOUR_DOMAIN \
  --set global.secretKey=$(openssl rand -hex 16) \
  --set "global.ingress.annotations.alb\.ingress\.kubernetes\.io/certificate-arn=<certificate-arn>" \
  --create-namespace \
  --namespace mcp-gateway \
  --timeout 10m
```

Monitor deployment:

```bash
kubectl get pods -n mcp-gateway -w
```

## Step 8: Configure Route53 DNS Records

Get the ALB addresses:

```bash
kubectl get ingress -n mcp-gateway
```

Create DNS CNAME records for each service:

```bash
HOSTED_ZONE_ID="<your-hosted-zone-id>"

cat > /tmp/dns-records.json << EOF
{
  "Changes": [
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "auth-server.YOUR_DOMAIN.",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "<auth-server-alb-address>"}]
      }
    },
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "keycloak.YOUR_DOMAIN.",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "<keycloak-alb-address>"}]
      }
    },
    {
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "mcpregistry.YOUR_DOMAIN.",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "<registry-alb-address>"}]
      }
    }
  ]
}
EOF

aws route53 change-resource-record-sets \
  --hosted-zone-id $HOSTED_ZONE_ID \
  --change-batch file:///tmp/dns-records.json
```

## Step 9: Verify Deployment

Test service health endpoints:

```bash
curl -s -o /dev/null -w "%{http_code}" https://mcpregistry.YOUR_DOMAIN/health
curl -s -o /dev/null -w "%{http_code}" https://auth-server.YOUR_DOMAIN/health
curl -s -o /dev/null -w "%{http_code}" https://keycloak.YOUR_DOMAIN/realms/mcp-gateway
```

All endpoints should return `200`.

## Service Endpoints

After deployment, the following endpoints are available:

| Service | URL |
|---------|-----|
| MCP Registry | `https://mcpregistry.YOUR_DOMAIN` |
| Auth Server | `https://auth-server.YOUR_DOMAIN` |
| Keycloak Admin | `https://keycloak.YOUR_DOMAIN/admin` |

## Default Credentials

The Keycloak setup creates the following test users:

| User | Password | Role |
|------|----------|------|
| admin | changeme | Administrator |
| testuser | testpass | Standard user |

**Important:** Change these default passwords in production.

## Cleanup

To destroy the infrastructure:

```bash
# Uninstall helm release
helm uninstall mcp-stack -n mcp-gateway

# Delete namespace
kubectl delete namespace mcp-gateway

# Destroy terraform resources
cd /home/ubuntu/ai-on-eks/infra/custom/terraform/_LOCAL
terraform destroy -var-file=../../blueprint.tfvars
```

## Troubleshooting

### Pods stuck in Pending state

Check if Karpenter is provisioning nodes:

```bash
kubectl get nodepools
kubectl get nodeclaims
kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter
```

### Keycloak setup job fails

The setup job may fail if Keycloak is not ready. Delete the failed pod to trigger a retry:

```bash
kubectl delete pod -n mcp-gateway -l job-name=setup-keycloak
```

### Image pull errors

Check node disk space. Karpenter will automatically provision new nodes if needed.

### Certificate validation pending

Ensure the DNS validation record is correctly created in Route53. Validation typically takes 5-30 minutes.
