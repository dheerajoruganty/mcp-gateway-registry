from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class ServerInfo(BaseModel):
    """Server information model."""
    server_name: str
    description: str = ""
    path: str
    proxy_pass_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    num_tools: int = 0
    num_stars: int = 0
    is_python: bool = False
    license: str = "N/A"
    tool_list: List[Dict[str, Any]] = Field(default_factory=list)
    is_enabled: bool = False
    transport: Optional[str] = Field(default="auto", description="Preferred transport: sse, streamable-http, or auto")
    supported_transports: List[str] = Field(default_factory=lambda: ["streamable-http"], description="List of supported transports")
    mcp_endpoint: Optional[str] = Field(
        default=None,
        description="Full URL for the MCP streamable-http endpoint. If set, used directly for health checks and client connections instead of appending /mcp to proxy_pass_url. Example: 'https://server.com/custom-path'"
    )
    sse_endpoint: Optional[str] = Field(
        default=None,
        description="Full URL for the SSE endpoint. If set, used directly for health checks and client connections instead of appending /sse to proxy_pass_url. Example: 'https://server.com/events'"
    )


class ToolDescription(BaseModel):
    """Parsed tool description sections."""
    main: str = "No description available."
    args: Optional[str] = None
    returns: Optional[str] = None
    raises: Optional[str] = None


class ToolInfo(BaseModel):
    """Tool information model."""
    name: str
    parsed_description: ToolDescription
    tool_schema: Dict[str, Any] = Field(default_factory=dict, alias="schema")
    server_path: Optional[str] = None
    server_name: Optional[str] = None

    class Config:
        populate_by_name = True


class HealthStatus(BaseModel):
    """Health check status model."""
    status: str
    last_checked_iso: Optional[str] = None
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
    transport: Optional[str] = Field(default="auto", description="Preferred transport: sse, streamable-http, or auto")
    supported_transports: str = Field(default="streamable-http", description="Comma-separated list of supported transports")
    mcp_endpoint: Optional[str] = Field(
        default=None,
        description="Full URL for the MCP streamable-http endpoint. If set, used directly for health checks and client connections instead of appending /mcp to proxy_pass_url. Example: 'https://server.com/custom-path'"
    )
    sse_endpoint: Optional[str] = Field(
        default=None,
        description="Full URL for the SSE endpoint. If set, used directly for health checks and client connections instead of appending /sse to proxy_pass_url. Example: 'https://server.com/events'"
    )


class OAuth2Provider(BaseModel):
    """OAuth2 provider information."""
    name: str
    display_name: str
    icon: Optional[str] = None


class FaissMetadata(BaseModel):
    """FAISS metadata model."""
    id: int
    text_for_embedding: str
    full_server_info: ServerInfo 