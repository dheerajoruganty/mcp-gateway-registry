#!/bin/bash
set -e

echo "=========================================="
echo "OpenSearch Initialization and Import"
echo "=========================================="

# Step 1: Initialize indices
echo ""
echo "Step 1/2: Creating OpenSearch indices..."
python init-opensearch-aws.py "$@"

if [ $? -ne 0 ]; then
    echo "ERROR: Index initialization failed"
    exit 1
fi

echo ""
echo "Step 1/2: Index initialization completed successfully"

# Step 2: Import scopes
echo ""
echo "Step 2/2: Importing scopes from scopes.yml..."
python import-scopes-to-opensearch-aws.py "$@"

if [ $? -ne 0 ]; then
    echo "ERROR: Scopes import failed"
    exit 1
fi

echo ""
echo "Step 2/2: Scopes import completed successfully"

echo ""
echo "=========================================="
echo "OpenSearch initialization complete!"
echo "=========================================="

exit 0
