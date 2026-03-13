#!/bin/bash
#
# Verification script for Lambda-based secret rotation deployment
# This script checks that all components are properly deployed and configured
#

set -e

echo "==================================================================="
echo "Secret Rotation Deployment Verification"
echo "==================================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get deployment name from terraform
DEPLOYMENT_NAME="${TF_VAR_name:-mcp-gateway}"
AWS_REGION="${TF_VAR_aws_region:-us-west-2}"

echo "Deployment: ${DEPLOYMENT_NAME}"
echo "Region: ${AWS_REGION}"
echo ""

# Check Lambda functions
echo "Checking Lambda Functions..."
echo "-------------------------------------------------------------------"

DOCUMENTDB_LAMBDA="${DEPLOYMENT_NAME}-rotate-documentdb"
RDS_LAMBDA="${DEPLOYMENT_NAME}-rotate-rds"

if aws lambda get-function --function-name "$DOCUMENTDB_LAMBDA" --region "$AWS_REGION" &>/dev/null; then
    echo -e "${GREEN}✓${NC} Lambda function exists: $DOCUMENTDB_LAMBDA"
else
    echo -e "${RED}✗${NC} Lambda function NOT found: $DOCUMENTDB_LAMBDA"
fi

if aws lambda get-function --function-name "$RDS_LAMBDA" --region "$AWS_REGION" &>/dev/null; then
    echo -e "${GREEN}✓${NC} Lambda function exists: $RDS_LAMBDA"
else
    echo -e "${RED}✗${NC} Lambda function NOT found: $RDS_LAMBDA"
fi

echo ""

# Check CloudWatch Log Groups
echo "Checking CloudWatch Log Groups..."
echo "-------------------------------------------------------------------"

DOCUMENTDB_LOG_GROUP="/aws/lambda/${DOCUMENTDB_LAMBDA}"
RDS_LOG_GROUP="/aws/lambda/${RDS_LAMBDA}"

if aws logs describe-log-groups --log-group-name-prefix "$DOCUMENTDB_LOG_GROUP" --region "$AWS_REGION" --query 'logGroups[0].logGroupName' --output text | grep -q "$DOCUMENTDB_LAMBDA"; then
    echo -e "${GREEN}✓${NC} Log group exists: $DOCUMENTDB_LOG_GROUP"
else
    echo -e "${RED}✗${NC} Log group NOT found: $DOCUMENTDB_LOG_GROUP"
fi

if aws logs describe-log-groups --log-group-name-prefix "$RDS_LOG_GROUP" --region "$AWS_REGION" --query 'logGroups[0].logGroupName' --output text | grep -q "$RDS_LAMBDA"; then
    echo -e "${GREEN}✓${NC} Log group exists: $RDS_LOG_GROUP"
else
    echo -e "${RED}✗${NC} Log group NOT found: $RDS_LOG_GROUP"
fi

echo ""

# Check Secrets Manager rotation configuration
echo "Checking Secrets Manager Rotation..."
echo "-------------------------------------------------------------------"

DOCUMENTDB_SECRET="${DEPLOYMENT_NAME}/documentdb/credentials"
RDS_SECRET="keycloak/database"

# Check DocumentDB secret
if aws secretsmanager describe-secret --secret-id "$DOCUMENTDB_SECRET" --region "$AWS_REGION" &>/dev/null; then
    ROTATION_ENABLED=$(aws secretsmanager describe-secret --secret-id "$DOCUMENTDB_SECRET" --region "$AWS_REGION" --query 'RotationEnabled' --output text)
    if [ "$ROTATION_ENABLED" = "True" ]; then
        echo -e "${GREEN}✓${NC} Rotation enabled: $DOCUMENTDB_SECRET"
        ROTATION_LAMBDA=$(aws secretsmanager describe-secret --secret-id "$DOCUMENTDB_SECRET" --region "$AWS_REGION" --query 'RotationRules.RotationLambdaARN' --output text 2>/dev/null || echo "N/A")
        echo "  Lambda ARN: $ROTATION_LAMBDA"
    else
        echo -e "${YELLOW}⚠${NC} Rotation NOT enabled: $DOCUMENTDB_SECRET"
    fi
else
    echo -e "${RED}✗${NC} Secret NOT found: $DOCUMENTDB_SECRET"
fi

# Check RDS secret
if aws secretsmanager describe-secret --secret-id "$RDS_SECRET" --region "$AWS_REGION" &>/dev/null; then
    ROTATION_ENABLED=$(aws secretsmanager describe-secret --secret-id "$RDS_SECRET" --region "$AWS_REGION" --query 'RotationEnabled' --output text)
    if [ "$ROTATION_ENABLED" = "True" ]; then
        echo -e "${GREEN}✓${NC} Rotation enabled: $RDS_SECRET"
        ROTATION_LAMBDA=$(aws secretsmanager describe-secret --secret-id "$RDS_SECRET" --region "$AWS_REGION" --query 'RotationRules.RotationLambdaARN' --output text 2>/dev/null || echo "N/A")
        echo "  Lambda ARN: $ROTATION_LAMBDA"
    else
        echo -e "${YELLOW}⚠${NC} Rotation NOT enabled: $RDS_SECRET"
    fi
else
    echo -e "${RED}✗${NC} Secret NOT found: $RDS_SECRET"
fi

echo ""
echo "==================================================================="
echo "Verification Complete"
echo "==================================================================="
echo ""
echo "To manually trigger rotation:"
echo "  aws secretsmanager rotate-secret --secret-id $DOCUMENTDB_SECRET --region $AWS_REGION"
echo "  aws secretsmanager rotate-secret --secret-id $RDS_SECRET --region $AWS_REGION"
echo ""
echo "To view Lambda logs:"
echo "  aws logs tail $DOCUMENTDB_LOG_GROUP --follow --region $AWS_REGION"
echo "  aws logs tail $RDS_LOG_GROUP --follow --region $AWS_REGION"
echo ""
