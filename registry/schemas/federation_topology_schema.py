"""
Unified federation topology schemas.

Provides Pydantic models for the unified topology API that represents
all federation sources (local, peer, anthropic, asor) in a single view.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FederationSourceType(str, Enum):
    """Types of federation sources."""
    LOCAL = "local"
    PEER = "peer"
    ANTHROPIC = "anthropic"
    ASOR = "asor"


class UnifiedFederationNode(BaseModel):
    """
    Unified node for all federation source types.

    Represents a single node in the federation topology graph,
    which could be the local registry, a peer registry, Anthropic MCP,
    or ASOR agents source.
    """
    id: str = Field(..., description="Unique identifier for the node")
    type: FederationSourceType = Field(
        ...,
        description="Type of federation source"
    )
    name: str = Field(..., description="Display name for the node")
    status: Literal["healthy", "error", "disabled", "unknown"] = Field(
        default="unknown",
        description="Current status of the federation source"
    )
    enabled: bool = Field(
        default=True,
        description="Whether the federation source is enabled"
    )
    endpoint: Optional[str] = Field(
        default=None,
        description="Endpoint URL for the federation source"
    )
    servers_count: int = Field(
        default=0,
        description="Number of servers synced from this source"
    )
    agents_count: int = Field(
        default=0,
        description="Number of agents synced from this source"
    )
    last_sync: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last successful sync"
    )
    sync_mode: Optional[str] = Field(
        default=None,
        description="Sync mode (all, whitelist, tag_filter)"
    )
    sync_interval_minutes: Optional[int] = Field(
        default=None,
        description="Sync interval in minutes"
    )
    sync_on_startup: Optional[bool] = Field(
        default=None,
        description="Whether to sync on startup"
    )
    position: Dict[str, float] = Field(
        default_factory=lambda: {"x": 0, "y": 0},
        description="Position for visualization"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "anthropic",
                "type": "anthropic",
                "name": "Anthropic MCP",
                "status": "healthy",
                "enabled": True,
                "endpoint": "https://registry.modelcontextprotocol.io",
                "servers_count": 3,
                "agents_count": 0,
                "last_sync": "2024-01-15T10:30:00Z",
                "sync_on_startup": True,
                "position": {"x": 200, "y": 300}
            }
        }
    }


class FederationEdge(BaseModel):
    """
    Edge connecting federation sources in the topology graph.

    Represents a sync relationship between two federation nodes,
    typically from a source (peer, anthropic, asor) to the local registry.
    """
    id: str = Field(..., description="Unique identifier for the edge")
    source: str = Field(
        ...,
        description="ID of the source node"
    )
    target: str = Field(
        ...,
        description="ID of the target node"
    )
    status: Literal["healthy", "error", "disabled", "unknown"] = Field(
        default="unknown",
        description="Status of the sync connection"
    )
    animated: bool = Field(
        default=False,
        description="Whether to animate the edge (indicates active sync)"
    )
    servers_synced: int = Field(
        default=0,
        description="Number of servers synced through this connection"
    )
    agents_synced: int = Field(
        default=0,
        description="Number of agents synced through this connection"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "edge-anthropic",
                "source": "anthropic",
                "target": "this-registry",
                "status": "healthy",
                "animated": True,
                "servers_synced": 3,
                "agents_synced": 0
            }
        }
    }


class TopologyMetadata(BaseModel):
    """Metadata about the topology response."""
    total_sources: int = Field(
        default=0,
        description="Total number of federation sources"
    )
    enabled_sources: int = Field(
        default=0,
        description="Number of enabled federation sources"
    )
    total_servers: int = Field(
        default=0,
        description="Total servers across all sources"
    )
    total_agents: int = Field(
        default=0,
        description="Total agents across all sources"
    )
    last_updated: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the topology was last updated"
    )


class UnifiedTopologyResponse(BaseModel):
    """
    Complete unified topology response.

    Contains all federation nodes, edges, and metadata for
    rendering the federation visualization.
    """
    nodes: List[UnifiedFederationNode] = Field(
        default_factory=list,
        description="List of all federation nodes"
    )
    edges: List[FederationEdge] = Field(
        default_factory=list,
        description="List of edges connecting nodes"
    )
    metadata: TopologyMetadata = Field(
        default_factory=TopologyMetadata,
        description="Topology metadata and statistics"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "nodes": [
                    {
                        "id": "this-registry",
                        "type": "local",
                        "name": "This Registry",
                        "status": "healthy",
                        "enabled": True,
                        "servers_count": 10,
                        "agents_count": 5,
                        "position": {"x": 400, "y": 300}
                    },
                    {
                        "id": "anthropic",
                        "type": "anthropic",
                        "name": "Anthropic MCP",
                        "status": "healthy",
                        "enabled": True,
                        "endpoint": "https://registry.modelcontextprotocol.io",
                        "servers_count": 3,
                        "agents_count": 0,
                        "position": {"x": 200, "y": 150}
                    }
                ],
                "edges": [
                    {
                        "id": "edge-anthropic",
                        "source": "anthropic",
                        "target": "this-registry",
                        "status": "healthy",
                        "animated": True,
                        "servers_synced": 3,
                        "agents_synced": 0
                    }
                ],
                "metadata": {
                    "total_sources": 2,
                    "enabled_sources": 2,
                    "total_servers": 13,
                    "total_agents": 5,
                    "last_updated": "2024-01-15T10:30:00Z"
                }
            }
        }
    }


class FederationSourceConfig(BaseModel):
    """Configuration update for a federation source (Anthropic/ASOR)."""
    enabled: Optional[bool] = Field(
        default=None,
        description="Enable or disable the federation source"
    )
    endpoint: Optional[str] = Field(
        default=None,
        description="Endpoint URL for the federation source"
    )
    sync_on_startup: Optional[bool] = Field(
        default=None,
        description="Whether to sync on startup"
    )
    auth_env_var: Optional[str] = Field(
        default=None,
        description="Environment variable name for auth token (ASOR only)"
    )


class FederationSyncResult(BaseModel):
    """Result of a federation sync operation."""
    success: bool = Field(
        ...,
        description="Whether the sync was successful"
    )
    source: str = Field(
        ...,
        description="Federation source that was synced"
    )
    servers_synced: int = Field(
        default=0,
        description="Number of servers synced"
    )
    agents_synced: int = Field(
        default=0,
        description="Number of agents synced"
    )
    duration_seconds: float = Field(
        default=0.0,
        description="Duration of the sync operation in seconds"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if sync failed"
    )
    synced_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when sync completed"
    )
