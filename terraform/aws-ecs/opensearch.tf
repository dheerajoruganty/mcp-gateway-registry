#
# OpenSearch ECS Service
#

locals {
  opensearch_container_env = [
    {
      name  = "discovery.type"
      value = "single-node"
    },
    {
      name  = "OPENSEARCH_JAVA_OPTS"
      value = "-Xms512m -Xmx512m"
    },
    {
      name  = "DISABLE_SECURITY_PLUGIN"
      value = "true"
    },
    {
      name  = "DISABLE_INSTALL_DEMO_CONFIG"
      value = "true"
    }
  ]

  opensearch_container_secrets = [
    {
      name      = "OPENSEARCH_INITIAL_ADMIN_PASSWORD"
      valueFrom = aws_ssm_parameter.opensearch_admin_password.arn
    }
  ]
}

# ECS Cluster for OpenSearch (reuse existing cluster)
# OpenSearch will be deployed to the same cluster as other services

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "opensearch" {
  name              = "/ecs/opensearch"
  retention_in_days = 7

  tags = local.common_tags
}

# ECS Task Execution Role
resource "aws_iam_role" "opensearch_task_exec_role" {
  name = "opensearch-task-exec-role-${var.aws_region}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Attach default ECS task execution policy
resource "aws_iam_role_policy_attachment" "opensearch_task_exec_role_policy" {
  role       = aws_iam_role.opensearch_task_exec_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Policy to read from SSM Parameter Store
resource "aws_iam_role_policy" "opensearch_task_exec_ssm_policy" {
  name = "opensearch-task-exec-ssm-policy"
  role = aws_iam_role.opensearch_task_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = [
          aws_ssm_parameter.opensearch_admin_password.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = "*"
      }
    ]
  })
}

# Policy to write logs to CloudWatch
resource "aws_iam_role_policy" "opensearch_task_exec_logs_policy" {
  name = "opensearch-task-exec-logs-policy"
  role = aws_iam_role.opensearch_task_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.opensearch.arn}:*"
      }
    ]
  })
}

# ECS Task Role
resource "aws_iam_role" "opensearch_task_role" {
  name = "opensearch-task-role-${var.aws_region}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Policy for SSM Session Manager
resource "aws_iam_role_policy" "opensearch_task_ssm_policy" {
  name = "opensearch-task-ssm-policy"
  role = aws_iam_role.opensearch_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })
}

# EFS Access Point for OpenSearch data
resource "aws_efs_access_point" "opensearch_data" {
  file_system_id = module.mcp_gateway.efs_id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/opensearch-data"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "755"
    }
  }

  tags = merge(
    local.common_tags,
    {
      Name = "opensearch-data"
    }
  )
}

# ECS Task Definition
resource "aws_ecs_task_definition" "opensearch" {
  family                   = "opensearch"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.opensearch_task_exec_role.arn
  task_role_arn            = aws_iam_role.opensearch_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "opensearch"
      image     = "128755427449.dkr.ecr.us-east-1.amazonaws.com/opensearch:2.11.0"
      essential = true

      portMappings = [
        {
          name          = "opensearch"
          containerPort = 9200
          hostPort      = 9200
          protocol      = "tcp"
        },
        {
          name          = "opensearch-perf"
          containerPort = 9600
          hostPort      = 9600
          protocol      = "tcp"
        }
      ]

      environment = local.opensearch_container_env

      secrets = local.opensearch_container_secrets

      mountPoints = [
        {
          sourceVolume  = "opensearch-data"
          containerPath = "/usr/share/opensearch/data"
          readOnly      = false
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.opensearch.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      readonlyRootFilesystem = false

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 5
        startPeriod = 120
      }
    }
  ])

  volume {
    name = "opensearch-data"

    efs_volume_configuration {
      file_system_id          = module.mcp_gateway.efs_id
      transit_encryption      = "ENABLED"
      transit_encryption_port = 2049
      authorization_config {
        access_point_id = aws_efs_access_point.opensearch_data.id
        iam             = "DISABLED"
      }
    }
  }

  tags = local.common_tags
}

# Service Discovery for OpenSearch
resource "aws_service_discovery_service" "opensearch" {
  name = "opensearch"

  dns_config {
    namespace_id = module.mcp_gateway.service_discovery_namespace_id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  # Health check configuration
  # Note: failure_threshold is deprecated and always set to 1 by AWS

  tags = local.common_tags
}

# ECS Service
resource "aws_ecs_service" "opensearch" {
  name            = "opensearch"
  cluster         = module.ecs_cluster.id
  task_definition = aws_ecs_task_definition.opensearch.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.opensearch_ecs.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.opensearch.arn
  }

  enable_execute_command = true

  depends_on = [
    aws_iam_role_policy.opensearch_task_exec_ssm_policy,
    aws_iam_role_policy.opensearch_task_exec_logs_policy
  ]

  tags = local.common_tags
}

# Security Group for OpenSearch ECS
resource "aws_security_group" "opensearch_ecs" {
  name        = "opensearch-ecs"
  description = "Security group for OpenSearch ECS tasks"
  vpc_id      = module.vpc.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "opensearch-ecs"
    }
  )
}

# ECS Egress to Internet (HTTPS)
resource "aws_security_group_rule" "opensearch_ecs_egress_internet" {
  description       = "Egress from OpenSearch ECS task to internet (HTTPS)"
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.opensearch_ecs.id
}

# ECS Egress to DNS
resource "aws_security_group_rule" "opensearch_ecs_egress_dns" {
  description       = "Egress from OpenSearch ECS task for DNS"
  type              = "egress"
  from_port         = 53
  to_port           = 53
  protocol          = "udp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.opensearch_ecs.id
}

# ECS Egress to EFS
resource "aws_security_group_rule" "opensearch_ecs_egress_efs" {
  description       = "Egress from OpenSearch ECS task to EFS"
  type              = "egress"
  from_port         = 2049
  to_port           = 2049
  protocol          = "tcp"
  security_group_id = aws_security_group.opensearch_ecs.id
  cidr_blocks       = [module.vpc.vpc_cidr_block]
}

# ECS Ingress from Registry Service
resource "aws_security_group_rule" "opensearch_ecs_ingress_registry" {
  description              = "Ingress from Registry to OpenSearch ECS task"
  type                     = "ingress"
  from_port                = 9200
  to_port                  = 9200
  protocol                 = "tcp"
  security_group_id        = aws_security_group.opensearch_ecs.id
  source_security_group_id = module.mcp_gateway.ecs_security_group_ids.registry
}

# ECS Ingress from Auth Server Service
resource "aws_security_group_rule" "opensearch_ecs_ingress_auth" {
  description              = "Ingress from Auth Server to OpenSearch ECS task"
  type                     = "ingress"
  from_port                = 9200
  to_port                  = 9200
  protocol                 = "tcp"
  security_group_id        = aws_security_group.opensearch_ecs.id
  source_security_group_id = module.mcp_gateway.ecs_security_group_ids.auth
}

# SSM Parameter for OpenSearch Admin Password
resource "aws_ssm_parameter" "opensearch_admin_password" {
  name  = "/opensearch/admin_password"
  type  = "SecureString"
  value = var.opensearch_admin_password
  tags  = local.common_tags
}
