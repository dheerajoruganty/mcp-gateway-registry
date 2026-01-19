"""
Unit tests for metrics client module.
"""

import logging
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from registry.metrics.client import (
    MetricsClient,
    MetricsCollector,
    _NoOpTracker,
    _ToolDiscoveryTracker,
    _HealthCheckTracker,
    create_metrics_client,
    get_metrics_collector,
)


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: MetricsClient
# =============================================================================


@pytest.mark.unit
class TestMetricsClient:
    """Tests for MetricsClient class."""

    def test_init_defaults(self):
        """Test MetricsClient initialization with defaults."""
        client = MetricsClient()
        assert client.service_name == "registry"
        assert client.service_version == "1.0.0"

    def test_init_custom_values(self):
        """Test MetricsClient initialization with custom values."""
        client = MetricsClient(
            service_name="custom-service",
            service_version="2.0.0",
            metrics_url="http://custom:8080",
            api_key="test-key"
        )
        assert client.service_name == "custom-service"
        assert client.service_version == "2.0.0"
        assert client.api_key == "test-key"

    @pytest.mark.asyncio
    async def test_emit_metric_no_api_key(self):
        """Test _emit_metric returns False without API key."""
        client = MetricsClient(api_key="")
        result = await client._emit_metric("test_metric")
        assert result is False

    @pytest.mark.asyncio
    async def test_emit_metric_success(self):
        """Test _emit_metric success."""
        client = MetricsClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client._emit_metric(
                metric_type="test_metric",
                value=1.0,
                duration_ms=100.0,
                dimensions={"key": "value"}
            )

            assert result is True
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_metric_failure(self):
        """Test _emit_metric failure."""
        client = MetricsClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client._emit_metric("test_metric")

            assert result is False

    @pytest.mark.asyncio
    async def test_emit_metric_exception(self):
        """Test _emit_metric handles exception."""
        client = MetricsClient(api_key="test-key")

        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection error")

            result = await client._emit_metric("test_metric")

            assert result is False

    @pytest.mark.asyncio
    async def test_emit_registry_metric(self):
        """Test emit_registry_metric method."""
        client = MetricsClient(api_key="test-key")

        with patch.object(client, '_emit_metric', new_callable=AsyncMock) as mock_emit:
            mock_emit.return_value = True

            result = await client.emit_registry_metric(
                operation="create",
                resource_type="server",
                success=True,
                duration_ms=100.0,
                resource_id="test-id"
            )

            assert result is True
            mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_discovery_metric(self):
        """Test emit_discovery_metric method."""
        client = MetricsClient(api_key="test-key")

        with patch.object(client, '_emit_metric', new_callable=AsyncMock) as mock_emit:
            mock_emit.return_value = True

            result = await client.emit_discovery_metric(
                query="test query",
                results_count=5,
                duration_ms=50.0
            )

            assert result is True
            mock_emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_tool_execution_metric(self):
        """Test emit_tool_execution_metric method."""
        client = MetricsClient(api_key="test-key")

        with patch.object(client, '_emit_metric', new_callable=AsyncMock) as mock_emit:
            mock_emit.return_value = True

            result = await client.emit_tool_execution_metric(
                tool_name="test_tool",
                server_path="/test-server",
                server_name="Test Server",
                success=True,
                duration_ms=200.0
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_emit_health_metric(self):
        """Test emit_health_metric method."""
        client = MetricsClient(api_key="test-key")

        with patch.object(client, '_emit_metric', new_callable=AsyncMock) as mock_emit:
            mock_emit.return_value = True

            result = await client.emit_health_metric(
                endpoint="/health",
                status_code=200,
                duration_ms=10.0,
                healthy=True
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_emit_custom_metric(self):
        """Test emit_custom_metric method."""
        client = MetricsClient(api_key="test-key")

        with patch.object(client, '_emit_metric', new_callable=AsyncMock) as mock_emit:
            mock_emit.return_value = True

            result = await client.emit_custom_metric(
                metric_name="custom_metric",
                value=42.0,
                dimensions={"extra": "data"}
            )

            assert result is True


# =============================================================================
# TEST: create_metrics_client
# =============================================================================


@pytest.mark.unit
class TestCreateMetricsClient:
    """Tests for create_metrics_client function."""

    def test_create_default(self):
        """Test creating client with defaults."""
        client = create_metrics_client()
        assert isinstance(client, MetricsClient)
        assert client.service_name == "registry"

    def test_create_custom_service(self):
        """Test creating client with custom service name."""
        client = create_metrics_client(service_name="custom")
        assert client.service_name == "custom"


# =============================================================================
# TEST: MetricsCollector
# =============================================================================


@pytest.mark.unit
class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_init(self):
        """Test MetricsCollector initialization."""
        collector = MetricsCollector()
        assert collector.is_enabled() is True

    def test_enable_disable(self):
        """Test enable/disable functionality."""
        collector = MetricsCollector()

        collector.disable()
        assert collector.is_enabled() is False

        collector.enable()
        assert collector.is_enabled() is True

    @pytest.mark.asyncio
    async def test_track_tool_discovery_disabled(self):
        """Test track_tool_discovery when disabled."""
        collector = MetricsCollector()
        collector.disable()

        async with collector.track_tool_discovery("http://test/server") as tracker:
            assert isinstance(tracker, _NoOpTracker)

    @pytest.mark.asyncio
    async def test_track_tool_discovery_enabled(self):
        """Test track_tool_discovery when enabled."""
        collector = MetricsCollector()

        with patch.object(collector.metrics_client, 'emit_discovery_metric', new_callable=AsyncMock):
            with patch.object(collector.metrics_client, 'emit_tool_execution_metric', new_callable=AsyncMock):
                async with collector.track_tool_discovery("http://test/server") as tracker:
                    assert isinstance(tracker, _ToolDiscoveryTracker)
                    tracker.set_result([{"tool": "test"}])

    @pytest.mark.asyncio
    async def test_track_tool_discovery_error(self):
        """Test track_tool_discovery handles errors."""
        collector = MetricsCollector()

        with patch.object(collector.metrics_client, 'emit_discovery_metric', new_callable=AsyncMock):
            with patch.object(collector.metrics_client, 'emit_tool_execution_metric', new_callable=AsyncMock):
                with pytest.raises(ValueError):
                    async with collector.track_tool_discovery("http://test/server") as tracker:
                        raise ValueError("Test error")

    @pytest.mark.asyncio
    async def test_track_health_check_disabled(self):
        """Test track_health_check when disabled."""
        collector = MetricsCollector()
        collector.disable()

        async with collector.track_health_check("http://test/server") as tracker:
            assert isinstance(tracker, _NoOpTracker)

    @pytest.mark.asyncio
    async def test_track_health_check_enabled(self):
        """Test track_health_check when enabled."""
        collector = MetricsCollector()

        with patch.object(collector.metrics_client, 'emit_health_metric', new_callable=AsyncMock):
            async with collector.track_health_check("http://test/server") as tracker:
                assert isinstance(tracker, _HealthCheckTracker)
                tracker.set_success()


# =============================================================================
# TEST: _ToolDiscoveryTracker
# =============================================================================


@pytest.mark.unit
class TestToolDiscoveryTracker:
    """Tests for _ToolDiscoveryTracker class."""

    @pytest.fixture
    def mock_metrics_client(self):
        """Create a mock metrics client."""
        mock = MagicMock()
        mock.emit_discovery_metric = AsyncMock()
        mock.emit_tool_execution_metric = AsyncMock()
        return mock

    def test_init(self, mock_metrics_client):
        """Test tracker initialization."""
        tracker = _ToolDiscoveryTracker(
            mock_metrics_client,
            "test-server",
            "http://test/server",
            0.0
        )
        assert tracker.success is False
        assert tracker.tools_count == 0

    def test_set_result_success(self, mock_metrics_client):
        """Test set_result with tools."""
        tracker = _ToolDiscoveryTracker(
            mock_metrics_client,
            "test-server",
            "http://test/server",
            0.0
        )
        tracker.set_result([{"tool": "t1"}, {"tool": "t2"}])
        assert tracker.success is True
        assert tracker.tools_count == 2

    def test_set_result_none(self, mock_metrics_client):
        """Test set_result with None."""
        tracker = _ToolDiscoveryTracker(
            mock_metrics_client,
            "test-server",
            "http://test/server",
            0.0
        )
        tracker.set_result(None)
        assert tracker.success is False

    def test_set_error(self, mock_metrics_client):
        """Test set_error."""
        tracker = _ToolDiscoveryTracker(
            mock_metrics_client,
            "test-server",
            "http://test/server",
            0.0
        )
        tracker.set_error(ValueError("test"))
        assert tracker.success is False
        assert tracker.error_code == "ValueError"

    @pytest.mark.asyncio
    async def test_finish(self, mock_metrics_client):
        """Test finish emits metrics."""
        import time
        tracker = _ToolDiscoveryTracker(
            mock_metrics_client,
            "test-server",
            "http://test/server",
            time.perf_counter()
        )
        tracker.set_result([{"tool": "t1"}])

        await tracker.finish()

        mock_metrics_client.emit_discovery_metric.assert_called_once()
        mock_metrics_client.emit_tool_execution_metric.assert_called_once()


# =============================================================================
# TEST: _HealthCheckTracker
# =============================================================================


@pytest.mark.unit
class TestHealthCheckTracker:
    """Tests for _HealthCheckTracker class."""

    @pytest.fixture
    def mock_metrics_client(self):
        """Create a mock metrics client."""
        mock = MagicMock()
        mock.emit_health_metric = AsyncMock()
        return mock

    def test_init(self, mock_metrics_client):
        """Test tracker initialization."""
        tracker = _HealthCheckTracker(
            mock_metrics_client,
            "test-server",
            0.0
        )
        assert tracker.success is False

    def test_set_success(self, mock_metrics_client):
        """Test set_success."""
        tracker = _HealthCheckTracker(
            mock_metrics_client,
            "test-server",
            0.0
        )
        tracker.set_success()
        assert tracker.success is True

    def test_set_error(self, mock_metrics_client):
        """Test set_error."""
        tracker = _HealthCheckTracker(
            mock_metrics_client,
            "test-server",
            0.0
        )
        tracker.set_error(TimeoutError("timeout"))
        assert tracker.success is False
        assert tracker.error_code == "TimeoutError"

    @pytest.mark.asyncio
    async def test_finish(self, mock_metrics_client):
        """Test finish emits metrics."""
        import time
        tracker = _HealthCheckTracker(
            mock_metrics_client,
            "test-server",
            time.perf_counter()
        )
        tracker.set_success()

        await tracker.finish()

        mock_metrics_client.emit_health_metric.assert_called_once()


# =============================================================================
# TEST: _NoOpTracker
# =============================================================================


@pytest.mark.unit
class TestNoOpTracker:
    """Tests for _NoOpTracker class."""

    def test_set_result(self):
        """Test set_result is no-op."""
        tracker = _NoOpTracker()
        tracker.set_result([{"tool": "test"}])  # Should not raise

    def test_set_error(self):
        """Test set_error is no-op."""
        tracker = _NoOpTracker()
        tracker.set_error(ValueError("test"))  # Should not raise

    def test_set_success(self):
        """Test set_success is no-op."""
        tracker = _NoOpTracker()
        tracker.set_success()  # Should not raise

    @pytest.mark.asyncio
    async def test_finish(self):
        """Test finish is no-op."""
        tracker = _NoOpTracker()
        await tracker.finish()  # Should not raise


# =============================================================================
# TEST: get_metrics_collector
# =============================================================================


@pytest.mark.unit
class TestGetMetricsCollector:
    """Tests for get_metrics_collector function."""

    def test_returns_collector(self):
        """Test that it returns a MetricsCollector instance."""
        # Reset global state
        import registry.metrics.client as client_module
        client_module._metrics_collector = None

        collector = get_metrics_collector()
        assert isinstance(collector, MetricsCollector)

    def test_returns_singleton(self):
        """Test that it returns the same instance."""
        # Reset global state
        import registry.metrics.client as client_module
        client_module._metrics_collector = None

        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        assert collector1 is collector2
