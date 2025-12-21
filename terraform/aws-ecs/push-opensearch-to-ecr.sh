#!/bin/bash
set -e

REGION="us-east-1"
ACCOUNT_ID="128755427449"
IMAGE_NAME="opensearch"
IMAGE_TAG="2.11.0"

echo "Creating ECR repository..."
aws ecr create-repository --repository-name ${IMAGE_NAME} --region ${REGION} 2>/dev/null || echo "Repository already exists"

echo "Logging into ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

echo "Pulling OpenSearch image from Docker Hub (AMD64 architecture for ECS Fargate)..."
docker pull --platform linux/amd64 opensearchproject/${IMAGE_NAME}:${IMAGE_TAG}

echo "Tagging image for ECR..."
docker tag opensearchproject/${IMAGE_NAME}:${IMAGE_TAG} ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:${IMAGE_TAG}

echo "Pushing to ECR..."
docker push ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:${IMAGE_TAG}

echo ""
echo "✅ Done! OpenSearch image pushed to ECR."
echo "ECR Image URI: ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "Now run: terraform apply -auto-approve"
