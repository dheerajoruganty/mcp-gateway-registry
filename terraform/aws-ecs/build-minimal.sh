#!/bin/bash
set -e

REGION="us-east-1"
ACCOUNT_ID="128755427449"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "Building minimal images for testing..."
echo ""

# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}

# Only build essential images
IMAGES=(
  "registry:docker/Dockerfile.registry:."
  "currenttime:docker/Dockerfile.mcp-server:servers/currenttime"
)

cd ../..

for IMAGE_INFO in "${IMAGES[@]}"; do
  IFS=':' read -r REPO_NAME DOCKERFILE CONTEXT <<< "$IMAGE_INFO"
  
  echo ""
  echo "Building: $REPO_NAME"
  
  aws ecr create-repository --repository-name ${REPO_NAME} --region ${REGION} 2>/dev/null || true
  
  docker build --platform linux/amd64 -f ${DOCKERFILE} -t ${REPO_NAME}:latest ${CONTEXT}
  docker tag ${REPO_NAME}:latest ${ECR_REGISTRY}/${REPO_NAME}:latest
  docker push ${ECR_REGISTRY}/${REPO_NAME}:latest
  
  echo "✅ Done: ${REPO_NAME}"
done

echo ""
echo "✅ Essential images ready!"
echo ""
echo "Now run: cd terraform/aws-ecs && terraform apply -auto-approve"
