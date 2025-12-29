# OpenSearch CLI Task Definition
# This task runs management commands for OpenSearch Serverless indexes

# Data source to look up existing ECR repository for OpenSearch CLI
# This is a dedicated lightweight image just for AOSS management
data "aws_ecr_repository" "opensearch_cli" {
  name = "mcp-gateway-opensearch-cli"
}

# Data source to look up existing registry task definition to extract roles
data "aws_ecs_task_definition" "registry" {
  task_definition = "${var.name}-v2-registry"
}

resource "aws_ecs_task_definition" "opensearch_cli" {
  family                   = "mcp-gateway-opensearch-cli"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = data.aws_ecs_task_definition.registry.execution_role_arn
  task_role_arn            = data.aws_ecs_task_definition.registry.task_role_arn

  container_definitions = jsonencode([
    {
      name      = "opensearch-cli"
      image     = "${data.aws_ecr_repository.opensearch_cli.repository_url}:latest"
      essential = true

      # Default command (can be overridden at runtime)
      command = [
        "python",
        "scripts/manage-aoss-indexes.py",
        "list"
      ]

      environment = [
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "OPENSEARCH_HOST"
          value = replace(replace(aws_opensearchserverless_collection.main.collection_endpoint, "https://", ""), "http://", "")
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.opensearch_cli.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "opensearch-cli"
        }
      }
    }
  ])

  tags = {
    Name      = "mcp-gateway-opensearch-cli"
    ManagedBy = "terraform"
  }
}

# CloudWatch Log Group for OpenSearch CLI
resource "aws_cloudwatch_log_group" "opensearch_cli" {
  name              = "/ecs/mcp-gateway-opensearch-cli"
  retention_in_days = 7

  tags = {
    Name      = "mcp-gateway-opensearch-cli-logs"
    ManagedBy = "terraform"
  }
}

# Output the task definition ARN
output "opensearch_cli_task_definition_arn" {
  description = "ARN of the OpenSearch CLI task definition"
  value       = aws_ecs_task_definition.opensearch_cli.arn
}
