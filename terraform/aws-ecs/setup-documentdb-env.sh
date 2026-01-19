#!/bin/bash
#
# Setup environment variables for DocumentDB Terraform deployment
#
# Usage:
#   source ./setup-documentdb-env.sh
#
# This script sets Terraform variables as environment variables for security.
# Credentials are not stored in terraform.tfvars files.
#

# Exit on error
set -e

echo "Setting up DocumentDB Terraform environment variables..."

# DocumentDB Admin Credentials
# IMPORTANT: Change these to your actual credentials!
export TF_VAR_documentdb_admin_username="docdbadmin"
export TF_VAR_documentdb_admin_password="CHANGE-ME-YourSecurePassword123!"

# Optional: Override default capacity settings
# Uncomment and modify as needed:
# export TF_VAR_documentdb_shard_capacity=2   # Options: 2, 4, 8, 16, 32, 64
# export TF_VAR_documentdb_shard_count=1      # 1-32 shards

echo ""
echo "✅ Environment variables set:"
echo "   TF_VAR_documentdb_admin_username = $TF_VAR_documentdb_admin_username"
echo "   TF_VAR_documentdb_admin_password = ******** (hidden)"
echo ""
echo "⚠️  IMPORTANT: Change the password before deploying to production!"
echo ""
echo "Next steps:"
echo "  1. Edit this file and set a secure password"
echo "  2. Source this file: source ./setup-documentdb-env.sh"
echo "  3. Deploy: terraform plan && terraform apply"
echo ""
