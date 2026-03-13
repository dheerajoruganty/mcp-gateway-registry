#
# CloudFront Access Logging Infrastructure
#
# This configuration creates an S3 bucket for CloudFront access logs
# with security hardening (public access block, encryption, lifecycle).
#

#
# S3 Bucket for CloudFront Logs
#
resource "aws_s3_bucket" "cloudfront_logs" {
  bucket = "ai-registry-${var.aws_region}-${data.aws_caller_identity.current.account_id}-cloudfront-logs"

  tags = merge(
    local.common_tags,
    {
      Purpose   = "CloudFront access logs"
      Component = "logging"
    }
  )
}

#
# Block Public Access
#
resource "aws_s3_bucket_public_access_block" "cloudfront_logs" {
  bucket = aws_s3_bucket.cloudfront_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

#
# Server-Side Encryption
#
resource "aws_s3_bucket_server_side_encryption_configuration" "cloudfront_logs" {
  bucket = aws_s3_bucket.cloudfront_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

#
# Lifecycle Policy - Delete logs after 90 days
#
resource "aws_s3_bucket_lifecycle_configuration" "cloudfront_logs" {
  bucket = aws_s3_bucket.cloudfront_logs.id

  rule {
    id     = "delete-old-logs"
    status = "Enabled"

    expiration {
      days = 90
    }
  }
}

#
# Ownership Controls (required for CloudFront logging)
#
# CloudFront uses the awslogsdelivery account to write logs,
# so we need BucketOwnerPreferred to ensure the bucket owner
# gets full control of the objects written by CloudFront.
#
resource "aws_s3_bucket_ownership_controls" "cloudfront_logs" {
  bucket = aws_s3_bucket.cloudfront_logs.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

#
# Versioning (optional, for additional protection)
#
resource "aws_s3_bucket_versioning" "cloudfront_logs" {
  bucket = aws_s3_bucket.cloudfront_logs.id

  versioning_configuration {
    status = "Enabled"
  }
}
