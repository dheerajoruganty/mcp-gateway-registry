#!/bin/bash

# Exit on error
set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
OPENSEARCH_INIT_DIR="$PARENT_DIR/opensearch-init"
REPO_ROOT="$(cd "$PARENT_DIR/../.." && pwd)"

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO_NAME="mcp-gateway-opensearch-init"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME"

echo "=================================================="
echo "Build and Push OpenSearch Init Container"
echo "=================================================="
echo "AWS Region: $AWS_REGION"
echo "ECR Repository: $ECR_REPO_NAME"
echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo ""

# Create opensearch-init directory if it doesn't exist
mkdir -p "$OPENSEARCH_INIT_DIR"

# Copy necessary files to build context
echo "Step 1: Preparing build context..."
cp "$REPO_ROOT/scripts/init-opensearch-aws.py" "$OPENSEARCH_INIT_DIR/"
cp "$REPO_ROOT/scripts/import-scopes-to-opensearch-aws.py" "$OPENSEARCH_INIT_DIR/"
cp -r "$REPO_ROOT/scripts/opensearch-schemas" "$OPENSEARCH_INIT_DIR/"
cp -r "$REPO_ROOT/auth_server" "$OPENSEARCH_INIT_DIR/"
echo "Build context ready"

# Login to Amazon ECR
echo "Step 2: Logging in to Amazon ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# Create repository if it doesn't exist
echo "Step 3: Creating ECR repository if it doesn't exist..."
aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" 2>/dev/null || \
    aws ecr create-repository \
        --repository-name "$ECR_REPO_NAME" \
        --region "$AWS_REGION" \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256

# Build the Docker image
echo "Step 4: Building Docker image..."
docker build -f "$OPENSEARCH_INIT_DIR/Dockerfile" -t "$ECR_REPO_NAME" "$OPENSEARCH_INIT_DIR"

# Tag the image
echo "Step 5: Tagging image..."
docker tag "$ECR_REPO_NAME":latest "$ECR_REPO_URI":latest

# Push the image to ECR
echo "Step 6: Pushing image to ECR..."
docker push "$ECR_REPO_URI":latest

echo ""
echo "=================================================="
echo "Successfully built and pushed image to:"
echo "$ECR_REPO_URI:latest"
echo "=================================================="
echo ""

# Clean up build context
rm -f "$OPENSEARCH_INIT_DIR/init-opensearch-aws.py"
rm -f "$OPENSEARCH_INIT_DIR/import-scopes-to-opensearch-aws.py"
rm -rf "$OPENSEARCH_INIT_DIR/opensearch-schemas"
rm -rf "$OPENSEARCH_INIT_DIR/auth_server"

exit 0
