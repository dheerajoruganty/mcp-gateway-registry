"""
Unit tests for file-based security scan repository.
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from registry.repositories.file.security_scan_repository import FileSecurityScanRepository


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: FileSecurityScanRepository Initialization
# =============================================================================


@pytest.mark.unit
class TestFileSecurityScanRepositoryInit:
    """Tests for FileSecurityScanRepository initialization."""

    def test_init_creates_empty_scans(self):
        """Test that init creates empty scans dict."""
        repo = FileSecurityScanRepository()

        assert repo._scans == {}
        assert repo._scans_dir == Path.home() / "mcp-gateway" / "security_scans"


# =============================================================================
# TEST: FileSecurityScanRepository Load All
# =============================================================================


@pytest.mark.unit
class TestFileSecurityScanRepositoryLoadAll:
    """Tests for FileSecurityScanRepository load_all method."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileSecurityScanRepository()
        repo._scans_dir = temp_dir / "security_scans"
        return repo

    @pytest.mark.asyncio
    async def test_load_all_no_directory(self, repo):
        """Test loading when directory doesn't exist."""
        await repo.load_all()

        assert repo._scans == {}

    @pytest.mark.asyncio
    async def test_load_all_empty_directory(self, repo):
        """Test loading from empty directory."""
        repo._scans_dir.mkdir(parents=True, exist_ok=True)

        await repo.load_all()

        assert repo._scans == {}

    @pytest.mark.asyncio
    async def test_load_all_with_valid_scans(self, repo):
        """Test loading valid scan files."""
        repo._scans_dir.mkdir(parents=True, exist_ok=True)

        # Create valid scan file
        scan_data = {
            "server_path": "/test-server",
            "scan_status": "completed",
            "findings": []
        }
        scan_file = repo._scans_dir / "test-server_scan.json"
        with open(scan_file, "w") as f:
            json.dump(scan_data, f)

        await repo.load_all()

        assert "/test-server" in repo._scans
        assert repo._scans["/test-server"]["scan_status"] == "completed"

    @pytest.mark.asyncio
    async def test_load_all_skips_invalid_json(self, repo):
        """Test that invalid JSON files are skipped."""
        repo._scans_dir.mkdir(parents=True, exist_ok=True)

        # Create invalid JSON file
        invalid_file = repo._scans_dir / "invalid.json"
        invalid_file.write_text("not valid json")

        await repo.load_all()

        assert repo._scans == {}

    @pytest.mark.asyncio
    async def test_load_all_skips_invalid_format(self, repo):
        """Test that files with invalid format are skipped."""
        repo._scans_dir.mkdir(parents=True, exist_ok=True)

        # Create file missing server_path
        invalid_file = repo._scans_dir / "invalid_format.json"
        invalid_file.write_text('{"scan_status": "completed"}')

        await repo.load_all()

        assert repo._scans == {}

    @pytest.mark.asyncio
    async def test_load_all_multiple_files(self, repo):
        """Test loading multiple scan files."""
        repo._scans_dir.mkdir(parents=True, exist_ok=True)

        # Create multiple scan files
        for i in range(3):
            scan_data = {
                "server_path": f"/server-{i}",
                "scan_status": "completed"
            }
            scan_file = repo._scans_dir / f"server-{i}_scan.json"
            with open(scan_file, "w") as f:
                json.dump(scan_data, f)

        await repo.load_all()

        assert len(repo._scans) == 3


# =============================================================================
# TEST: FileSecurityScanRepository CRUD Operations
# =============================================================================


@pytest.mark.unit
class TestFileSecurityScanRepositoryCRUD:
    """Tests for FileSecurityScanRepository CRUD operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def repo(self, temp_dir):
        """Create a repository with temporary directory."""
        repo = FileSecurityScanRepository()
        repo._scans_dir = temp_dir / "security_scans"
        return repo

    @pytest.mark.asyncio
    async def test_get_existing(self, repo):
        """Test getting an existing scan."""
        repo._scans = {
            "/test-server": {"server_path": "/test-server", "scan_status": "completed"}
        }

        result = await repo.get("/test-server")

        assert result is not None
        assert result["scan_status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo):
        """Test getting a nonexistent scan."""
        repo._scans = {}

        result = await repo.get("/nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_latest(self, repo):
        """Test get_latest (alias for get)."""
        repo._scans = {
            "/test-server": {"server_path": "/test-server", "scan_status": "completed"}
        }

        result = await repo.get_latest("/test-server")

        assert result is not None
        assert result["scan_status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_all(self, repo):
        """Test listing all scans."""
        repo._scans = {
            "/server1": {"server_path": "/server1", "scan_status": "completed"},
            "/server2": {"server_path": "/server2", "scan_status": "pending"},
        }

        result = await repo.list_all()

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_create_success(self, repo):
        """Test creating a new scan result."""
        scan_result = {
            "server_path": "/test-server",
            "scan_status": "completed",
            "findings": [{"severity": "high", "message": "Test finding"}]
        }

        result = await repo.create(scan_result)

        assert result is True
        assert "/test-server" in repo._scans
        # Check file was created
        expected_file = repo._scans_dir / "test-server_scan.json"
        assert expected_file.exists()

    @pytest.mark.asyncio
    async def test_create_missing_server_path(self, repo):
        """Test creating scan without server_path fails."""
        scan_result = {"scan_status": "completed"}

        result = await repo.create(scan_result)

        assert result is False

    @pytest.mark.asyncio
    async def test_create_overwrites_existing(self, repo):
        """Test creating scan overwrites existing."""
        # Create initial scan
        scan_result1 = {
            "server_path": "/test-server",
            "scan_status": "pending"
        }
        await repo.create(scan_result1)

        # Create updated scan
        scan_result2 = {
            "server_path": "/test-server",
            "scan_status": "completed"
        }
        result = await repo.create(scan_result2)

        assert result is True
        assert repo._scans["/test-server"]["scan_status"] == "completed"

    @pytest.mark.asyncio
    async def test_create_sanitizes_path(self, repo):
        """Test that server path is sanitized in filename."""
        scan_result = {
            "server_path": "/namespace/test-server",
            "scan_status": "completed"
        }

        result = await repo.create(scan_result)

        assert result is True
        expected_file = repo._scans_dir / "namespace_test-server_scan.json"
        assert expected_file.exists()


# =============================================================================
# TEST: FileSecurityScanRepository Query Methods
# =============================================================================


@pytest.mark.unit
class TestFileSecurityScanRepositoryQuery:
    """Tests for FileSecurityScanRepository query methods."""

    @pytest.fixture
    def repo(self):
        """Create a repository for testing."""
        return FileSecurityScanRepository()

    @pytest.mark.asyncio
    async def test_query_by_status_found(self, repo):
        """Test querying by status finds matching scans."""
        repo._scans = {
            "/server1": {"server_path": "/server1", "scan_status": "completed"},
            "/server2": {"server_path": "/server2", "scan_status": "pending"},
            "/server3": {"server_path": "/server3", "scan_status": "completed"},
        }

        result = await repo.query_by_status("completed")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_query_by_status_not_found(self, repo):
        """Test querying by status returns empty when none match."""
        repo._scans = {
            "/server1": {"server_path": "/server1", "scan_status": "completed"},
        }

        result = await repo.query_by_status("failed")

        assert result == []

    @pytest.mark.asyncio
    async def test_query_by_status_empty(self, repo):
        """Test querying empty scans returns empty list."""
        repo._scans = {}

        result = await repo.query_by_status("completed")

        assert result == []
