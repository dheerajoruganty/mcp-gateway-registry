"""
Unit tests for registry.services.agent_scanner module.

This module tests the agent scanner service that scans A2A agents
for security vulnerabilities.
"""

import json
import logging
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from registry.services.agent_scanner import AgentScannerService


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_agent_card():
    """Create a sample agent card for testing."""
    return {
        "name": "Test Agent",
        "description": "A test agent",
        "url": "http://localhost:9000/agent",
        "version": "1.0.0",
        "protocol_version": "1.0",
        "skills": [
            {"name": "skill1", "description": "First skill"},
        ],
    }


@pytest.fixture
def mock_scan_repo():
    """Create a mock scan repository."""
    mock = AsyncMock()
    mock.create = AsyncMock()
    mock.get_latest = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def scanner_service(mock_scan_repo):
    """Create an AgentScannerService with mocked repository."""
    with patch("registry.services.agent_scanner.get_security_scan_repository", return_value=mock_scan_repo):
        service = AgentScannerService()
        service._scan_repo = mock_scan_repo
        return service


# =============================================================================
# TEST: AgentScannerService Configuration
# =============================================================================


@pytest.mark.unit
class TestAgentScannerServiceConfig:
    """Tests for AgentScannerService configuration."""

    def test_get_scan_config(self, scanner_service):
        """Test getting scan configuration."""
        result = scanner_service.get_scan_config()

        assert result is not None
        assert hasattr(result, "enabled")
        assert hasattr(result, "analyzers")
        assert hasattr(result, "scan_timeout_seconds")


# =============================================================================
# TEST: AgentScannerService._analyze_scan_results
# =============================================================================


@pytest.mark.unit
class TestAgentScannerAnalyzeResults:
    """Tests for the _analyze_scan_results method."""

    def test_analyze_scan_results_all_safe(self, scanner_service):
        """Test analyzing scan results with no findings."""
        raw_output = {"analysis_results": {}}

        is_safe, critical, high, medium, low = scanner_service._analyze_scan_results(raw_output)

        assert is_safe is True
        assert critical == 0
        assert high == 0
        assert medium == 0
        assert low == 0

    def test_analyze_scan_results_with_critical(self, scanner_service):
        """Test analyzing scan results with critical findings."""
        raw_output = {
            "analysis_results": {
                "Analyzer1": {
                    "findings": [
                        {"severity": "critical"},
                        {"severity": "high"},
                    ]
                }
            }
        }

        is_safe, critical, high, medium, low = scanner_service._analyze_scan_results(raw_output)

        assert is_safe is False
        assert critical == 1
        assert high == 1

    def test_analyze_scan_results_with_medium_low(self, scanner_service):
        """Test analyzing scan results with medium and low findings."""
        raw_output = {
            "analysis_results": {
                "Analyzer1": {
                    "findings": [
                        {"severity": "medium"},
                        {"severity": "low"},
                        {"severity": "low"},
                    ]
                }
            }
        }

        is_safe, critical, high, medium, low = scanner_service._analyze_scan_results(raw_output)

        assert is_safe is True
        assert critical == 0
        assert high == 0
        assert medium == 1
        assert low == 2

    def test_analyze_scan_results_case_insensitive(self, scanner_service):
        """Test that severity analysis is case insensitive."""
        raw_output = {
            "analysis_results": {
                "Analyzer1": {
                    "findings": [
                        {"severity": "HIGH"},
                        {"severity": "Medium"},
                        {"severity": "LOW"},
                    ]
                }
            }
        }

        is_safe, critical, high, medium, low = scanner_service._analyze_scan_results(raw_output)

        assert is_safe is False
        assert high == 1
        assert medium == 1
        assert low == 1

    def test_analyze_scan_results_multiple_analyzers(self, scanner_service):
        """Test analyzing results from multiple analyzers."""
        raw_output = {
            "analysis_results": {
                "Analyzer1": {
                    "findings": [{"severity": "high"}]
                },
                "Analyzer2": {
                    "findings": [{"severity": "medium"}]
                },
            }
        }

        is_safe, critical, high, medium, low = scanner_service._analyze_scan_results(raw_output)

        assert is_safe is False
        assert high == 1
        assert medium == 1


# =============================================================================
# TEST: AgentScannerService.scan_agent (async)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentScannerScanAgent:
    """Async tests for the scan_agent method."""

    @pytest.fixture
    def mock_scan_repo(self):
        """Create a mock scan repository."""
        mock = AsyncMock()
        mock.create = AsyncMock()
        mock.get_latest = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def scanner_service(self, mock_scan_repo):
        """Create an AgentScannerService with mocked repository."""
        with patch("registry.services.agent_scanner.get_security_scan_repository", return_value=mock_scan_repo):
            service = AgentScannerService()
            service._scan_repo = mock_scan_repo
            return service

    async def test_scan_agent_success(self, scanner_service, mock_scan_repo, sample_agent_card):
        """Test successful agent scan."""
        mock_output = {
            "analysis_results": {},
            "scan_results": {},
        }

        with patch.object(scanner_service, "_run_a2a_scanner", return_value=mock_output):
            result = await scanner_service.scan_agent(
                agent_card=sample_agent_card,
                agent_path="/test-agent",
                analyzers="basic",
                timeout=30,
            )

        assert result.is_safe is True
        assert result.scan_failed is False
        mock_scan_repo.create.assert_called_once()

    async def test_scan_agent_with_findings(self, scanner_service, mock_scan_repo, sample_agent_card):
        """Test agent scan with security findings."""
        mock_output = {
            "analysis_results": {
                "Analyzer1": {
                    "findings": [{"severity": "high"}]
                }
            },
            "scan_results": {},
        }

        with patch.object(scanner_service, "_run_a2a_scanner", return_value=mock_output):
            result = await scanner_service.scan_agent(
                agent_card=sample_agent_card,
                agent_path="/test-agent",
            )

        assert result.is_safe is False
        assert result.high_severity == 1

    async def test_scan_agent_error(self, scanner_service, mock_scan_repo, sample_agent_card):
        """Test agent scan error handling."""
        with patch.object(scanner_service, "_run_a2a_scanner", side_effect=RuntimeError("Scanner failed")):
            result = await scanner_service.scan_agent(
                agent_card=sample_agent_card,
                agent_path="/test-agent",
            )

        assert result.scan_failed is True
        assert result.is_safe is False
        assert "Scanner failed" in result.error_message

    async def test_scan_agent_includes_url(self, scanner_service, mock_scan_repo, sample_agent_card):
        """Test that agent URL is included in result."""
        mock_output = {"analysis_results": {}, "scan_results": {}}

        with patch.object(scanner_service, "_run_a2a_scanner", return_value=mock_output):
            result = await scanner_service.scan_agent(
                agent_card=sample_agent_card,
                agent_path="/test-agent",
            )

        assert result.agent_url == "http://localhost:9000/agent"


# =============================================================================
# TEST: AgentScannerService.get_scan_result (async)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgentScannerGetScanResult:
    """Async tests for the get_scan_result method."""

    @pytest.fixture
    def mock_scan_repo(self):
        """Create a mock scan repository."""
        mock = AsyncMock()
        mock.get_latest = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def scanner_service(self, mock_scan_repo):
        """Create an AgentScannerService with mocked repository."""
        with patch("registry.services.agent_scanner.get_security_scan_repository", return_value=mock_scan_repo):
            service = AgentScannerService()
            service._scan_repo = mock_scan_repo
            return service

    async def test_get_scan_result_found(self, scanner_service, mock_scan_repo):
        """Test getting existing scan result."""
        mock_scan_repo.get_latest.return_value = {
            "agent_path": "/test-agent",
            "is_safe": True,
        }

        result = await scanner_service.get_scan_result("/test-agent")

        assert result is not None
        assert result["is_safe"] is True

    async def test_get_scan_result_not_found(self, scanner_service, mock_scan_repo):
        """Test getting scan result when none exists."""
        mock_scan_repo.get_latest.return_value = None

        result = await scanner_service.get_scan_result("/nonexistent")

        assert result is None

    async def test_get_scan_result_exception(self, scanner_service, mock_scan_repo):
        """Test get_scan_result handles exception."""
        mock_scan_repo.get_latest.side_effect = Exception("DB error")

        result = await scanner_service.get_scan_result("/test-agent")

        assert result is None


# =============================================================================
# TEST: AgentScannerService._run_a2a_scanner
# =============================================================================


@pytest.mark.unit
class TestAgentScannerRunScanner:
    """Tests for the _run_a2a_scanner method."""

    @pytest.fixture
    def mock_scan_repo(self):
        """Create a mock scan repository."""
        return AsyncMock()

    @pytest.fixture
    def scanner_service(self, mock_scan_repo):
        """Create an AgentScannerService with mocked repository."""
        with patch("registry.services.agent_scanner.get_security_scan_repository", return_value=mock_scan_repo):
            return AgentScannerService()

    def test_run_a2a_scanner_success(self, scanner_service, sample_agent_card):
        """Test successful scanner run."""
        mock_result = MagicMock()
        mock_result.stdout = '{"findings": [], "is_safe": true}'
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/test.json"
                with patch("os.unlink"):
                    result = scanner_service._run_a2a_scanner(
                        agent_card=sample_agent_card,
                        agent_path="/test-agent",
                        analyzers="basic",
                        timeout=30,
                    )

        assert "scan_results" in result
        assert "analysis_results" in result

    def test_run_a2a_scanner_timeout(self, scanner_service, sample_agent_card):
        """Test scanner timeout handling."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/test.json"
                with patch("os.unlink"):
                    with pytest.raises(RuntimeError, match="timed out"):
                        scanner_service._run_a2a_scanner(
                            agent_card=sample_agent_card,
                            agent_path="/test-agent",
                            analyzers="basic",
                            timeout=30,
                        )

    def test_run_a2a_scanner_error(self, scanner_service, sample_agent_card):
        """Test scanner error handling."""
        mock_error = subprocess.CalledProcessError(1, "cmd")
        mock_error.stderr = "Scanner error"

        with patch("subprocess.run", side_effect=mock_error):
            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/test.json"
                with patch("os.unlink"):
                    with pytest.raises(RuntimeError, match="Agent security scanner failed"):
                        scanner_service._run_a2a_scanner(
                            agent_card=sample_agent_card,
                            agent_path="/test-agent",
                            analyzers="basic",
                            timeout=30,
                        )

    def test_run_a2a_scanner_cleans_up_temp_file(self, scanner_service, sample_agent_card):
        """Test that temporary file is cleaned up."""
        mock_result = MagicMock()
        mock_result.stdout = '{"findings": []}'
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/test.json"
                with patch("os.unlink") as mock_unlink:
                    scanner_service._run_a2a_scanner(
                        agent_card=sample_agent_card,
                        agent_path="/test-agent",
                        analyzers="basic",
                        timeout=30,
                    )

        mock_unlink.assert_called_once_with("/tmp/test.json")

    def test_run_a2a_scanner_with_findings(self, scanner_service, sample_agent_card):
        """Test scanner with findings in output."""
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({
            "findings": [
                {"analyzer": "TestAnalyzer", "severity": "high"},
            ]
        })
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/test.json"
                with patch("os.unlink"):
                    result = scanner_service._run_a2a_scanner(
                        agent_card=sample_agent_card,
                        agent_path="/test-agent",
                        analyzers="basic",
                        timeout=30,
                    )

        assert "TestAnalyzer" in result["analysis_results"]

    def test_run_a2a_scanner_with_api_key(self, scanner_service, sample_agent_card):
        """Test scanner with API key set in environment."""
        mock_result = MagicMock()
        mock_result.stdout = '{"findings": []}'
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            with patch("tempfile.NamedTemporaryFile") as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/test.json"
                with patch("os.unlink"):
                    scanner_service._run_a2a_scanner(
                        agent_card=sample_agent_card,
                        agent_path="/test-agent",
                        analyzers="basic",
                        api_key="test-api-key",
                        timeout=30,
                    )

        call_args = mock_run.call_args
        env = call_args.kwargs.get("env", {})
        assert env.get("AZURE_OPENAI_API_KEY") == "test-api-key"
