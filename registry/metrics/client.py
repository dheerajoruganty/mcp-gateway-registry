"""
Metrics client and enhanced MCP client for registry service.

Provides both the basic metrics client and an enhanced MCP client service
that uses dependency injection for clean metrics collection.
"""

import os
import sys
import time
import logging
from typing import List, Dict, Optional
from contextlib import asynccontextmanager
from fastapi import Depends

# Import the main metrics client from metrics service
sys.path.append(os.path.join(os.path.dirname(__file__), '../../metrics-service'))
from metrics_client import MetricsClient as BaseMetricsClient, create_metrics_client as base_create_client
from .utils import extract_server_name_from_url

logger = logging.getLogger(__name__)


class MetricsClient(BaseMetricsClient):
    """Registry-specific metrics client."""
    pass


def create_metrics_client(service_name: str = "registry", **kwargs) -> MetricsClient:
    """Create a registry metrics client with default configuration."""
    return base_create_client(service_name=service_name, **kwargs)


class MetricsCollector:
    """
    Metrics collection service for MCP operations.
    
    Uses dependency injection to provide clean, testable metrics collection
    for MCP client calls and other registry operations.
    """
    
    def __init__(self, service_name: str = "registry"):
        self.metrics_client = create_metrics_client(service_name=service_name)
        self._enabled = True
    
    def is_enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._enabled
    
    def disable(self):
        """Disable metrics collection (useful for testing)."""
        self._enabled = False
    
    def enable(self):
        """Enable metrics collection."""
        self._enabled = True
    
    @asynccontextmanager
    async def track_tool_discovery(self, server_url: str):
        """
        Context manager to track tool discovery operations.
        
        Usage:
            async with metrics.track_tool_discovery(server_url) as tracker:
                tools = await get_tools_from_server(server_url)
                tracker.set_result(tools)
        """
        if not self._enabled:
            yield _NoOpTracker()
            return
            
        start_time = time.perf_counter()
        server_name = extract_server_name_from_url(server_url)
        tracker = _ToolDiscoveryTracker(
            self.metrics_client,
            server_name,
            server_url,
            start_time
        )
        
        try:
            yield tracker
        except Exception as e:
            tracker.set_error(e)
            raise
        finally:
            await tracker.finish()
    
    @asynccontextmanager
    async def track_health_check(self, server_url: str):
        """Context manager to track health check operations."""
        if not self._enabled:
            yield _NoOpTracker()
            return
            
        start_time = time.perf_counter()
        server_name = extract_server_name_from_url(server_url)
        tracker = _HealthCheckTracker(
            self.metrics_client,
            server_name,
            start_time
        )
        
        try:
            yield tracker
        except Exception as e:
            tracker.set_error(e)
            raise
        finally:
            await tracker.finish()


class _ToolDiscoveryTracker:
    """Tracker for tool discovery operations."""
    
    def __init__(self, metrics_client, server_name: str, server_url: str, start_time: float):
        self.metrics_client = metrics_client
        self.server_name = server_name
        self.server_url = server_url
        self.start_time = start_time
        self.success = False
        self.tools_count = 0
        self.error_code = None
    
    def set_result(self, tools: Optional[List[Dict]]):
        """Set the result of the tool discovery operation."""
        if tools is not None:
            self.success = True
            self.tools_count = len(tools)
    
    def set_error(self, error: Exception):
        """Set error information."""
        self.success = False
        self.error_code = type(error).__name__
    
    async def finish(self):
        """Emit metrics for the completed operation."""
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        
        try:
            # Emit discovery metric
            await self.metrics_client.emit_discovery_metric(
                query=f"tools_from_{self.server_name}",
                results_count=self.tools_count if self.success else 0,
                duration_ms=duration_ms
            )
            
            # Emit tool execution metric for MCP protocol interaction
            await self.metrics_client.emit_tool_execution_metric(
                tool_name="tools/list",
                server_path=self.server_url,
                server_name=self.server_name,
                success=self.success,
                duration_ms=duration_ms,
                output_size_bytes=self.tools_count * 100 if self.success else 0,
                error_code=self.error_code
            )
        except Exception as e:
            logger.debug(f"Failed to emit tool discovery metrics: {e}")


class _HealthCheckTracker:
    """Tracker for health check operations."""
    
    def __init__(self, metrics_client, server_name: str, start_time: float):
        self.metrics_client = metrics_client
        self.server_name = server_name
        self.start_time = start_time
        self.success = False
        self.error_code = None
    
    def set_success(self):
        """Mark the health check as successful."""
        self.success = True
    
    def set_error(self, error: Exception):
        """Set error information."""
        self.success = False
        self.error_code = type(error).__name__
    
    async def finish(self):
        """Emit metrics for the completed health check."""
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        
        try:
            await self.metrics_client.emit_health_metric(
                endpoint=f"/health/{self.server_name}",
                status_code=200 if self.success else 500,
                duration_ms=duration_ms,
                healthy=self.success
            )
        except Exception as e:
            logger.debug(f"Failed to emit health check metric: {e}")


class _NoOpTracker:
    """No-op tracker for when metrics are disabled."""
    
    def set_result(self, *args, **kwargs):
        pass
    
    def set_error(self, *args, **kwargs):
        pass
    
    def set_success(self, *args, **kwargs):
        pass
    
    async def finish(self):
        pass


class EnhancedMCPClientService:
    """
    Enhanced MCP client service with metrics collection.
    
    Uses dependency injection to cleanly add metrics to MCP operations
    without modifying the original client.
    """
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        # Import here to avoid circular imports
        from ..core.mcp_client import mcp_client_service
        self.original_client = mcp_client_service
    
    async def get_tools_from_server_with_server_info(
        self, 
        base_url: str, 
        server_info: dict = None
    ) -> Optional[List[Dict]]:
        """Get tools from MCP server with metrics collection."""
        async with self.metrics_collector.track_tool_discovery(base_url) as tracker:
            # Call the original client method
            result = await self.original_client.get_tools_from_server_with_server_info(
                base_url, server_info
            )
            
            # Set the result for metrics tracking
            tracker.set_result(result)
            
            return result


# Global instances
_metrics_collector = None
_enhanced_mcp_client = None


def get_metrics_collector() -> MetricsCollector:
    """Dependency to get the metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_enhanced_mcp_client(
    metrics_collector: MetricsCollector = Depends(get_metrics_collector)
) -> EnhancedMCPClientService:
    """Dependency to get the enhanced MCP client service."""
    return EnhancedMCPClientService(metrics_collector)


# Convenient dependency aliases
MetricsCollectorDep = Depends(get_metrics_collector)
EnhancedMCPClientDep = Depends(get_enhanced_mcp_client)