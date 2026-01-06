# Testing Guide

Comprehensive testing documentation for the MCP Gateway Registry project.

## Table of Contents

- [Quick Start](#quick-start)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Categories](#test-categories)
- [Coverage Requirements](#coverage-requirements)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

## Quick Start

Run all tests:

```bash
make test
```

Run specific test categories:

```bash
# Unit tests only (fast)
make test-unit

# Integration tests
make test-integration

# E2E tests (slow)
make test-e2e

# With coverage report
make test-coverage
```

Run tests using pytest directly:

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/unit/test_server_service.py

# Specific test class
uv run pytest tests/unit/test_server_service.py::TestServerService

# Specific test function
uv run pytest tests/unit/test_server_service.py::TestServerService::test_register_server

# With verbose output
uv run pytest -v

# With coverage
uv run pytest --cov=registry --cov-report=html
```

## Test Structure

The test suite is organized into three main categories:

```
tests/
├── unit/                    # Unit tests (fast, isolated)
│   ├── services/           # Service layer tests
│   ├── api/                # API endpoint tests
│   ├── core/               # Core functionality tests
│   └── agents/             # Agent-specific tests
├── integration/            # Integration tests (slower)
│   ├── test_server_integration.py
│   ├── test_api_integration.py
│   └── test_e2e_workflows.py
├── fixtures/               # Shared test fixtures
│   └── factories.py        # Factory functions for test data
├── conftest.py             # Shared pytest configuration
└── reports/                # Test reports and coverage data
```

### Test File Organization

- **Unit tests**: Test individual components in isolation
  - Mock external dependencies
  - Fast execution (< 1 second per test)
  - High coverage of edge cases

- **Integration tests**: Test component interactions
  - May use real services (databases, files)
  - Moderate execution time (< 5 seconds per test)
  - Test realistic workflows

- **E2E tests**: Test complete user workflows
  - Test entire system end-to-end
  - Slower execution (5-30 seconds per test)
  - Marked with `@pytest.mark.slow`

## Running Tests

### Using Make Commands

The project includes convenient Make targets for running tests:

```bash
# Run all tests
make test

# Run only unit tests (fast)
make test-unit

# Run only integration tests
make test-integration

# Run E2E tests
make test-e2e

# Run with coverage report
make test-coverage

# Run and open HTML coverage report
make test-coverage-html
```

### Using Pytest Directly

For more control, use pytest commands:

```bash
# Run all tests
uv run pytest

# Run tests with specific markers
uv run pytest -m unit           # Only unit tests
uv run pytest -m integration    # Only integration tests
uv run pytest -m "not slow"     # Skip slow tests

# Run tests in parallel (faster)
uv run pytest -n auto           # Auto-detect CPU count

# Run with verbose output
uv run pytest -v

# Show print statements
uv run pytest -s

# Run specific tests by keyword
uv run pytest -k "server"       # All tests with "server" in name

# Stop on first failure
uv run pytest -x

# Run last failed tests
uv run pytest --lf

# Run failed tests first
uv run pytest --ff
```

### Integration Test Requirements

Integration and E2E tests may require:

1. **Authentication tokens**: Generate tokens before running:
   ```bash
   ./keycloak/setup/generate-agent-token.sh admin-bot
   ./keycloak/setup/generate-agent-token.sh lob1-bot
   ./keycloak/setup/generate-agent-token.sh lob2-bot
   ```

2. **Running services**: Ensure Docker containers are running:
   ```bash
   docker-compose up -d
   ```

3. **Environment variables**:
   ```bash
   export BASE_URL="http://localhost"
   export TOKEN_FILE=".oauth-tokens/admin-bot-token.json"
   ```

## Test Categories

Tests are organized using pytest markers:

### Available Markers

- `@pytest.mark.unit` - Unit tests (fast, isolated)
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.slow` - Slow tests (> 5 seconds)
- `@pytest.mark.auth` - Authentication/authorization tests
- `@pytest.mark.servers` - Server management tests
- `@pytest.mark.agents` - Agent-specific tests
- `@pytest.mark.search` - Search functionality tests
- `@pytest.mark.health` - Health monitoring tests

### Running Tests by Marker

```bash
# Run only unit tests
uv run pytest -m unit

# Run integration tests
uv run pytest -m integration

# Run E2E tests
uv run pytest -m e2e

# Skip slow tests
uv run pytest -m "not slow"

# Run auth and agent tests
uv run pytest -m "auth or agents"

# Run integration but not slow tests
uv run pytest -m "integration and not slow"
```

## Coverage Requirements

The project maintains **80% minimum code coverage**.

### Checking Coverage

```bash
# Run tests with coverage report
uv run pytest --cov=registry --cov-report=term-missing

# Generate HTML coverage report
uv run pytest --cov=registry --cov-report=html

# Open HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Coverage Configuration

Coverage settings are configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = [
    "--cov=registry",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-fail-under=80",
]
```

### What Gets Covered

Coverage includes:
- All source code in `registry/` directory
- Excludes: tests, migrations, __init__.py files
- Reports missing lines for easy identification

## CI/CD Integration

Tests run automatically in CI/CD pipelines on:
- Every pull request
- Every push to main branch
- Nightly scheduled runs

### GitHub Actions

The project uses GitHub Actions for CI/CD. Test workflows are defined in:

```
.github/workflows/
├── test.yml           # Main test workflow
├── coverage.yml       # Coverage reporting
└── integration.yml    # Integration test workflow
```

### Pre-commit Hooks

Install pre-commit hooks to run tests before commits:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

## Troubleshooting

### Common Issues

#### 1. Token File Not Found

**Error**: `Token file not found: .oauth-tokens/admin-bot-token.json`

**Solution**: Generate authentication tokens:
```bash
./keycloak/setup/generate-agent-token.sh admin-bot
```

#### 2. Docker Containers Not Running

**Error**: `Cannot connect to gateway at http://localhost`

**Solution**: Start Docker containers:
```bash
docker-compose up -d
```

#### 3. Import Errors

**Error**: `ModuleNotFoundError: No module named 'registry'`

**Solution**: Ensure you're using `uv run`:
```bash
uv run pytest  # Correct
pytest         # May fail if environment not activated
```

#### 4. Fixture Not Found

**Error**: `fixture 'some_fixture' not found`

**Solution**: Check fixture is defined in:
- `tests/conftest.py` (shared fixtures)
- Test file's conftest.py
- Imported from fixtures module

#### 5. Slow Tests

**Issue**: Tests taking too long

**Solution**: Skip slow tests during development:
```bash
uv run pytest -m "not slow"
```

#### 6. Failed Async Tests

**Error**: `RuntimeError: Event loop is closed`

**Solution**: Check async fixtures are properly defined:
```python
@pytest.fixture
async def async_client():
    async with AsyncClient() as client:
        yield client
```

#### 7. Coverage Too Low

**Error**: `FAIL Required test coverage of 80% not reached`

**Solution**: Add tests for uncovered code:
```bash
# Check which lines are missing
uv run pytest --cov=registry --cov-report=term-missing

# Generate detailed HTML report
uv run pytest --cov=registry --cov-report=html
open htmlcov/index.html
```

### Debug Mode

Run tests in debug mode for detailed output:

```bash
# Show print statements
uv run pytest -s

# Verbose output
uv run pytest -v

# Very verbose (shows fixtures)
uv run pytest -vv

# Show local variables on failure
uv run pytest -l

# Enter debugger on failure
uv run pytest --pdb
```

### Logging During Tests

Enable logging output:

```bash
# Show all logs
uv run pytest --log-cli-level=DEBUG

# Show only INFO and above
uv run pytest --log-cli-level=INFO

# Log to file
uv run pytest --log-file=tests/reports/test.log
```

## Additional Resources

- [Writing Tests Guide](./WRITING_TESTS.md) - How to write effective tests
- [Test Maintenance Guide](./MAINTENANCE.md) - Maintaining test suite health
- [Pytest Documentation](https://docs.pytest.org/) - Official pytest docs
- [Coverage.py Documentation](https://coverage.readthedocs.io/) - Coverage tool docs

## Getting Help

If you encounter issues:

1. Check this troubleshooting guide
2. Review test output for error messages
3. Check relevant documentation
4. Ask in team chat or create an issue

## Summary

Key commands to remember:

```bash
# Development workflow
make test-unit                    # Quick unit tests
make test-coverage                # Full test with coverage
uv run pytest -m "not slow"      # Skip slow tests

# Before committing
make test                         # Run all tests
pre-commit run --all-files       # Run all checks

# Debugging
uv run pytest -v -s              # Verbose with prints
uv run pytest --pdb              # Debug on failure
```
