"""OpenSearch-based repository for hybrid search (BM25 + k-NN)."""

import logging
from typing import Dict, Any, Optional, List

from opensearchpy import AsyncOpenSearch

from ...core.config import settings
from ...schemas.agent_models import AgentCard
from ..interfaces import SearchRepositoryBase
from .client import get_opensearch_client, get_index_name

logger = logging.getLogger(__name__)


class OpenSearchSearchRepository(SearchRepositoryBase):
    """OpenSearch implementation with hybrid search (BM25 + k-NN)."""

    def __init__(self):
        self._client: Optional[AsyncOpenSearch] = None
        self._index_name = get_index_name(settings.opensearch_index_embeddings)
        self._embedding_model = None

    async def _get_client(self) -> AsyncOpenSearch:
        """Get OpenSearch client."""
        if self._client is None:
            self._client = await get_opensearch_client()
        return self._client

    async def _get_embedding_model(self):
        """Lazy load embedding model."""
        if self._embedding_model is None:
            from ...embeddings import create_embeddings_client
            self._embedding_model = create_embeddings_client(
                provider=settings.embeddings_provider,
                model_name=settings.embeddings_model_name,
                model_dir=settings.embeddings_model_dir,
                api_key=settings.embeddings_api_key,
                api_base=settings.embeddings_api_base,
                aws_region=settings.embeddings_aws_region,
                embedding_dimension=settings.embeddings_model_dimensions,
            )
        return self._embedding_model

    def _path_to_doc_id(self, path: str) -> str:
        """Convert path to document ID."""
        return path.replace("/", "_").strip("_")

    async def initialize(self) -> None:
        """Initialize the search service."""
        logger.info(f"Initializing OpenSearch hybrid search on index: {self._index_name}")
        client = await self._get_client()
        
        try:
            exists = await client.indices.exists(index=self._index_name)
            if exists:
                logger.info(f"Search index {self._index_name} exists")
            else:
                logger.warning(f"Search index {self._index_name} does not exist")
        except Exception as e:
            logger.error(f"Failed to check search index: {e}")

    async def index_server(
        self,
        path: str,
        server_info: Dict[str, Any],
        is_enabled: bool = False,
    ) -> None:
        """Index a server for search."""
        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        # Build text for embedding
        text_parts = [
            server_info.get("server_name", ""),
            server_info.get("description", ""),
        ]

        # Add tags
        tags = server_info.get("tags", [])
        if tags:
            text_parts.append("Tags: " + ", ".join(tags))

        # Add tool names and descriptions
        for tool in server_info.get("tool_list", []):
            text_parts.append(tool.get("name", ""))
            text_parts.append(tool.get("description", ""))

        text_for_embedding = " ".join(filter(None, text_parts))

        # Generate embedding
        model = await self._get_embedding_model()
        embedding = model.encode([text_for_embedding])[0].tolist()

        # Prepare document
        doc = {
            "entity_type": "mcp_server",
            "path": path,
            "name": server_info.get("server_name", ""),
            "description": server_info.get("description", ""),
            "tags": server_info.get("tags", []),
            "is_enabled": is_enabled,
            "text_for_embedding": text_for_embedding,
            "embedding": embedding,
            "tools": [
                {"name": t.get("name"), "description": t.get("description")}
                for t in server_info.get("tool_list", [])
            ],
            "metadata": server_info,
            "indexed_at": server_info.get("updated_at", server_info.get("registered_at"))
        }

        try:
            await client.index(
                index=self._index_name,
                id=doc_id,
                body=doc,
                refresh=True
            )
            logger.info(f"Indexed server '{server_info.get('server_name')}' for search")
        except Exception as e:
            logger.error(f"Failed to index server in search: {e}", exc_info=True)

    async def index_agent(
        self,
        path: str,
        agent_card: AgentCard,
        is_enabled: bool = False,
    ) -> None:
        """Index an agent for search."""
        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        # Build text for embedding
        text_parts = [
            agent_card.name,
            agent_card.description or "",
        ]

        # Add tags
        tags = agent_card.tags or []
        if tags:
            text_parts.append("Tags: " + ", ".join(tags))

        # Add skill names and descriptions
        for skill in agent_card.skills or []:
            text_parts.append(skill.name)
            text_parts.append(skill.description or "")

        text_for_embedding = " ".join(filter(None, text_parts))

        # Generate embedding
        model = await self._get_embedding_model()
        embedding = model.encode([text_for_embedding])[0].tolist()

        # Prepare document
        doc = {
            "entity_type": "a2a_agent",
            "path": path,
            "name": agent_card.name,
            "description": agent_card.description or "",
            "tags": agent_card.tags or [],
            "is_enabled": is_enabled,
            "text_for_embedding": text_for_embedding,
            "embedding": embedding,
            "skills": [
                {"id": s.id, "name": s.name, "description": s.description}
                for s in (agent_card.skills or [])
            ],
            "metadata": agent_card.model_dump(mode="json"),
            "indexed_at": agent_card.updated_at or agent_card.registered_at
        }

        try:
            await client.index(
                index=self._index_name,
                id=doc_id,
                body=doc,
                refresh=True
            )
            logger.info(f"Indexed agent '{agent_card.name}' for search")
        except Exception as e:
            logger.error(f"Failed to index agent in search: {e}", exc_info=True)

    async def remove_entity(self, path: str) -> None:
        """Remove entity from search index."""
        client = await self._get_client()
        doc_id = self._path_to_doc_id(path)

        try:
            await client.delete(
                index=self._index_name,
                id=doc_id,
                refresh=True
            )
            logger.info(f"Removed entity '{path}' from search index")
        except Exception as e:
            logger.debug(f"Entity '{path}' not found in search index or error: {e}")

    async def search(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        max_results: int = 10,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Perform hybrid search (BM25 + k-NN)."""
        client = await self._get_client()

        # Generate query embedding
        model = await self._get_embedding_model()
        query_embedding = model.encode([query])[0].tolist()

        # Build filter for entity types
        filters = []
        if entity_types:
            filters.append({"terms": {"entity_type": entity_types}})

        # Hybrid search query
        search_body = {
            "query": {
                "hybrid": {
                    "queries": [
                        # BM25 keyword search
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["name^3", "tags^2.5", "description^2", "text_for_embedding"],
                                "type": "best_fields"
                            }
                        },
                        # k-NN vector search
                        {
                            "knn": {
                                "embedding": {
                                    "vector": query_embedding,
                                    "k": max_results * 2
                                }
                            }
                        }
                    ]
                }
            },
            "size": max_results * 2,
            "_source": ["entity_type", "path", "name", "description", "tags", "is_enabled", "tools", "skills"]
        }

        # Add filters if any
        if filters:
            search_body["query"] = {
                "bool": {
                    "must": [search_body["query"]],
                    "filter": filters
                }
            }

        try:
            response = await client.search(
                index=self._index_name,
                body=search_body,
                params={"search_pipeline": "hybrid-search-pipeline"}
            )

            # Group results by entity type
            servers = []
            agents = []
            tools = []

            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                result = {
                    "path": source["path"],
                    "name": source["name"],
                    "description": source.get("description", ""),
                    "relevance_score": hit["_score"],
                    "is_enabled": source.get("is_enabled", False),
                    "tags": source.get("tags", [])
                }

                if source["entity_type"] == "mcp_server":
                    result["server_name"] = source["name"]
                    servers.append(result)
                    
                    # Extract tools
                    for tool in source.get("tools", []):
                        tools.append({
                            "tool_name": tool["name"],
                            "server_path": source["path"],
                            "description": tool.get("description", ""),
                            "relevance_score": hit["_score"]
                        })
                        
                elif source["entity_type"] == "a2a_agent":
                    result["agent_name"] = source["name"]
                    agents.append(result)

            return {
                "servers": servers[:max_results],
                "tools": tools[:max_results],
                "agents": agents[:max_results]
            }

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            return {"servers": [], "tools": [], "agents": []}
