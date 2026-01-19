"""
Unit tests for FAISS-based search repository.

Note: FaissSearchRepository is a thin wrapper around faiss_service, which
initializes lazily. We test the repository methods by mocking the faiss_service
after instantiation.
"""

import logging
from unittest.mock import MagicMock, AsyncMock

import pytest


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: FaissSearchRepository Index Operations
# =============================================================================


@pytest.mark.unit
class TestFaissSearchRepositoryIndex:
    """Tests for FaissSearchRepository indexing operations."""

    @pytest.fixture
    def mock_faiss_service(self):
        """Create a mock faiss service."""
        mock = MagicMock()
        mock.add_or_update_entity = AsyncMock()
        mock.remove_entity = AsyncMock()
        mock.rebuild_index = AsyncMock()
        mock.search_mixed = AsyncMock(return_value={"mcp_server": [], "a2a_agent": []})
        return mock

    @pytest.fixture
    def repo(self, mock_faiss_service):
        """Create a repository with mocked faiss service."""
        # Import fresh to avoid cached module state
        import importlib
        import registry.repositories.file.search_repository as search_repo_module

        importlib.reload(search_repo_module)

        repo = search_repo_module.FaissSearchRepository()
        # Replace the faiss_service with mock after instantiation
        repo.faiss_service = mock_faiss_service
        return repo

    @pytest.mark.asyncio
    async def test_index_entity(self, repo, mock_faiss_service):
        """Test indexing an entity."""
        entity_data = {"name": "Test", "description": "A test entity"}

        await repo.index_entity(
            entity_path="/test",
            entity_data=entity_data,
            entity_type="server",
            is_enabled=True
        )

        mock_faiss_service.add_or_update_entity.assert_called_once_with(
            entity_path="/test",
            entity_info=entity_data,
            entity_type="server",
            is_enabled=True
        )

    @pytest.mark.asyncio
    async def test_remove_entity(self, repo, mock_faiss_service):
        """Test removing an entity from index."""
        await repo.remove_entity("/test")

        mock_faiss_service.remove_entity.assert_called_once_with("/test")

    @pytest.mark.asyncio
    async def test_rebuild_index(self, repo, mock_faiss_service):
        """Test rebuilding the index."""
        await repo.rebuild_index()

        mock_faiss_service.rebuild_index.assert_called_once()

    @pytest.mark.asyncio
    async def test_index_server(self, repo, mock_faiss_service):
        """Test indexing a server (convenience method)."""
        server_data = {"name": "Test Server"}

        await repo.index_server("/test-server", server_data, True)

        mock_faiss_service.add_or_update_entity.assert_called_once_with(
            entity_path="/test-server",
            entity_info=server_data,
            entity_type="server",
            is_enabled=True
        )

    @pytest.mark.asyncio
    async def test_index_agent(self, repo, mock_faiss_service):
        """Test indexing an agent (convenience method)."""
        agent_data = {"name": "Test Agent"}

        await repo.index_agent("/test-agent", agent_data, False)

        mock_faiss_service.add_or_update_entity.assert_called_once_with(
            entity_path="/test-agent",
            entity_info=agent_data,
            entity_type="agent",
            is_enabled=False
        )


# =============================================================================
# TEST: FaissSearchRepository Search Operations
# =============================================================================


@pytest.mark.unit
class TestFaissSearchRepositorySearch:
    """Tests for FaissSearchRepository search operations."""

    @pytest.fixture
    def mock_faiss_service(self):
        """Create a mock faiss service."""
        mock = MagicMock()
        mock.search_mixed = AsyncMock(return_value={
            "mcp_server": [{"path": "/test-server", "score": 0.9}],
            "a2a_agent": []
        })
        return mock

    @pytest.fixture
    def repo(self, mock_faiss_service):
        """Create a repository with mocked faiss service."""
        import importlib
        import registry.repositories.file.search_repository as search_repo_module

        importlib.reload(search_repo_module)

        repo = search_repo_module.FaissSearchRepository()
        repo.faiss_service = mock_faiss_service
        return repo

    @pytest.mark.asyncio
    async def test_search_default_params(self, repo, mock_faiss_service):
        """Test search with default parameters."""
        result = await repo.search("test query")

        mock_faiss_service.search_mixed.assert_called_once_with(
            query="test query",
            entity_types=None,
            max_results=10
        )
        assert "mcp_server" in result

    @pytest.mark.asyncio
    async def test_search_with_entity_types(self, repo, mock_faiss_service):
        """Test search with entity type filter."""
        result = await repo.search(
            "test query",
            entity_types=["mcp_server"],
            max_results=5
        )

        mock_faiss_service.search_mixed.assert_called_once_with(
            query="test query",
            entity_types=["mcp_server"],
            max_results=5
        )

    @pytest.mark.asyncio
    async def test_search_with_max_results(self, repo, mock_faiss_service):
        """Test search with custom max_results."""
        await repo.search("test", max_results=20)

        mock_faiss_service.search_mixed.assert_called_once_with(
            query="test",
            entity_types=None,
            max_results=20
        )


# =============================================================================
# TEST: FaissSearchRepository Initialize
# =============================================================================


@pytest.mark.unit
class TestFaissSearchRepositoryInitialize:
    """Tests for FaissSearchRepository initialize method."""

    @pytest.fixture
    def repo(self):
        """Create a repository with mocked faiss service."""
        import importlib
        import registry.repositories.file.search_repository as search_repo_module

        importlib.reload(search_repo_module)

        repo = search_repo_module.FaissSearchRepository()
        repo.faiss_service = MagicMock()
        return repo

    @pytest.mark.asyncio
    async def test_initialize_does_nothing(self, repo):
        """Test that initialize is a no-op (faiss service initializes itself)."""
        # Should not raise
        await repo.initialize()
