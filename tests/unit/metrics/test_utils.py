"""
Unit tests for metrics utility functions.
"""

import logging

import pytest

from registry.metrics.utils import (
    extract_server_name_from_url,
    hash_user_id,
    categorize_user_agent,
    extract_headers_for_analysis,
)


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: extract_server_name_from_url
# =============================================================================


@pytest.mark.unit
class TestExtractServerNameFromUrl:
    """Tests for extract_server_name_from_url function."""

    def test_extract_from_valid_url(self):
        """Test extracting server name from valid URL."""
        url = "http://localhost:8080/my-server/"
        result = extract_server_name_from_url(url)
        assert result == "my-server"

    def test_extract_from_url_without_port(self):
        """Test extracting server name from URL without port."""
        url = "https://example.com/test-server/mcp"
        result = extract_server_name_from_url(url)
        assert result == "test-server"

    def test_extract_from_empty_url(self):
        """Test extracting server name from empty URL returns unknown."""
        result = extract_server_name_from_url("")
        assert result == "unknown"

    def test_extract_from_none_url(self):
        """Test extracting server name from None returns unknown."""
        result = extract_server_name_from_url(None)
        assert result == "unknown"

    def test_extract_from_url_no_path(self):
        """Test extracting server name from URL with no path."""
        url = "http://localhost:8080"
        result = extract_server_name_from_url(url)
        assert result == "unknown"

    def test_extract_from_url_empty_path(self):
        """Test extracting server name from URL with empty path."""
        url = "http://localhost:8080/"
        result = extract_server_name_from_url(url)
        assert result == "unknown"

    def test_extract_from_complex_path(self):
        """Test extracting server name from complex path."""
        url = "http://mcp-gateway:8000/cloudflare-docs/mcp/endpoint"
        result = extract_server_name_from_url(url)
        assert result == "cloudflare-docs"


# =============================================================================
# TEST: hash_user_id
# =============================================================================


@pytest.mark.unit
class TestHashUserId:
    """Tests for hash_user_id function."""

    def test_hash_valid_user_id(self):
        """Test hashing a valid user ID."""
        user_id = "user@example.com"
        result = hash_user_id(user_id)
        assert len(result) == 12
        assert result.isalnum()

    def test_hash_empty_user_id(self):
        """Test hashing empty user ID returns empty string."""
        result = hash_user_id("")
        assert result == ""

    def test_hash_none_user_id(self):
        """Test hashing None user ID returns empty string."""
        result = hash_user_id(None)
        assert result == ""

    def test_hash_is_consistent(self):
        """Test that same user ID always produces same hash."""
        user_id = "test_user"
        result1 = hash_user_id(user_id)
        result2 = hash_user_id(user_id)
        assert result1 == result2

    def test_hash_different_users(self):
        """Test that different user IDs produce different hashes."""
        result1 = hash_user_id("user1")
        result2 = hash_user_id("user2")
        assert result1 != result2


# =============================================================================
# TEST: categorize_user_agent
# =============================================================================


@pytest.mark.unit
class TestCategorizeUserAgent:
    """Tests for categorize_user_agent function."""

    def test_categorize_curl(self):
        """Test categorizing curl user agent."""
        result = categorize_user_agent("curl/7.68.0")
        assert result == "curl"

    def test_categorize_postman(self):
        """Test categorizing Postman user agent."""
        result = categorize_user_agent("PostmanRuntime/7.29.0")
        assert result == "postman"

    def test_categorize_chrome(self):
        """Test categorizing Chrome user agent."""
        result = categorize_user_agent("Mozilla/5.0 Chrome/91.0")
        assert result == "chrome"

    def test_categorize_firefox(self):
        """Test categorizing Firefox user agent."""
        result = categorize_user_agent("Mozilla/5.0 Firefox/89.0")
        assert result == "firefox"

    def test_categorize_safari(self):
        """Test categorizing Safari user agent."""
        result = categorize_user_agent("Mozilla/5.0 Safari/537.36")
        assert result == "safari"

    def test_categorize_python_requests(self):
        """Test categorizing Python requests user agent."""
        result = categorize_user_agent("python-requests/2.25.1")
        assert result == "python_client"

    def test_categorize_python_generic(self):
        """Test categorizing generic Python user agent."""
        result = categorize_user_agent("Python/3.9")
        assert result == "python_client"

    def test_categorize_bot(self):
        """Test categorizing bot user agent."""
        result = categorize_user_agent("Googlebot/2.1")
        assert result == "bot"

    def test_categorize_crawler(self):
        """Test categorizing crawler user agent."""
        result = categorize_user_agent("Some Crawler/1.0")
        assert result == "bot"

    def test_categorize_empty(self):
        """Test categorizing empty user agent."""
        result = categorize_user_agent("")
        assert result == "unknown"

    def test_categorize_none(self):
        """Test categorizing None user agent."""
        result = categorize_user_agent(None)
        assert result == "unknown"

    def test_categorize_unknown(self):
        """Test categorizing unknown user agent."""
        result = categorize_user_agent("SomeCustomAgent/1.0")
        assert result == "other"


# =============================================================================
# TEST: extract_headers_for_analysis
# =============================================================================


@pytest.mark.unit
class TestExtractHeadersForAnalysis:
    """Tests for extract_headers_for_analysis function."""

    def test_extract_full_headers(self):
        """Test extracting all header information."""
        headers = {
            "user-agent": "curl/7.68.0",
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": "Bearer token123",
            "x-forwarded-for": "192.168.1.1",
            "origin": "http://localhost:3000",
            "referer": "http://localhost:3000/page",
            "connection": "keep-alive",
            "upgrade": "websocket",
        }

        result = extract_headers_for_analysis(headers)

        assert result["user_agent_type"] == "curl"
        assert result["accept"] == "application/json"
        assert result["content_type"] == "application/json"
        assert result["authorization_present"] is True
        assert result["x_forwarded_for_present"] is True
        assert result["origin"] == "http://localhost:3000"
        assert result["referer_present"] is True
        assert result["connection"] == "keep-alive"
        assert result["upgrade"] == "websocket"

    def test_extract_empty_headers(self):
        """Test extracting from empty headers."""
        result = extract_headers_for_analysis({})

        assert result["user_agent_type"] == "unknown"
        assert result["accept"] == "unknown"
        assert result["content_type"] == "unknown"
        assert result["authorization_present"] is False
        assert result["x_forwarded_for_present"] is False
        assert result["origin"] == "unknown"
        assert result["referer_present"] is False
        assert result["connection"] == "unknown"
        assert result["upgrade"] == "unknown"

    def test_extract_partial_headers(self):
        """Test extracting from partial headers."""
        headers = {
            "user-agent": "Chrome/91.0",
            "authorization": "Bearer token",
        }

        result = extract_headers_for_analysis(headers)

        assert result["user_agent_type"] == "chrome"
        assert result["authorization_present"] is True
        assert result["accept"] == "unknown"
