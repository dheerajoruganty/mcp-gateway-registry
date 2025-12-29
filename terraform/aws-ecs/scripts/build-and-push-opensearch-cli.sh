#!/bin/bash
# Build and push OpenSearch CLI Docker image to ECR

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TERRAFORM_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$TERRAFORM_DIR")")"

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPO_NAME="mcp-gateway-opensearch-cli"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME"

echo "Building OpenSearch CLI Docker image..."
echo "Project root: $PROJECT_ROOT"
echo "ECR repository: $ECR_REPO_URI"
echo ""

# Login to Amazon ECR
echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# Create repository if it doesn't exist
echo "Creating ECR repository if it doesn't exist..."
aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" 2>/dev/null || \
    aws ecr create-repository --repository-name "$ECR_REPO_NAME" --region "$AWS_REGION"

# Build the Docker image
echo "Building Docker image..."
docker build \
    -f "$TERRAFORM_DIR/opensearch-cli/Dockerfile" \
    -t "$ECR_REPO_NAME:latest" \
    "$PROJECT_ROOT"

# Tag the image
echo "Tagging image..."
docker tag "$ECR_REPO_NAME:latest" "$ECR_REPO_URI:latest"

# Push the image to ECR
echo "Pushing image to ECR..."
docker push "$ECR_REPO_URI:latest"

echo ""
echo "Successfully built and pushed image:"
echo "$ECR_REPO_URI:latest"
echo ""

# Save the container URI to a file for reference
echo "$ECR_REPO_URI:latest" > "$SCRIPT_DIR/.opensearch_cli_container_uri"
echo "Container URI saved to: $SCRIPT_DIR/.opensearch_cli_container_uri"
