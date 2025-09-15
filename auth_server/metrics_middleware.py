"""
FastAPI middleware for automatic metrics collection in the auth server.

This middleware automatically tracks authentication metrics for all requests
without requiring changes to individual endpoints.
"""

import time
import logging
import asyncio
import hashlib
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import os
import sys

# Import metrics client
sys.path.append(os.path.join(os.path.dirname(__file__), '../metrics-service'))
from metrics_client import create_metrics_client

logger = logging.getLogger(__name__)


class AuthMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically collect authentication metrics.
    
    Tracks timing, success/failure rates, and authentication methods
    for all requests passing through the auth server.
    """
    
    def __init__(self, app, service_name: str = "auth-server"):
        super().__init__(app)
        self.metrics_client = create_metrics_client(
            service_name=service_name,
            service_version="1.0.0"
        )
    
    def hash_username(self, username: str) -> str:
        """Hash username for privacy in metrics."""
        if not username:
            return ""
        return hashlib.sha256(username.encode()).hexdigest()[:12]
    
    def extract_server_name_from_url(self, original_url: str) -> str:
        """Extract server name from the original URL."""
        if not original_url:
            return "unknown"
        
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(original_url)
            path = parsed_url.path.strip('/')
            path_parts = path.split('/') if path else []
            return path_parts[0] if path_parts else "unknown"
        except Exception:
            return "unknown"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and collect metrics.
        """
        # Skip metrics collection for non-validation endpoints
        if not request.url.path.startswith('/validate'):
            return await call_next(request)
        
        # Start timing
        start_time = time.perf_counter()
        
        # Extract metadata for metrics
        server_name = "unknown"
        user_hash = ""
        auth_method = "unknown"
        
        # Extract server name from original URL header
        original_url = request.headers.get("X-Original-URL")
        if original_url:
            server_name = self.extract_server_name_from_url(original_url)
        
        # Process the request
        response = None
        success = False
        error_code = None
        
        try:
            response = await call_next(request)
            
            # Determine success based on response status
            success = response.status_code == 200
            
            if success:
                # Extract user info from response headers if available
                username = response.headers.get("X-Username", "")
                user_hash = self.hash_username(username)
                auth_method = response.headers.get("X-Auth-Method", "unknown")
            else:
                error_code = str(response.status_code)
            
        except Exception as e:
            # Handle exceptions during request processing
            success = False
            error_code = type(e).__name__
            logger.error(f"Error in auth request: {e}")
            # Re-raise the exception to maintain normal error handling
            raise
        
        finally:
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Emit metrics asynchronously (fire and forget)
            asyncio.create_task(
                self._emit_auth_metric(
                    success=success,
                    method=auth_method,
                    duration_ms=duration_ms,
                    server_name=server_name,
                    user_hash=user_hash,
                    error_code=error_code
                )
            )
        
        return response
    
    async def _emit_auth_metric(
        self,
        success: bool,
        method: str,
        duration_ms: float,
        server_name: str,
        user_hash: str,
        error_code: str = None
    ):
        """
        Emit authentication metric asynchronously.
        """
        try:
            await self.metrics_client.emit_auth_metric(
                success=success,
                method=method,
                duration_ms=duration_ms,
                server_name=server_name,
                user_hash=user_hash,
                error_code=error_code
            )
        except Exception as e:
            # Never let metrics collection fail the main request
            logger.debug(f"Failed to emit auth metric: {e}")


def add_auth_metrics_middleware(app, service_name: str = "auth-server"):
    """
    Convenience function to add auth metrics middleware to a FastAPI app.
    
    Args:
        app: FastAPI application instance
        service_name: Name of the service for metrics identification
    """
    app.add_middleware(AuthMetricsMiddleware, service_name=service_name)
    logger.info(f"Auth metrics middleware added for service: {service_name}")