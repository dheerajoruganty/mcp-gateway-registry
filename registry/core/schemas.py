from typing import Any

from pydantic import BaseModel, Field


class ServerInfo(BaseModel):
    """Server information model."""
    server_name: str
    description: str = ""
    path: str
    proxy_pass_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    num_tools: int = 0
    num_stars: int = 0
    is_python: bool = False
    license: str = "N/A"
    tool_list: list[dict[str, Any]] = Field(default_factory=list)
    is_enabled: bool = False
    transport: str | None = Field(default="auto", description="Preferred transport: sse, streamable-http, or auto")
    supported_transports: list[str] = Field(default_factory=lambda: ["streamable-http"], description="List of supported transports")
    mcp_endpoint: str | None = Field(default=None, description="Custom /mcp endpoint path")
    sse_endpoint: str | None = Field(default=None, description="Custom /sse endpoint path")


class ToolDescription(BaseModel):
    """Parsed tool description sections."""
    main: str = "No description available."
    args: str | None = None
    returns: str | None = None
    raises: str | None = None


class ToolInfo(BaseModel):
    """Tool information model."""
    name: str
    parsed_description: ToolDescription
    schema: dict[str, Any] = Field(default_factory=dict)
    server_path: str | None = None
    server_name: str | None = None


class HealthStatus(BaseModel):
    """Health check status model."""
    status: str
    last_checked_iso: str | None = None
    num_tools: int = 0


class SessionData(BaseModel):
    """Session data model."""
    username: str
    auth_method: str = "traditional"
    provider: str = "local"


class ServiceRegistrationRequest(BaseModel):
    """Service registration request model."""
    name: str = Field(..., min_length=1)
    description: str = ""
    path: str = Field(..., min_length=1)
    proxy_pass_url: str = Field(..., min_length=1)
    tags: str = ""
    num_tools: int = Field(0, ge=0)
    num_stars: int = Field(0, ge=0)
    is_python: bool = False
    license: str = "N/A"
    transport: str | None = Field(default="auto", description="Preferred transport: sse, streamable-http, or auto")
    supported_transports: str = Field(default="streamable-http", description="Comma-separated list of supported transports")
    mcp_endpoint: str | None = Field(default=None, description="Custom /mcp endpoint path")
    sse_endpoint: str | None = Field(default=None, description="Custom /sse endpoint path")


class OAuth2Provider(BaseModel):
    """OAuth2 provider information."""
    name: str
    display_name: str
    icon: str | None = None


class FaissMetadata(BaseModel):
    """FAISS metadata model."""
    id: int
    text_for_embedding: str
    full_server_info: ServerInfo
