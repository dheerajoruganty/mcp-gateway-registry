"""
Unit tests for registry.services.agent_transform_service module.

This module tests the agent transformation service that converts internal
A2A agent data to Anthropic API schema format.
"""

import logging
from typing import Any, Dict

import pytest

from registry.services.agent_transform_service import (
    _create_agent_name,
    _create_agent_transport_config,
    _determine_agent_version,
    transform_to_agent_detail,
    transform_to_agent_list,
    transform_to_agent_response,
)
from registry.constants import REGISTRY_CONSTANTS


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_agent_info() -> Dict[str, Any]:
    """Create sample agent info for testing."""
    return {
        "path": "/code-reviewer",
        "name": "Code Reviewer Agent",
        "description": "An AI agent that reviews code",
        "url": "http://localhost:9000/agent",
        "is_enabled": True,
        "visibility": "public",
        "trust_level": "verified",
        "skills": [
            {"name": "code-review", "description": "Review code quality"},
            {"name": "security-scan", "description": "Scan for vulnerabilities"},
        ],
        "tags": ["code", "review", "ai"],
        "protocol_version": "1.0",
        "last_checked_iso": "2024-01-01T00:00:00Z",
        "health_status": "healthy",
    }


@pytest.fixture
def sample_agent_with_meta() -> Dict[str, Any]:
    """Create sample agent info with _meta version."""
    return {
        "path": "/versioned-agent",
        "name": "Versioned Agent",
        "description": "Agent with version metadata",
        "url": "http://localhost:9001/agent",
        "_meta": {"version": "2.5.0"},
    }


# =============================================================================
# TEST: _create_agent_transport_config
# =============================================================================


@pytest.mark.unit
class TestCreateAgentTransportConfig:
    """Tests for the _create_agent_transport_config function."""

    def test_create_agent_transport_config_basic(self, sample_agent_info):
        """Test creating transport config with url."""
        result = _create_agent_transport_config(sample_agent_info)

        assert result["type"] == "streamable-http"
        assert result["url"] == "http://localhost:9000/agent"

    def test_create_agent_transport_config_empty_url(self):
        """Test creating transport config with empty url."""
        agent_info = {"path": "/test"}

        result = _create_agent_transport_config(agent_info)

        assert result["type"] == "streamable-http"
        assert result["url"] == ""

    def test_create_agent_transport_config_missing_url(self):
        """Test creating transport config when url is missing."""
        agent_info = {}

        result = _create_agent_transport_config(agent_info)

        assert result["type"] == "streamable-http"
        assert result["url"] == ""


# =============================================================================
# TEST: _determine_agent_version
# =============================================================================


@pytest.mark.unit
class TestDetermineAgentVersion:
    """Tests for the _determine_agent_version function."""

    def test_determine_agent_version_from_protocol(self, sample_agent_info):
        """Test version from protocol_version field."""
        result = _determine_agent_version(sample_agent_info)

        assert result == "1.0"

    def test_determine_agent_version_from_meta(self, sample_agent_with_meta):
        """Test version from _meta field."""
        result = _determine_agent_version(sample_agent_with_meta)

        assert result == "2.5.0"

    def test_determine_agent_version_default(self):
        """Test default version when no metadata."""
        agent_info = {"path": "/test"}

        result = _determine_agent_version(agent_info)

        assert result == "1.0.0"

    def test_determine_agent_version_protocol_takes_precedence(self):
        """Test protocol_version takes precedence over _meta."""
        agent_info = {
            "protocol_version": "3.0",
            "_meta": {"version": "2.0.0"},
        }

        result = _determine_agent_version(agent_info)

        assert result == "3.0"


# =============================================================================
# TEST: _create_agent_name
# =============================================================================


@pytest.mark.unit
class TestCreateAgentName:
    """Tests for the _create_agent_name function."""

    def test_create_agent_name_basic(self, sample_agent_info):
        """Test creating reverse-DNS agent name."""
        result = _create_agent_name(sample_agent_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/code-reviewer"

    def test_create_agent_name_with_leading_slash(self):
        """Test agent name strips leading slash."""
        agent_info = {"path": "/my-agent"}

        result = _create_agent_name(agent_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/my-agent"

    def test_create_agent_name_with_trailing_slash(self):
        """Test agent name strips trailing slash."""
        agent_info = {"path": "/my-agent/"}

        result = _create_agent_name(agent_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/my-agent"

    def test_create_agent_name_empty_path(self):
        """Test agent name with empty path."""
        agent_info = {"path": ""}

        result = _create_agent_name(agent_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/"

    def test_create_agent_name_missing_path(self):
        """Test agent name when path is missing."""
        agent_info = {}

        result = _create_agent_name(agent_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result == f"{namespace}/"


# =============================================================================
# TEST: transform_to_agent_detail
# =============================================================================


@pytest.mark.unit
class TestTransformToAgentDetail:
    """Tests for the transform_to_agent_detail function."""

    def test_transform_to_agent_detail_basic(self, sample_agent_info):
        """Test basic agent detail transformation."""
        result = transform_to_agent_detail(sample_agent_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        assert result.name == f"{namespace}/code-reviewer"
        assert result.description == "An AI agent that reviews code"
        assert result.version == "1.0"
        assert result.title == "Code Reviewer Agent"
        assert result.repository is None
        assert len(result.packages) == 1

    def test_transform_to_agent_detail_package(self, sample_agent_info):
        """Test package in agent detail transformation."""
        result = transform_to_agent_detail(sample_agent_info)

        package = result.packages[0]
        assert package.registryType == "mcpb"
        assert package.version == "1.0"
        assert package.transport["type"] == "streamable-http"
        assert package.transport["url"] == "http://localhost:9000/agent"
        assert package.runtimeHint == "docker"

    def test_transform_to_agent_detail_meta(self, sample_agent_info):
        """Test metadata in agent detail transformation."""
        result = transform_to_agent_detail(sample_agent_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        meta_key = f"{namespace}/internal"
        assert meta_key in result.meta
        assert result.meta[meta_key]["path"] == "/code-reviewer"
        assert result.meta[meta_key]["type"] == "a2a-agent"
        assert result.meta[meta_key]["is_enabled"] is True
        assert result.meta[meta_key]["visibility"] == "public"
        assert result.meta[meta_key]["trust_level"] == "verified"
        assert len(result.meta[meta_key]["skills"]) == 2
        assert result.meta[meta_key]["tags"] == ["code", "review", "ai"]
        assert result.meta[meta_key]["protocol_version"] == "1.0"

    def test_transform_to_agent_detail_missing_fields(self):
        """Test transformation with missing optional fields."""
        agent_info = {"path": "/minimal-agent"}

        result = transform_to_agent_detail(agent_info)

        assert result.description == ""
        assert result.title is None
        assert result.version == "1.0.0"

    def test_transform_to_agent_detail_default_values(self):
        """Test transformation uses default values for missing fields."""
        agent_info = {"path": "/test-agent"}

        result = transform_to_agent_detail(agent_info)

        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        meta_key = f"{namespace}/internal"
        assert result.meta[meta_key]["is_enabled"] is True
        assert result.meta[meta_key]["visibility"] == "public"
        assert result.meta[meta_key]["trust_level"] == "community"
        assert result.meta[meta_key]["skills"] == []
        assert result.meta[meta_key]["tags"] == []
        assert result.meta[meta_key]["protocol_version"] == "1.0"


# =============================================================================
# TEST: transform_to_agent_response
# =============================================================================


@pytest.mark.unit
class TestTransformToAgentResponse:
    """Tests for the transform_to_agent_response function."""

    def test_transform_to_agent_response_with_meta(self, sample_agent_info):
        """Test agent response with registry metadata."""
        result = transform_to_agent_response(sample_agent_info, include_registry_meta=True)

        assert result.server is not None
        assert result.meta is not None
        namespace = REGISTRY_CONSTANTS.ANTHROPIC_SERVER_NAMESPACE
        registry_key = f"{namespace}/registry"
        assert registry_key in result.meta
        assert result.meta[registry_key]["last_checked"] == "2024-01-01T00:00:00Z"
        assert result.meta[registry_key]["health_status"] == "healthy"

    def test_transform_to_agent_response_without_meta(self, sample_agent_info):
        """Test agent response without registry metadata."""
        result = transform_to_agent_response(sample_agent_info, include_registry_meta=False)

        assert result.server is not None
        assert result.meta is None


# =============================================================================
# TEST: transform_to_agent_list
# =============================================================================


@pytest.mark.unit
class TestTransformToAgentList:
    """Tests for the transform_to_agent_list function."""

    def test_transform_to_agent_list_empty(self):
        """Test transformation of empty agent list."""
        result = transform_to_agent_list([])

        assert len(result.servers) == 0
        assert result.metadata.nextCursor is None
        assert result.metadata.count == 0

    def test_transform_to_agent_list_single(self, sample_agent_info):
        """Test transformation of single agent."""
        result = transform_to_agent_list([sample_agent_info])

        assert len(result.servers) == 1
        assert result.metadata.count == 1
        assert result.metadata.nextCursor is None

    def test_transform_to_agent_list_multiple(self, sample_agent_info):
        """Test transformation of multiple agents."""
        agents = [
            {**sample_agent_info, "path": f"/agent-{i}"}
            for i in range(5)
        ]

        result = transform_to_agent_list(agents)

        assert len(result.servers) == 5
        assert result.metadata.count == 5

    def test_transform_to_agent_list_with_limit(self, sample_agent_info):
        """Test transformation with limit."""
        agents = [
            {**sample_agent_info, "path": f"/agent-{i}"}
            for i in range(10)
        ]

        result = transform_to_agent_list(agents, limit=5)

        assert len(result.servers) == 5
        assert result.metadata.count == 5
        assert result.metadata.nextCursor is not None

    def test_transform_to_agent_list_with_cursor(self, sample_agent_info):
        """Test transformation with cursor pagination."""
        agents = [
            {**sample_agent_info, "path": f"/agent-{i}"}
            for i in range(10)
        ]

        first_result = transform_to_agent_list(agents, limit=5)
        cursor = first_result.metadata.nextCursor

        second_result = transform_to_agent_list(agents, cursor=cursor, limit=5)

        assert len(second_result.servers) == 5
        assert second_result.metadata.count == 5

    def test_transform_to_agent_list_default_limit(self, sample_agent_info):
        """Test that default limit is 100."""
        agents = [
            {**sample_agent_info, "path": f"/agent-{i}"}
            for i in range(150)
        ]

        result = transform_to_agent_list(agents, limit=None)

        assert len(result.servers) == 100

    def test_transform_to_agent_list_max_limit(self, sample_agent_info):
        """Test that max limit is enforced at 1000."""
        agents = [
            {**sample_agent_info, "path": f"/agent-{i}"}
            for i in range(100)
        ]

        result = transform_to_agent_list(agents, limit=2000)

        assert len(result.servers) == 100

    def test_transform_to_agent_list_sorted_by_name(self):
        """Test that agents are sorted by name."""
        agents = [
            {"path": "/z-agent", "name": "Z Agent"},
            {"path": "/a-agent", "name": "A Agent"},
            {"path": "/m-agent", "name": "M Agent"},
        ]

        result = transform_to_agent_list(agents)

        names = [s.server.name for s in result.servers]
        assert names == sorted(names)
