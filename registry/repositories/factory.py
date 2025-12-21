"""
Repository factory - creates concrete implementations based on configuration.
"""

import logging
from typing import Optional

from ..core.config import settings
from .interfaces import (
    ServerRepositoryBase,
    AgentRepositoryBase,
    SearchRepositoryBase,
)

logger = logging.getLogger(__name__)

# Singleton instances
_server_repo: Optional[ServerRepositoryBase] = None
_agent_repo: Optional[AgentRepositoryBase] = None
_search_repo: Optional[SearchRepositoryBase] = None


def get_server_repository() -> ServerRepositoryBase:
    """Get server repository singleton."""
    global _server_repo

    if _server_repo is not None:
        return _server_repo

    backend = settings.storage_backend
    logger.info(f"Creating server repository with backend: {backend}")

    if backend == "opensearch":
        from .opensearch.server_repository import OpenSearchServerRepository
        _server_repo = OpenSearchServerRepository()
    else:
        from .file.server_repository import FileServerRepository
        _server_repo = FileServerRepository()

    return _server_repo


def get_agent_repository() -> AgentRepositoryBase:
    """Get agent repository singleton."""
    global _agent_repo

    if _agent_repo is not None:
        return _agent_repo

    backend = settings.storage_backend
    logger.info(f"Creating agent repository with backend: {backend}")

    if backend == "opensearch":
        from .opensearch.agent_repository import OpenSearchAgentRepository
        _agent_repo = OpenSearchAgentRepository()
    else:
        from .file.agent_repository import FileAgentRepository
        _agent_repo = FileAgentRepository()

    return _agent_repo


def get_search_repository() -> SearchRepositoryBase:
    """Get search repository singleton."""
    global _search_repo

    if _search_repo is not None:
        return _search_repo

    backend = settings.storage_backend
    logger.info(f"Creating search repository with backend: {backend}")

    if backend == "opensearch":
        from .opensearch.search_repository import OpenSearchSearchRepository
        _search_repo = OpenSearchSearchRepository()
    else:
        from .file.search_repository import FaissSearchRepository
        _search_repo = FaissSearchRepository()

    return _search_repo


def reset_repositories() -> None:
    """Reset all repository singletons. USE ONLY IN TESTS."""
    global _server_repo, _agent_repo, _search_repo
    _server_repo = None
    _agent_repo = None
    _search_repo = None
