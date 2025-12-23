"""
Conftest for integration tests.

Provides fixtures specific to integration tests that involve multiple
components working together.
"""

import logging
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)


@pytest.fixture
def test_client(mock_settings) -> Generator[TestClient, None, None]:
    """
    Create a FastAPI test client for integration tests.

    Args:
        mock_settings: Test settings fixture

    Yields:
        FastAPI TestClient instance
    """
    from registry.main import app

    with TestClient(app) as client:
        logger.debug("Created FastAPI test client")
        yield client


@pytest.fixture
async def async_test_client(mock_settings):
    """
    Create an async FastAPI test client for integration tests.

    Args:
        mock_settings: Test settings fixture

    Yields:
        Async test client
    """
    from httpx import AsyncClient

    from registry.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        logger.debug("Created async FastAPI test client")
        yield client
