# Writing Tests Guide

A comprehensive guide to writing effective tests for the MCP Gateway Registry project.

## Table of Contents

- [Test Writing Principles](#test-writing-principles)
- [Test Structure](#test-structure)
- [Test Patterns](#test-patterns)
- [Using Fixtures](#using-fixtures)
- [Mocking Strategies](#mocking-strategies)
- [Async Testing](#async-testing)
- [Factory Pattern](#factory-pattern)
- [Best Practices](#best-practices)
- [Examples](#examples)

## Test Writing Principles

### 1. Follow AAA Pattern

Organize tests using Arrange-Act-Assert:

```python
def test_register_server(server_service, sample_server):
    # Arrange - Set up test data and preconditions
    server_id = "test-server"
    server_info = sample_server

    # Act - Perform the action being tested
    result = server_service.register_server(server_id, server_info)

    # Assert - Verify the outcome
    assert result is not None
    assert result["id"] == server_id
```

### 2. One Assertion Per Test (When Possible)

Each test should verify one specific behavior:

```python
# Good - Tests one thing
def test_server_registration_succeeds(server_service, sample_server):
    result = server_service.register_server("test", sample_server)
    assert result is not None

def test_server_registration_stores_data(server_service, sample_server):
    result = server_service.register_server("test", sample_server)
    assert result["name"] == sample_server["name"]

# Avoid - Tests too many things
def test_server_registration(server_service, sample_server):
    result = server_service.register_server("test", sample_server)
    assert result is not None
    assert result["name"] == sample_server["name"]
    assert len(server_service.list_servers()) == 1
    assert server_service.get_server("test") == result
```

### 3. Descriptive Test Names

Use clear, descriptive names that explain what is being tested:

```python
# Good - Clear and descriptive
def test_register_server_with_valid_data_succeeds():
    pass

def test_register_server_with_duplicate_id_raises_error():
    pass

def test_list_servers_returns_empty_list_when_no_servers():
    pass

# Avoid - Vague names
def test_server():
    pass

def test_register():
    pass

def test_list():
    pass
```

## Test Structure

### File Organization

Organize tests to mirror the source code structure:

```
registry/
├── services/
│   ├── server_service.py
│   └── agent_service.py
└── api/
    └── routes.py

tests/
├── unit/
│   ├── services/
│   │   ├── test_server_service.py
│   │   └── test_agent_service.py
│   └── api/
│       └── test_routes.py
```

### Test Class Structure

Group related tests in classes:

```python
import pytest


@pytest.mark.unit
class TestServerService:
    """Tests for ServerService class."""

    def test_register_server_succeeds(self, server_service):
        """Test successful server registration."""
        pass

    def test_register_server_duplicate_fails(self, server_service):
        """Test that duplicate server IDs are rejected."""
        pass

    def test_list_servers_returns_all(self, server_service):
        """Test listing all registered servers."""
        pass


@pytest.mark.unit
class TestServerServiceValidation:
    """Tests for ServerService validation logic."""

    def test_validate_server_info_with_valid_data(self):
        """Test validation passes with valid server info."""
        pass

    def test_validate_server_info_rejects_missing_name(self):
        """Test validation fails when name is missing."""
        pass
```

## Test Patterns

### Unit Test Pattern

Test individual functions/methods in isolation:

```python
@pytest.mark.unit
def test_calculate_health_score():
    """Test health score calculation."""
    # Arrange
    server_status = {
        "available": True,
        "response_time": 100,
        "error_rate": 0.01
    }

    # Act
    score = calculate_health_score(server_status)

    # Assert
    assert 0.0 <= score <= 1.0
    assert score > 0.9  # Healthy server
```

### Integration Test Pattern

Test component interactions:

```python
@pytest.mark.integration
async def test_server_registration_workflow(
    server_service,
    health_service,
    sample_server,
):
    """Test complete server registration workflow."""
    # Register server
    server_id = "integration-test"
    result = server_service.register_server(server_id, sample_server)

    # Verify health monitoring started
    await asyncio.sleep(0.1)
    health_status = health_service.get_health_status(server_id)

    assert result is not None
    assert health_status is not None
```

### E2E Test Pattern

Test complete user workflows:

```python
@pytest.mark.e2e
@pytest.mark.slow
async def test_complete_agent_lifecycle(
    base_url,
    auth_headers,
    test_agent_data,
):
    """Test complete agent lifecycle: create, update, delete."""
    async with httpx.AsyncClient() as client:
        # Create agent
        response = await client.post(
            f"{base_url}/api/agents/register",
            headers=auth_headers,
            json=test_agent_data,
        )
        assert response.status_code == 200
        agent_path = response.json()["path"]

        # Update agent
        response = await client.put(
            f"{base_url}/api/agents/{agent_path}",
            headers=auth_headers,
            json={"description": "Updated"},
        )
        assert response.status_code == 200

        # Delete agent
        response = await client.delete(
            f"{base_url}/api/agents/{agent_path}",
            headers=auth_headers,
        )
        assert response.status_code in [200, 204]
```

## Using Fixtures

### Built-in Fixtures

Leverage pytest's built-in fixtures:

```python
def test_with_temp_directory(tmp_path):
    """Use tmp_path for temporary directories."""
    test_file = tmp_path / "test.json"
    test_file.write_text('{"key": "value"}')
    assert test_file.exists()


def test_with_monkeypatch(monkeypatch):
    """Use monkeypatch to modify environment."""
    monkeypatch.setenv("TEST_VAR", "test_value")
    assert os.getenv("TEST_VAR") == "test_value"
```

### Custom Fixtures

Create reusable test fixtures in `conftest.py`:

```python
# tests/conftest.py
import pytest


@pytest.fixture
def sample_server():
    """Create a sample server for testing."""
    return {
        "name": "Test Server",
        "url": "http://test.example.com",
        "description": "Test server for unit tests"
    }


@pytest.fixture
def authenticated_client(test_client, auth_token):
    """Create an authenticated test client."""
    test_client.headers["Authorization"] = f"Bearer {auth_token}"
    return test_client
```

### Fixture Scopes

Use appropriate fixture scopes:

```python
@pytest.fixture(scope="function")  # Default - new instance per test
def temp_database():
    """Create a fresh database for each test."""
    db = create_test_database()
    yield db
    db.cleanup()


@pytest.fixture(scope="class")  # Shared across test class
def shared_resource():
    """Create resource shared by all tests in class."""
    resource = expensive_setup()
    yield resource
    resource.cleanup()


@pytest.fixture(scope="module")  # Shared across module
def module_database():
    """Create database shared by all tests in module."""
    db = create_test_database()
    yield db
    db.cleanup()
```

## Mocking Strategies

### Using unittest.mock

Mock external dependencies:

```python
from unittest.mock import Mock, AsyncMock, patch


def test_with_mock_dependency():
    """Test with mocked dependency."""
    # Create mock
    mock_service = Mock()
    mock_service.get_data.return_value = {"key": "value"}

    # Use mock
    result = function_under_test(mock_service)

    # Verify mock was called
    mock_service.get_data.assert_called_once()
    assert result is not None


async def test_with_async_mock():
    """Test with async mock."""
    mock_service = AsyncMock()
    mock_service.fetch_data.return_value = {"data": "test"}

    result = await async_function_under_test(mock_service)

    mock_service.fetch_data.assert_called_once()
    assert result == {"data": "test"}
```

### Patching Functions

Use `@patch` decorator or context manager:

```python
@patch('registry.services.external_api_call')
def test_with_patched_function(mock_api):
    """Test with patched external function."""
    mock_api.return_value = {"status": "success"}

    result = function_that_calls_api()

    mock_api.assert_called_once()
    assert result["status"] == "success"


def test_with_patch_context_manager():
    """Test using patch as context manager."""
    with patch('registry.services.external_api_call') as mock_api:
        mock_api.return_value = {"status": "success"}
        result = function_that_calls_api()
        assert result["status"] == "success"
```

### Mock Configuration

Configure mocks for specific behaviors:

```python
def test_mock_configuration():
    """Test with configured mock."""
    mock_service = Mock()

    # Configure return values
    mock_service.get.return_value = "value"
    mock_service.list.return_value = ["item1", "item2"]

    # Configure side effects
    mock_service.process.side_effect = [1, 2, 3]

    # Configure exceptions
    mock_service.fail.side_effect = ValueError("Test error")

    # Use configured mock
    assert mock_service.get() == "value"
    assert mock_service.process() == 1
    assert mock_service.process() == 2

    with pytest.raises(ValueError):
        mock_service.fail()
```

## Async Testing

### Async Test Functions

Use `async def` for async tests:

```python
@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await async_function()
    assert result is not None


@pytest.mark.asyncio
async def test_async_client(async_client):
    """Test with async HTTP client."""
    response = await async_client.get("/api/endpoint")
    assert response.status_code == 200
```

### Async Fixtures

Create async fixtures:

```python
@pytest.fixture
async def async_database():
    """Create async database connection."""
    db = await create_async_database()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_with_async_fixture(async_database):
    """Test using async fixture."""
    result = await async_database.query("SELECT * FROM table")
    assert result is not None
```

### Testing Async Context Managers

Test async context managers:

```python
@pytest.mark.asyncio
async def test_async_context_manager():
    """Test async context manager."""
    async with AsyncResource() as resource:
        result = await resource.do_something()
        assert result is not None
```

## Factory Pattern

### Creating Test Data Factories

Use factories to generate test data:

```python
# tests/fixtures/factories.py
def ServerInfoFactory(
    name: str = "Test Server",
    url: str = "http://test.example.com",
    **kwargs
) -> Dict[str, Any]:
    """Factory for creating server info dictionaries."""
    return {
        "name": name,
        "url": url,
        "description": kwargs.get("description", "Test server"),
        "tags": kwargs.get("tags", ["test"]),
        "version": kwargs.get("version", "1.0.0"),
    }


def create_multiple_servers(count: int = 3) -> Dict[str, Dict[str, Any]]:
    """Create multiple test servers."""
    return {
        f"server-{i}": ServerInfoFactory(
            name=f"Test Server {i}",
            url=f"http://server{i}.example.com"
        )
        for i in range(count)
    }


def create_server_with_tools(num_tools: int = 5) -> Dict[str, Any]:
    """Create a server with tools."""
    server = ServerInfoFactory()
    server["tools"] = [
        {
            "name": f"tool_{i}",
            "description": f"Test tool {i}",
            "parameters": {}
        }
        for i in range(num_tools)
    ]
    return server
```

### Using Factories in Tests

```python
def test_with_factory(server_service):
    """Test using factory-created data."""
    # Create single server
    server = ServerInfoFactory(name="Custom Server")
    result = server_service.register_server("test", server)
    assert result["name"] == "Custom Server"


def test_with_multiple_factories(server_service):
    """Test with multiple factory-created servers."""
    servers = create_multiple_servers(count=5)

    for server_id, server_info in servers.items():
        server_service.register_server(server_id, server_info)

    assert len(server_service.list_servers()) == 5
```

## Best Practices

### 1. Test Independence

Tests should be independent and not rely on execution order:

```python
# Good - Independent tests
def test_register_server(server_service, sample_server):
    """Test registers its own server."""
    result = server_service.register_server("test1", sample_server)
    assert result is not None


def test_list_servers(server_service, sample_server):
    """Test creates its own data."""
    server_service.register_server("test2", sample_server)
    servers = server_service.list_servers()
    assert len(servers) >= 1


# Avoid - Tests depend on each other
def test_register_server_first(server_service, sample_server):
    """Test creates server for other tests."""
    server_service.register_server("shared", sample_server)


def test_list_servers_second(server_service):
    """Test assumes server from previous test exists."""
    servers = server_service.list_servers()
    assert "shared" in servers  # Fragile!
```

### 2. Test Edge Cases

Test boundary conditions and edge cases:

```python
def test_edge_cases():
    """Test edge cases and boundary conditions."""
    # Empty input
    assert process_data([]) == []

    # Single item
    assert process_data([1]) == [1]

    # Large input
    assert len(process_data(range(10000))) == 10000

    # Null/None input
    with pytest.raises(ValueError):
        process_data(None)

    # Invalid type
    with pytest.raises(TypeError):
        process_data("not a list")
```

### 3. Test Error Handling

Verify error handling behavior:

```python
def test_error_handling():
    """Test error handling."""
    # Test specific exception
    with pytest.raises(ValueError):
        function_that_raises_value_error()

    # Test exception message
    with pytest.raises(ValueError, match="Invalid input"):
        function_with_specific_error()

    # Test exception attributes
    with pytest.raises(CustomError) as exc_info:
        function_with_custom_error()

    assert exc_info.value.code == 400
    assert "error" in str(exc_info.value)
```

### 4. Use Parametrize for Similar Tests

Use `@pytest.mark.parametrize` to test multiple inputs:

```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
    (0, 0),
    (-1, -2),
])
def test_double(input, expected):
    """Test double function with multiple inputs."""
    assert double(input) == expected


@pytest.mark.parametrize("server_id,should_fail", [
    ("valid-id", False),
    ("valid_id", False),
    ("invalid id", True),  # Spaces not allowed
    ("", True),  # Empty string
    ("a" * 256, True),  # Too long
])
def test_server_id_validation(server_id, should_fail):
    """Test server ID validation with various inputs."""
    if should_fail:
        with pytest.raises(ValueError):
            validate_server_id(server_id)
    else:
        validate_server_id(server_id)  # Should not raise
```

### 5. Clean Up Resources

Always clean up resources after tests:

```python
@pytest.fixture
def temp_file():
    """Create temporary file and clean up after."""
    file_path = Path("temp_test_file.txt")
    file_path.write_text("test data")

    yield file_path

    # Cleanup
    if file_path.exists():
        file_path.unlink()


@pytest.fixture
def database_connection():
    """Create database connection and close after."""
    connection = create_connection()

    yield connection

    # Cleanup
    connection.close()
```

## Examples

### Complete Unit Test Example

```python
import pytest
from unittest.mock import Mock
from registry.services.server_service import ServerService


@pytest.mark.unit
class TestServerService:
    """Tests for ServerService."""

    def test_register_server_with_valid_data(
        self,
        server_service,
        sample_server,
    ):
        """Test registering a server with valid data."""
        # Arrange
        server_id = "test-server"

        # Act
        result = server_service.register_server(server_id, sample_server)

        # Assert
        assert result is not None
        assert result["id"] == server_id
        assert result["name"] == sample_server["name"]

    def test_register_server_with_duplicate_id_raises_error(
        self,
        server_service,
        sample_server,
    ):
        """Test that duplicate server IDs raise an error."""
        # Arrange
        server_id = "test-server"
        server_service.register_server(server_id, sample_server)

        # Act & Assert
        with pytest.raises(ValueError, match="already registered"):
            server_service.register_server(server_id, sample_server)

    def test_list_servers_returns_all_registered_servers(
        self,
        server_service,
    ):
        """Test listing all registered servers."""
        # Arrange
        servers = create_multiple_servers(count=3)
        for server_id, server_info in servers.items():
            server_service.register_server(server_id, server_info)

        # Act
        result = server_service.list_servers()

        # Assert
        assert len(result) == 3
        assert all(s["id"] in servers for s in result)
```

### Complete Integration Test Example

```python
import pytest
import httpx


@pytest.mark.integration
class TestAgentAPI:
    """Integration tests for Agent API."""

    async def test_complete_agent_workflow(
        self,
        base_url,
        auth_headers,
    ):
        """Test complete agent registration workflow."""
        async with httpx.AsyncClient() as client:
            # Create agent
            agent_data = {
                "name": "Test Agent",
                "description": "Integration test agent",
                "url": "http://test.example.com",
            }

            response = await client.post(
                f"{base_url}/api/agents/register",
                headers=auth_headers,
                json=agent_data,
            )

            assert response.status_code == 200
            agent_path = response.json()["path"]

            # Retrieve agent
            response = await client.get(
                f"{base_url}/api/agents/{agent_path}",
                headers=auth_headers,
            )

            assert response.status_code == 200
            agent = response.json()
            assert agent["name"] == "Test Agent"

            # Update agent
            response = await client.put(
                f"{base_url}/api/agents/{agent_path}",
                headers=auth_headers,
                json={"description": "Updated description"},
            )

            assert response.status_code == 200

            # Delete agent
            response = await client.delete(
                f"{base_url}/api/agents/{agent_path}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204]
```

## Summary

Key points for writing effective tests:

1. Follow AAA pattern (Arrange, Act, Assert)
2. Write descriptive test names
3. Test one thing per test
4. Use fixtures for reusable test data
5. Mock external dependencies
6. Test edge cases and error handling
7. Use parametrize for similar tests
8. Keep tests independent
9. Clean up resources
10. Maintain good test coverage

For more information, see:
- [Testing Guide](./README.md)
- [Test Maintenance](./MAINTENANCE.md)
