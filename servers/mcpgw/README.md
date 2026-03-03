# MCP Gateway Interaction Server (mcpgw)

This MCP server provides AI agents with tools to interact with the MCP Gateway Registry API. It acts as a thin protocol adapter, translating MCP tool calls into registry HTTP requests.

## Features

**Read-Only Operations:**
- `list_services` - List all registered MCP servers
- `list_agents` - List all registered agents
- `list_skills` - List all registered skills
- `intelligent_tool_finder` - Semantic search for tools
- `healthcheck` - Get registry health and statistics

**All tools require bearer token authentication.**

## Architecture

```
AI Agent → mcpgw Server → Registry API
         (MCP Protocol)  (HTTP/JSON)
         (Bearer Token)  (Forward Token)
```

The mcpgw server is a lightweight MCP protocol adapter (~250 lines) that:
- Forwards bearer tokens to registry APIs for authentication
- Uses pure HTTP client (no direct imports from registry)
- Maintains stateless operation with connection pooling
- Can be deployed independently from registry

## Setup

1. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
   *(Use `.venv\Scripts\activate` on Windows)*

2. **Install dependencies:**
   ```bash
   uv add --directory servers/mcpgw fastmcp pydantic httpx python-dotenv
   ```

3. **Configure environment variables:**
   Copy the `.env.template` file to `.env`:
   ```bash
   cp .env.template .env
   ```
   Edit the `.env` file and set the following variables:
   - `REGISTRY_BASE_URL`: The URL of your running MCP Gateway Registry (e.g., `http://localhost:7860`)
   - `REGISTRY_API_TIMEOUT`: Timeout for API calls in seconds (default: 30)
   - `MCP_SERVER_PORT`: Port for the mcpgw server (default: 8001)
   - `LOG_LEVEL`: Logging level (default: INFO)

## Authentication

**IMPORTANT**: All tools require bearer token authentication. Clients must provide an `Authorization: Bearer [token]` header with every request.

### Client Configuration

**Claude Desktop:**
```json
{
  "mcpServers": {
    "mcpgw": {
      "url": "http://localhost:8001",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN_HERE"
      }
    }
  }
}
```

**Python Client:**
```python
import httpx

headers = {"Authorization": "Bearer YOUR_TOKEN_HERE"}
response = httpx.post(
    "http://localhost:8001/mcp/list_services",
    headers=headers
)
```

### Token Requirements

- Format: Standard JWT bearer token
- Validation: Performed by registry (not by mcpgw)
- Scope: Token must have appropriate permissions in registry
- Without valid token: Returns HTTP 401 Unauthorized or 403 Forbidden

## Running the Server

```bash
python -m servers.mcpgw.server
```

The server will start and listen on the configured port (default: 8001).

## Available Tools

### list_services

List all MCP servers registered in the gateway.

```python
result = await list_services()
# Returns: {services: [...], total_count: N, enabled_count: N, status: "success"}
```

### list_agents

List all agents registered in the gateway.

```python
result = await list_agents()
# Returns: {agents: [...], total_count: N, status: "success"}
```

### list_skills

List all skills registered in the gateway.

```python
result = await list_skills()
# Returns: {skills: [...], total_count: N, status: "success"}
```

### intelligent_tool_finder

Search for tools using natural language semantic search.

```python
result = await intelligent_tool_finder(
    query="find information about weather",
    top_n=5
)
# Returns: {results: [...], query: "...", total_results: N, status: "success"}
```

### healthcheck

Get registry health status and statistics.

```python
result = await healthcheck()
# Returns: {total_servers: N, enabled_servers: M, health_status: "...", status: "success"}
```

## Registry API Endpoints Used

| MCP Tool | Registry Endpoint | Method |
|----------|-------------------|--------|
| `list_services` | `/servers` | GET |
| `list_agents` | `/agents` | GET |
| `list_skills` | `/skills` | GET |
| `intelligent_tool_finder` | `/semantic` | POST |
| `healthcheck` | `/api/stats` | GET |

## Migration from v1.0

**Removed Tools** (no longer available):
- Management tools: `toggle_service`, `register_service`, `remove_service`, `refresh_service`
- IAM tools: `create_group`, `delete_group`, `add_server_to_scopes_groups`, etc.
- Debug tools: `debug_auth_context`, `get_http_headers`

**Alternative for Removed Tools:**
- Use the registry web UI or management CLI for administrative tasks
- Use Keycloak admin console for IAM operations

**Core Functionality Preserved:**
- All search and list operations remain available
- Response formats are backward compatible
- Tool signatures unchanged (except removed tools)

**Breaking Change:**
- Authentication now **required** for all tools (previously optional)
- All clients must configure `Authorization: Bearer [token]` header

## Development

### Running Tests

```bash
pytest servers/mcpgw/tests/
```

### Code Quality

```bash
# Format code
ruff format servers/mcpgw/

# Lint code
ruff check servers/mcpgw/
```

## Troubleshooting

### "Registry API error: 401"
- Check that bearer token is configured in client
- Verify token is valid and not expired
- Ensure token has appropriate permissions in registry

### "Registry API error: 404"
- Verify `REGISTRY_BASE_URL` is correct
- Ensure registry is running and accessible

### "Connection timeout"
- Check registry is running and responsive
- Increase `REGISTRY_API_TIMEOUT` if needed
- Verify network connectivity

## Performance

- **Memory footprint**: <100MB (vs ~2GB in v1.0)
- **Dependencies**: 4 packages (vs 13+ in v1.0)
- **Code size**: ~250 lines (vs 2,083 in v1.0)
- **Startup time**: <1 second (vs ~30 seconds in v1.0)
- **Connection pooling**: Enabled for optimal performance
- **Horizontal scaling**: Fully stateless, can scale to any number of instances

## Technical Details

- **Language**: Python 3.12+
- **Framework**: FastMCP 2.0+
- **HTTP Client**: httpx with async support
- **Data Validation**: Pydantic models
- **Architecture**: Stateless with connection pooling
- **Authentication**: Pass-through bearer token forwarding
