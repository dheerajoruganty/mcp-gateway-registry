#!/bin/bash
set -e

REGION="us-east-1"
ACCOUNT_ID="128755427449"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "Building and pushing all images to ECR..."
echo ""

# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}

# Array of images to build
IMAGES=(
  "registry:docker/Dockerfile.registry:."
  "currenttime:docker/Dockerfile.mcp-server:servers/currenttime"
  "mcpgw:docker/Dockerfile.mcp-server:servers/mcpgw"
  "realserverfaketools:docker/Dockerfile.mcp-server:servers/realserverfaketools"
  "flight-booking-agent:agents/a2a/flight-booking-agent/Dockerfile:agents/a2a/flight-booking-agent"
  "travel-assistant-agent:agents/a2a/travel-assistant-agent/Dockerfile:agents/a2a/travel-assistant-agent"
)

cd ../..

for IMAGE_INFO in "${IMAGES[@]}"; do
  IFS=':' read -r REPO_NAME DOCKERFILE CONTEXT <<< "$IMAGE_INFO"
  
  echo ""
  echo "========================================="
  echo "Building: $REPO_NAME"
  echo "========================================="
  
  # Create ECR repository if it doesn't exist
  aws ecr create-repository --repository-name ${REPO_NAME} --region ${REGION} 2>/dev/null || echo "Repository exists"
  
  # Build image
  docker build --platform linux/amd64 -f ${DOCKERFILE} -t ${REPO_NAME}:latest ${CONTEXT}
  
  # Tag for ECR
  docker tag ${REPO_NAME}:latest ${ECR_REGISTRY}/${REPO_NAME}:latest
  
  # Push to ECR
  docker push ${ECR_REGISTRY}/${REPO_NAME}:latest
  
  echo "✅ Done: ${REPO_NAME}"
done

echo ""
echo "========================================="
echo "✅ All images built and pushed to ECR!"
echo "========================================="
echo ""
echo "Now run: cd terraform/aws-ecs && terraform apply -auto-approve"
