#
# Secret Rotation Configuration
#
# This file adds automatic rotation to existing secrets defined in:
# - documentdb.tf: aws_secretsmanager_secret.documentdb_credentials
# - keycloak-database.tf: aws_secretsmanager_secret.keycloak_db_secret
#
# Secrets are rotated every 30 days automatically by Lambda functions.
#

#
# Enable Rotation for DocumentDB Credentials
#
resource "aws_secretsmanager_secret_rotation" "documentdb_credentials" {
  secret_id           = aws_secretsmanager_secret.documentdb_credentials.id
  rotation_lambda_arn = aws_lambda_function.documentdb_rotation.arn

  rotation_rules {
    automatically_after_days = 30
  }

  depends_on = [
    aws_lambda_permission.documentdb_rotation,
    aws_secretsmanager_secret_version.documentdb_credentials
  ]
}

#
# Enable Rotation for Keycloak Database Credentials
#
resource "aws_secretsmanager_secret_rotation" "keycloak_db_secret" {
  secret_id           = aws_secretsmanager_secret.keycloak_db_secret.id
  rotation_lambda_arn = aws_lambda_function.rds_rotation.arn

  rotation_rules {
    automatically_after_days = 30
  }

  depends_on = [
    aws_lambda_permission.rds_rotation,
    aws_secretsmanager_secret_version.keycloak_db_secret
  ]
}
