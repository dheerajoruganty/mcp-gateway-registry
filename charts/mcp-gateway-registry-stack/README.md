# MCP Gateway Registry Stack Charts

This collection of charts deploys everything needed to install the MCP Gateway Registry using Helm or ArgoCD.

## Prerequisites

### Amazon EKS Cluster

For production deployments, we recommend using the [AWS AI/ML on Amazon EKS](https://github.com/awslabs/ai-on-eks) blueprints to provision a production-ready EKS cluster:

```bash
# Clone AI on EKS repository
git clone https://github.com/awslabs/ai-on-eks.git
cd ai-on-eks

# Until https://github.com/awslabs/ai-on-eks/pull/232 is merged, the custom stack can be used

cd infra/custom
./install.sh
```

The ai-on-eks blueprints provide:
- GPU support for AI/ML workloads
- Karpenter for efficient auto-scaling
- EKS-optimized configurations
- Security best practices
- Observability with Prometheus/Grafana
- Proven, battle-tested infrastructure

### Additional Requirements

- `helm` CLI installed (v3.0+)
- `kubectl` configured to access your EKS cluster
- AWS Load Balancer Controller for EKS
- ExternalDNS (optional, for automatic DNS management)
- Domain name with DNS access
- TLS certificates (AWS Certificate Manager or Let's Encrypt)

## Setup

```
git clone https://github.com/agentic-community/mcp-gateway-registry
cd mcp-gateway-registry/charts/mcp-gateway-registry-stack
```

## Values file

The `values.yaml` file needs to be updated for your setup, specifically:

- `DOMAIN`: there are placeholders for `DOMAIN` that should be updated with your full domain. For example, if you intend
  to use `example.com`, replace `DOMAIN` with `example.com`. If you intend to use a subdomain like
  `subdomain.example.com`, `DOMAIN` should be replaced with `subdomain.example.com`
- `secretKey`: the registry and auth-server both have a placeholder for `secretKey`, this should be updated to the same
  random, secure key that is used in both locations
- `routingMode`: choose between `subdomain` (default) or `path` based routing (see Routing Modes section below)

### Routing Modes

The stack supports two routing modes for accessing services:

#### Subdomain-Based Routing (Default)

Services are accessed via subdomains:
- `keycloak.{domain}` - Keycloak authentication server
- `auth-server.{domain}` - MCP Gateway auth server
- `mcpregistry.{domain}` - MCP server registry

**Configuration:**
```yaml
global:
  domain: "yourdomain.com"
  ingress:
    routingMode: subdomain
```

**DNS Requirements:** Configure A/CNAME records for each subdomain pointing to your ingress load balancer.

#### Path-Based Routing

Services are accessed via paths on a single domain:
- `{domain}/keycloak` - Keycloak authentication server (default, configurable)
- `{domain}/auth-server` - MCP Gateway auth server (default, configurable)
- `{domain}/registry` - MCP server registry (default, configurable)
- `{domain}/` - MCP server registry (root path)

**Configuration:**
```yaml
global:
  domain: "yourdomain.com"
  ingress:
    routingMode: path
    paths:
      authServer: /auth-server    # Customize as needed (e.g., /api/auth)
      registry: /registry          # Customize as needed (e.g., /api)
      keycloak: /keycloak         # Customize as needed (e.g., /auth/keycloak)
```

**Important:** If you customize the Keycloak path, update the helm variable:
```yaml
keycloak:
  httpRelativePath: /keycloak/
```

**DNS Requirements:** Configure a single A/CNAME record for your domain pointing to your ingress load balancer.

## Install

Once the `values.yaml` file is updated and saved, run (substitute MYNAMESPACE for the namespace in which this should be
installed):

```bash
helm dependency build && helm dependency update
helm install mcp-gateway-registry -n MYNAMESPACE --create-namespace . 
```

This will deploy the necessary resources for a Kubernetes deployment of the MCP Gateway Registry

## Deploy Process

- postgres, keycloak, registry, and auth-server will be deployed as the core components
- A `keycloak-configure` job will also be created
- Postgres will need to be running first before Keycloak will run
- Keycloak needs to be available before the `keycloak-configure` job will run
- auth-server will not start until the `keycloak-configure` job has succeeded and generated a secret that is needed for
  the auth-server.
- The registry will start as soon as the image is pulled

## Use

Navigate to the registry based on your routing mode:

**Subdomain mode:** https://mcpregistry.DOMAIN

**Path mode:** https://DOMAIN/registry or https://DOMAIN/

The username/password are displayed in the output of the `keycloak-configure job`

```bash
kubectl get pods -l job-name=setup-keycloak -n MYNAMESPACE     
```

The output will look similar to:

```
NAME                   READY   STATUS      RESTARTS   AGE
setup-keycloak-d6g2r   0/1     Completed   0          29m
setup-keycloak-nnqgj   0/1     Error       0          31m
```

Use the pod name that completed successfully:

```
kubectl logs -n MYNAMESPACE setup-keycloak-d6g2r --tail 20
```

You will see the credentials in the output

## Scaling and High Availability

### Replica Configuration

Both the auth-server and registry deployments support configuring the number of replicas via `values.yaml`:

```yaml
auth-server:
  replicaCount: 2

registry:
  replicaCount: 2
```

For production environments, we recommend running at least 2 replicas of each service to ensure high availability.

### Topology Spread Constraints

By default, neither the auth-server nor registry deployments include `topologySpreadConstraints`. This is intentional for several reasons:

1. **Routing Complexity**: Routing is complex and handled differently between deployments  
2. **Development Flexibility**: Single-node or small clusters (common in dev/test) would fail to schedule pods with strict spread constraints
3. **Custom Requirements**: Organizations often have specific topology requirements that vary by environment

For production deployments on multi-AZ clusters, we recommend adding topology spread constraints to both deployments to distribute pods across availability zones and nodes. This improves fault tolerance and ensures service availability during zone or node failures.

#### Adding Topology Spread Constraints

To add topology spread constraints, patch the deployments after installation:

```bash
# Patch auth-server deployment
kubectl patch deployment auth-server -n MYNAMESPACE --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/topologySpreadConstraints",
    "value": [
      {
        "maxSkew": 1,
        "topologyKey": "topology.kubernetes.io/zone",
        "whenUnsatisfiable": "ScheduleAnyway",
        "labelSelector": {
          "matchLabels": {
            "app.kubernetes.io/name": "auth-server",
            "app.kubernetes.io/component": "auth-server"
          }
        }
      },
      {
        "maxSkew": 1,
        "topologyKey": "kubernetes.io/hostname",
        "whenUnsatisfiable": "ScheduleAnyway",
        "labelSelector": {
          "matchLabels": {
            "app.kubernetes.io/name": "auth-server",
            "app.kubernetes.io/component": "auth-server"
          }
        }
      }
    ]
  }
]'

# Patch registry deployment
kubectl patch deployment registry -n MYNAMESPACE --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/topologySpreadConstraints",
    "value": [
      {
        "maxSkew": 1,
        "topologyKey": "topology.kubernetes.io/zone",
        "whenUnsatisfiable": "ScheduleAnyway",
        "labelSelector": {
          "matchLabels": {
            "app.kubernetes.io/name": "registry",
            "app.kubernetes.io/component": "registry"
          }
        }
      },
      {
        "maxSkew": 1,
        "topologyKey": "kubernetes.io/hostname",
        "whenUnsatisfiable": "ScheduleAnyway",
        "labelSelector": {
          "matchLabels": {
            "app.kubernetes.io/name": "registry",
            "app.kubernetes.io/component": "registry"
          }
        }
      }
    ]
  }
]'
```

#### Constraint Explanation

- **`topology.kubernetes.io/zone`**: Spreads pods across availability zones for zone-level fault tolerance
- **`kubernetes.io/hostname`**: Spreads pods across different nodes within each zone for node-level fault tolerance
- **`maxSkew: 1`**: Ensures pods are distributed as evenly as possible (difference between zones/nodes is at most 1)
- **`whenUnsatisfiable: ScheduleAnyway`**: Uses soft constraints that prefer even distribution but won't block scheduling if perfect distribution isn't possible. Change to `DoNotSchedule` for strict enforcement
