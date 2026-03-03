"""Pydantic models for mcpgw MCP server.

These models define the data structures returned by the registry API
and used by the MCP tools.
"""

from pydantic import BaseModel, Field


class ServerInfo(BaseModel):
    """Information about a registered MCP server."""

    server_name: str = Field(..., description="Display name of the server")
    path: str = Field(..., description="URL path for the server (e.g., '/fininfo')")
    description: str | None = Field(None, description="Server description")
    enabled: bool = Field(..., description="Whether the server is enabled")
    tags: list[str] = Field(default_factory=list, description="Server tags")
    tool_count: int | None = Field(None, description="Number of tools provided")


class AgentInfo(BaseModel):
    """Information about a registered agent."""

    agent_name: str = Field(..., description="Name of the agent")
    description: str | None = Field(None, description="Agent description")
    tags: list[str] = Field(default_factory=list, description="Agent tags")
    created_at: str | None = Field(None, description="Creation timestamp")


class SkillInfo(BaseModel):
    """Information about a registered skill."""

    skill_name: str = Field(..., description="Name of the skill")
    description: str | None = Field(None, description="Skill description")
    tags: list[str] = Field(default_factory=list, description="Skill tags")
    created_at: str | None = Field(None, description="Creation timestamp")


class ToolSearchResult(BaseModel):
    """Search result for semantic tool search."""

    tool_name: str = Field(..., description="Name of the tool")
    server_name: str = Field(..., description="Server providing the tool")
    description: str | None = Field(None, description="Tool description")
    score: float | None = Field(None, description="Relevance score (0-1)")
    path: str | None = Field(None, description="Server path")


class RegistryStats(BaseModel):
    """Registry statistics and health information."""

    total_servers: int = Field(..., description="Total number of servers")
    enabled_servers: int | None = Field(None, description="Number of enabled servers")
    total_tools: int | None = Field(None, description="Total number of tools")
    health_status: str = Field(default="unknown", description="Health status")


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error message")
    status: str = Field(default="failed", description="Status indicator")
    details: dict | None = Field(None, description="Additional error details")
