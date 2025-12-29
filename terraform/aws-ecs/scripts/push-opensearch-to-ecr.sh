#!/bin/bash
# Pull OpenSearch image from Docker Hub and push to ECR
# This avoids Docker Hub rate limits for production deployments

set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="opensearch"
OPENSEARCH_VERSION="2.11.1"
DOCKER_HUB_IMAGE="opensearchproject/opensearch:${OPENSEARCH_VERSION}"
ECR_IMAGE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:${OPENSEARCH_VERSION}"
ECR_IMAGE_LATEST="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}:latest"

echo "=================================================="
echo "OpenSearch ECR Image Push Script"
echo "=================================================="
echo "Docker Hub Image: ${DOCKER_HUB_IMAGE}"
echo "ECR Image: ${ECR_IMAGE}"
echo ""

# Step 1: Login to Amazon ECR
echo "Step 1: Logging in to Amazon ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Step 2: Create ECR repository if it doesn't exist
echo "Step 2: Creating ECR repository if it doesn't exist..."
aws ecr describe-repositories --repository-names "${ECR_REPO_NAME}" --region "${AWS_REGION}" 2>/dev/null || \
    aws ecr create-repository \
        --repository-name "${ECR_REPO_NAME}" \
        --region "${AWS_REGION}" \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256

# Step 3: Pull OpenSearch image from Docker Hub
echo "Step 3: Pulling OpenSearch ${OPENSEARCH_VERSION} from Docker Hub..."
docker pull "${DOCKER_HUB_IMAGE}"

# Step 4: Tag the image for ECR
echo "Step 4: Tagging image for ECR..."
docker tag "${DOCKER_HUB_IMAGE}" "${ECR_IMAGE}"
docker tag "${DOCKER_HUB_IMAGE}" "${ECR_IMAGE_LATEST}"

# Step 5: Push to ECR
echo "Step 5: Pushing image to ECR..."
docker push "${ECR_IMAGE}"
docker push "${ECR_IMAGE_LATEST}"

echo ""
echo "=================================================="
echo "Successfully pushed OpenSearch to ECR!"
echo "=================================================="
echo "Image URI (versioned): ${ECR_IMAGE}"
echo "Image URI (latest):    ${ECR_IMAGE_LATEST}"
echo ""
echo "Next steps:"
echo "1. Update terraform/aws-ecs/opensearch-services.tf to use ECR image"
echo "2. Run: terraform apply"
echo ""
