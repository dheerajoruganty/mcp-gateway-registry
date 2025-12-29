#
# Amazon OpenSearch Serverless Infrastructure for MCP Gateway Registry
#
# This configuration creates an OpenSearch Serverless collection with VPC access
# for the MCP Gateway Registry backend search functionality.
#
# Note: Uses data.aws_caller_identity.current defined in keycloak-ecr.tf

#
# Encryption Policy
#
resource "aws_opensearchserverless_security_policy" "encryption" {
  name = "${var.name}-v2-encryption-policy"
  type = "encryption"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource = [
          "collection/${var.name}-registry"
        ]
      }
    ]
    AWSOwnedKey = true
  })

  description = "Encryption policy for MCP Gateway Registry OpenSearch Serverless collection"
}

#
# Network Policy
#
resource "aws_opensearchserverless_security_policy" "network" {
  name = "${var.name}-v2-network-policy"
  type = "network"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/${var.name}-registry"
          ]
        },
        {
          ResourceType = "dashboard"
          Resource = [
            "collection/${var.name}-registry"
          ]
        }
      ]
      AllowFromPublic = false
      SourceVPCEs = [
        aws_opensearchserverless_vpc_endpoint.main.id
      ]
    }
  ])

  description = "Network policy for MCP Gateway Registry OpenSearch Serverless collection (VPC access only)"

  depends_on = [
    aws_opensearchserverless_vpc_endpoint.main
  ]
}

#
# Data Access Policy
#
resource "aws_opensearchserverless_access_policy" "data" {
  name = "${var.name}-v2-data-policy"
  type = "data"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource = [
            "index/${var.name}-registry/*"
          ]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument"
          ]
        },
        {
          ResourceType = "collection"
          Resource = [
            "collection/${var.name}-registry"
          ]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DeleteCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems"
          ]
        }
      ]
      Principal = [
        # Grant access to all IAM roles in the account
        # This allows ECS task roles to access the collection
        "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
      ]
    }
  ])

  description = "Data access policy for MCP Gateway Registry OpenSearch Serverless collection"
}

#
# OpenSearch Serverless Collection
#
resource "aws_opensearchserverless_collection" "main" {
  name = "${var.name}-registry"
  type = "VECTORSEARCH"

  description = "MCP Gateway Registry vector search backend using OpenSearch Serverless"

  tags = local.common_tags

  depends_on = [
    aws_opensearchserverless_security_policy.encryption
  ]
}

#
# Security Group for VPC Endpoint
#
resource "aws_security_group" "opensearch_endpoint" {
  name        = "${var.name}-v2-opensearch-serverless-endpoint-sg"
  description = "Security group for OpenSearch Serverless VPC endpoint"
  vpc_id      = module.vpc.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "${var.name}-v2-opensearch-serverless-endpoint-sg"
    }
  )
}

# Ingress from Registry service
resource "aws_vpc_security_group_ingress_rule" "opensearch_from_registry" {
  security_group_id = aws_security_group.opensearch_endpoint.id

  referenced_security_group_id = module.mcp_gateway.ecs_security_group_ids.registry
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Allow HTTPS from Registry ECS service to OpenSearch Serverless"

  tags = merge(
    local.common_tags,
    {
      Name = "opensearch-from-registry"
    }
  )
}

# Ingress from Auth service
resource "aws_vpc_security_group_ingress_rule" "opensearch_from_auth" {
  security_group_id = aws_security_group.opensearch_endpoint.id

  referenced_security_group_id = module.mcp_gateway.ecs_security_group_ids.auth
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Allow HTTPS from Auth ECS service to OpenSearch Serverless"

  tags = merge(
    local.common_tags,
    {
      Name = "opensearch-from-auth"
    }
  )
}

# Egress to anywhere (standard for VPC endpoints)
resource "aws_vpc_security_group_egress_rule" "opensearch_egress" {
  security_group_id = aws_security_group.opensearch_endpoint.id

  cidr_ipv4   = "0.0.0.0/0"
  ip_protocol = "-1"
  description = "Allow all outbound traffic"

  tags = merge(
    local.common_tags,
    {
      Name = "opensearch-egress-all"
    }
  )
}

#
# Security Group Rules for Registry and Auth services to reach OpenSearch
#

# Registry -> OpenSearch endpoint
resource "aws_vpc_security_group_egress_rule" "registry_to_opensearch" {
  security_group_id = module.mcp_gateway.ecs_security_group_ids.registry

  referenced_security_group_id = aws_security_group.opensearch_endpoint.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Allow Registry service to connect to OpenSearch Serverless"

  tags = merge(
    local.common_tags,
    {
      Name = "registry-to-opensearch"
    }
  )
}

# Auth -> OpenSearch endpoint
resource "aws_vpc_security_group_egress_rule" "auth_to_opensearch" {
  security_group_id = module.mcp_gateway.ecs_security_group_ids.auth

  referenced_security_group_id = aws_security_group.opensearch_endpoint.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
  description                  = "Allow Auth service to connect to OpenSearch Serverless"

  tags = merge(
    local.common_tags,
    {
      Name = "auth-to-opensearch"
    }
  )
}

#
# VPC Endpoint
#
resource "aws_opensearchserverless_vpc_endpoint" "main" {
  name               = "${var.name}-v2-os-endpoint"
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = module.vpc.private_subnets
  security_group_ids = [aws_security_group.opensearch_endpoint.id]

  # Ensure security group is created before VPC endpoint
  depends_on = [
    aws_security_group.opensearch_endpoint
  ]
}
