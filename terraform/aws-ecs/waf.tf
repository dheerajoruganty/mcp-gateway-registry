#
# WAFv2 Web ACL Configuration for MCP Gateway and Keycloak ALBs
# Set enable_waf = false in terraform.tfvars if you don't have wafv2:* IAM permissions
#

# WAFv2 Web ACL for MCP Gateway ALB
resource "aws_wafv2_web_acl" "mcp_gateway" {
  count = var.enable_waf ? 1 : 0

  name  = "${var.name}-mcp-gateway-waf"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS Managed Rules - Common Rule Set
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesCommonRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules - Known Bad Inputs
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesKnownBadInputsRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  # IP-based rate limiting rule (100 req/5min per IP)
  rule {
    name     = "IPRateLimitRule"
    priority = 3

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 100
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "IPRateLimitRuleMetric"
      sampled_requests_enabled   = true
    }
  }

  # Global rate limiting rule (2000 req/5min globally)
  rule {
    name     = "GlobalRateLimitRule"
    priority = 4

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "CONSTANT"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "GlobalRateLimitRuleMetric"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name}-mcp-gateway-waf"
    sampled_requests_enabled   = true
  }

  tags = merge(
    local.common_tags,
    {
      Purpose   = "WAF protection for MCP Gateway ALB"
      Component = "security"
    }
  )
}


# Associate WAF with MCP Gateway ALB
resource "aws_wafv2_web_acl_association" "mcp_gateway" {
  count = var.enable_waf ? 1 : 0

  resource_arn = module.mcp_gateway.alb_arn
  web_acl_arn  = aws_wafv2_web_acl.mcp_gateway[0].arn
}


# CloudWatch Log Group for WAF logs
resource "aws_cloudwatch_log_group" "waf_mcp_gateway" {
  count = var.enable_waf ? 1 : 0

  name              = "/aws/wafv2/${var.name}-mcp-gateway"
  retention_in_days = 30

  tags = merge(
    local.common_tags,
    {
      Purpose   = "WAF logs for MCP Gateway"
      Component = "security"
    }
  )
}


# WAF Logging Configuration
resource "aws_wafv2_web_acl_logging_configuration" "mcp_gateway" {
  count = var.enable_waf ? 1 : 0

  resource_arn            = aws_wafv2_web_acl.mcp_gateway[0].arn
  log_destination_configs = [aws_cloudwatch_log_group.waf_mcp_gateway[0].arn]

  # Redact sensitive headers from logs
  redacted_fields {
    single_header {
      name = "authorization"
    }
  }
}


# WAFv2 Web ACL for Keycloak ALB
resource "aws_wafv2_web_acl" "keycloak" {
  count = var.enable_waf ? 1 : 0

  name  = "${var.name}-keycloak-waf"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS Managed Rules - Common Rule Set
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesCommonRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules - Known Bad Inputs
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesKnownBadInputsRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  # IP-based rate limiting rule (100 req/5min per IP)
  rule {
    name     = "IPRateLimitRule"
    priority = 3

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 100
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "IPRateLimitRuleMetric"
      sampled_requests_enabled   = true
    }
  }

  # Global rate limiting rule (2000 req/5min globally)
  rule {
    name     = "GlobalRateLimitRule"
    priority = 4

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "CONSTANT"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "GlobalRateLimitRuleMetric"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name}-keycloak-waf"
    sampled_requests_enabled   = true
  }

  tags = merge(
    local.common_tags,
    {
      Purpose   = "WAF protection for Keycloak ALB"
      Component = "security"
    }
  )
}


# Associate WAF with Keycloak ALB
resource "aws_wafv2_web_acl_association" "keycloak" {
  count = var.enable_waf ? 1 : 0

  resource_arn = aws_lb.keycloak.arn
  web_acl_arn  = aws_wafv2_web_acl.keycloak[0].arn
}


# CloudWatch Log Group for Keycloak WAF logs
resource "aws_cloudwatch_log_group" "waf_keycloak" {
  count = var.enable_waf ? 1 : 0

  name              = "/aws/wafv2/${var.name}-keycloak"
  retention_in_days = 30

  tags = merge(
    local.common_tags,
    {
      Purpose   = "WAF logs for Keycloak"
      Component = "security"
    }
  )
}


# WAF Logging Configuration for Keycloak
resource "aws_wafv2_web_acl_logging_configuration" "keycloak" {
  count = var.enable_waf ? 1 : 0

  resource_arn            = aws_wafv2_web_acl.keycloak[0].arn
  log_destination_configs = [aws_cloudwatch_log_group.waf_keycloak[0].arn]

  # Redact sensitive headers from logs
  redacted_fields {
    single_header {
      name = "authorization"
    }
  }
}


# Outputs
output "mcp_gateway_waf_arn" {
  description = "ARN of WAF Web ACL for MCP Gateway"
  value       = var.enable_waf ? aws_wafv2_web_acl.mcp_gateway[0].arn : ""
}


output "keycloak_waf_arn" {
  description = "ARN of WAF Web ACL for Keycloak"
  value       = var.enable_waf ? aws_wafv2_web_acl.keycloak[0].arn : ""
}
