"""
Unit tests for registry.services.transform_service module.

This module tests the server transformation service that converts internal
server data to Anthropic API schema format.
"""

import logging
from typing import Any, Dict

import pytest

from registry.services.transform_service import (
    _create_server_name,
    _create_transport_config,
    _determine_version,
    _extract_repository_from_description,
    transform_to_server_detail,
    transform_to_server_list,
    transform_to_server_response,
)
from registry.constants import REGISTRY_CONSTANTS


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_server_info() -> Dict[str, Any]:
    """Create sample server info for testing."""
    return {
        "path": "/test-server",
        "server_name": "Test Server",
        "description": "A test server for unit tests",
        "proxy_pass_url": "http://localhost:8080/mcp",
        "is_enabled": True,
        "health_status": "healthy",
        "num_tools": 5,
        "tags": ["test", "example"],
        "license": "MIT",
        "last_checked_iso": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_server_with_version() -> Dict[str, Any]:
    """Create sample server info with version metadata."""
    return {
        "path": "/versioned-server",
        "server_name": "Versioned Server",
        "description": "Server with version",
        "proxy_pass_url": "http://localhost:9090/mcp",
        "_meta": {"version": "2.0.0"},
    }


# =============================================================================
# TEST: _create_transport_config
# =============================================================================


@pytest.mark.unit
class TestCreateTransportConfig:
    """Tests for the _create_transport_config function."""

    def test_create_transport_config_basic(self, sample_server_info):
        """Test creating transport config with proxy_pass_url."""
        result = _create_transport_config(sample_server_info)

        assert result["type"] == "streamable-http"
        assert result["url"] == "http://localhost:8080/mcp"

    def test_create_transport_config_empty_url(self):
        """Test creating transport config with empty proxy_pass_url."""
        server_info = {"path": "/test"}

        result = _create_transport_config(server_info)

        assert result["type"] == "streamable-http"
        assert result["url"] == ""

    def test_create_transport_config_missing_url(self):
        """Test creating transport config when proxy_pass_url is missing."""
        server_info = {}

        result = _create_transport_config(server_info)

        assert result["type"] == "streamable-http"
        assert result["url"] == ""


# =============================================================================
# TEST: _extract_repository_from_description
# =============================================================================


@pytest.mark.unit
class TestExtractRepositoryFromDescription:
    """Tests for the _extract_repository_from_description function."""

    def test_extract_repository_returns_none(self):
        """Test that repository extraction returns None for now."""
        result = _extract_repository_from_description("Some description")

        assert result is None

    def test_extract_repository_empty_description(self):
        """Test repository extraction with empty description."""
        result = _extract_repository_from_description("")

        assert result is None


# =============================================================================
# TEST: _determine_version
# =============================================================================


@pytest.mark.unit
class TestDetermineVersion:
    """Tests for the _determine_version function."""

    def test_determine_version_default(self, sample_server_info):
        """Test default version is returned when no metadata."""
        result = _determine_version(sample_server_info)

        assert result == "1.0.0"

    def test_determine_version_from_meta(self, sample_server_with_version):
        """Test version is extracted from _meta."""
        result = _determine_version(sample_server_with_version)

        assert result == "2.0.0"

    def test_determine_version_empty_meta(self):
        """Test default version when _meta exists but no version."""
        server_info = {"path": "/test", "_meta": {}}

        result = _determine_version(server_info)

        assert result == "1.0.0"


# =============================================================================
# TEST: _create_server_name
# =============================================================================


@pytest.mark.unit
class TestCreateServerName:
    """Tests for the _create_server_name function."""

    def test_create_server_name_basic(self, sample_server_info):
        """Test creating reverse-DNS server name."""
        result = _create_server_name(sample_server_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/test-server"

    def test_create_server_name_with_leading_slash(self):
        """Test server name strips leading slash."""
        server_info = {"path": "/my-server"}

        result = _create_server_name(server_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/my-server"

    def test_create_server_name_with_trailing_slash(self):
        """Test server name strips trailing slash."""
        server_info = {"path": "/my-server/"}

        result = _create_server_name(server_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/my-server"

    def test_create_server_name_empty_path(self):
        """Test server name with empty path."""
        server_info = {"path": ""}

        result = _create_server_name(server_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/"

    def test_create_server_name_missing_path(self):
        """Test server name when path is missing."""
        server_info = {}

        result = _create_server_name(server_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/"


# =============================================================================
# TEST: transform_to_server_detail
# =============================================================================


@pytest.mark.unit
class TestTransformToServerDetail:
    """Tests for the transform_to_server_detail function."""

    def test_transform_to_server_detail_basic(self, sample_server_info):
        """Test basic server detail transformation."""
        result = transform_to_server_detail(sample_server_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result.name == f"{namespace}/test-server"
        assert result.description == "A test server for unit tests"
        assert result.version == "1.0.0"
        assert result.title == "Test Server"
        assert result.repository is None
        assert len(result.packages) == 1

    def test_transform_to_server_detail_package(self, sample_server_info):
        """Test package in server detail transformation."""
        result = transform_to_server_detail(sample_server_info)

        package = result.packages[0]
        assert package.registryType == "mcpb"
        assert package.version == "1.0.0"
        assert package.transport["type"] == "streamable-http"
        assert package.transport["url"] == "http://localhost:8080/mcp"
        assert package.runtimeHint == "docker"

    def test_transform_to_server_detail_meta(self, sample_server_info):
        """Test metadata in server detail transformation."""
        result = transform_to_server_detail(sample_server_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        meta_key = f"{namespace}/internal"
        assert meta_key in result.meta
        assert result.meta[meta_key]["path"] == "/test-server"
        assert result.meta[meta_key]["is_enabled"] is True
        assert result.meta[meta_key]["health_status"] == "healthy"
        assert result.meta[meta_key]["num_tools"] == 5
        assert result.meta[meta_key]["tags"] == ["test", "example"]
        assert result.meta[meta_key]["license"] == "MIT"

    def test_transform_to_server_detail_with_version(self, sample_server_with_version):
        """Test server detail with version metadata."""
        result = transform_to_server_detail(sample_server_with_version)

        assert result.version == "2.0.0"

    def test_transform_to_server_detail_missing_fields(self):
        """Test transformation with missing optional fields."""
        server_info = {"path": "/minimal-server"}

        result = transform_to_server_detail(server_info)

        assert result.description == ""
        assert result.title is None
        assert result.version == "1.0.0"


# =============================================================================
# TEST: transform_to_server_response
# =============================================================================


@pytest.mark.unit
class TestTransformToServerResponse:
    """Tests for the transform_to_server_response function."""

    def test_transform_to_server_response_with_meta(self, sample_server_info):
        """Test server response with registry metadata."""
        result = transform_to_server_response(sample_server_info, include_registry_meta=True)

        assert result.server is not None
        assert result.meta is not None
        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        registry_key = f"{namespace}/registry"
        assert registry_key in result.meta
        assert result.meta[registry_key]["last_checked"] == "2024-01-01T00:00:00Z"
        assert result.meta[registry_key]["health_status"] == "healthy"

    def test_transform_to_server_response_without_meta(self, sample_server_info):
        """Test server response without registry metadata."""
        result = transform_to_server_response(sample_server_info, include_registry_meta=False)

        assert result.server is not None
        assert result.meta is None


# =============================================================================
# TEST: transform_to_server_list
# =============================================================================


@pytest.mark.unit
class TestTransformToServerList:
    """Tests for the transform_to_server_list function."""

    def test_transform_to_server_list_empty(self):
        """Test transformation of empty server list."""
        result = transform_to_server_list([])

        assert len(result.servers) == 0
        assert result.metadata.nextCursor is None
        assert result.metadata.count == 0

    def test_transform_to_server_list_single(self, sample_server_info):
        """Test transformation of single server."""
        result = transform_to_server_list([sample_server_info])

        assert len(result.servers) == 1
        assert result.metadata.count == 1
        assert result.metadata.nextCursor is None

    def test_transform_to_server_list_multiple(self, sample_server_info):
        """Test transformation of multiple servers."""
        servers = [
            {**sample_server_info, "path": f"/server-{i}"}
            for i in range(5)
        ]

        result = transform_to_server_list(servers)

        assert len(result.servers) == 5
        assert result.metadata.count == 5

    def test_transform_to_server_list_with_limit(self, sample_server_info):
        """Test transformation with limit."""
        servers = [
            {**sample_server_info, "path": f"/server-{i}"}
            for i in range(10)
        ]

        result = transform_to_server_list(servers, limit=5)

        assert len(result.servers) == 5
        assert result.metadata.count == 5
        assert result.metadata.nextCursor is not None

    def test_transform_to_server_list_with_cursor(self, sample_server_info):
        """Test transformation with cursor pagination."""
        servers = [
            {**sample_server_info, "path": f"/server-{i}"}
            for i in range(10)
        ]

        # Get first page
        first_result = transform_to_server_list(servers, limit=5)
        cursor = first_result.metadata.nextCursor

        # Get second page using cursor
        second_result = transform_to_server_list(servers, cursor=cursor, limit=5)

        assert len(second_result.servers) == 5
        assert second_result.metadata.count == 5

    def test_transform_to_server_list_default_limit(self, sample_server_info):
        """Test that default limit is 100."""
        servers = [
            {**sample_server_info, "path": f"/server-{i}"}
            for i in range(150)
        ]

        result = transform_to_server_list(servers, limit=None)

        assert len(result.servers) == 100

    def test_transform_to_server_list_max_limit(self, sample_server_info):
        """Test that max limit is enforced at 1000."""
        servers = [
            {**sample_server_info, "path": f"/server-{i}"}
            for i in range(100)
        ]

        result = transform_to_server_list(servers, limit=2000)

        # Should cap at 1000, but we only have 100 servers
        assert len(result.servers) == 100

    def test_transform_to_server_list_zero_limit(self, sample_server_info):
        """Test that zero limit uses default."""
        servers = [
            {**sample_server_info, "path": f"/server-{i}"}
            for i in range(150)
        ]

        result = transform_to_server_list(servers, limit=0)

        assert len(result.servers) == 100

    def test_transform_to_server_list_negative_limit(self, sample_server_info):
        """Test that negative limit uses default."""
        servers = [
            {**sample_server_info, "path": f"/server-{i}"}
            for i in range(150)
        ]

        result = transform_to_server_list(servers, limit=-5)

        assert len(result.servers) == 100

    def test_transform_to_server_list_sorted_by_name(self):
        """Test that servers are sorted by name."""
        servers = [
            {"path": "/z-server", "server_name": "Z Server"},
            {"path": "/a-server", "server_name": "A Server"},
            {"path": "/m-server", "server_name": "M Server"},
        ]

        result = transform_to_server_list(servers)

        # Servers should be sorted by created name
        names = [s.server.name for s in result.servers]
        assert names == sorted(names)
