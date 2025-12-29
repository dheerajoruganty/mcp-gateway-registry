"""AWS-specific authentication for OpenSearch Serverless."""

import logging

import boto3
from opensearchpy import AWSV4SignerAsyncAuth
from opensearchpy.connection import AsyncHttpConnection

logger = logging.getLogger(__name__)


def get_aws_auth(
    region: str
) -> AWSV4SignerAsyncAuth:
    """
    Create AWS SigV4 async auth for OpenSearch Serverless.

    Args:
        region: AWS region name

    Returns:
        AWSV4SignerAsyncAuth instance configured for async OpenSearch Serverless
    """
    credentials = boto3.Session().get_credentials()

    if not credentials:
        raise ValueError("No AWS credentials found. Configure AWS credentials.")

    auth = AWSV4SignerAsyncAuth(credentials, region, "aoss")

    logger.info(f"Configured AWS SigV4 async auth for region: {region}, service: aoss")

    return auth


def get_aws_connection_class():
    """
    Get the connection class for AWS OpenSearch.

    Returns:
        AsyncHttpConnection class for AWS authentication with async support
    """
    return AsyncHttpConnection
