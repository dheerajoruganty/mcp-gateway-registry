from fastapi import APIRouter, HTTPException, Depends, Request, Response
from typing import List
import uuid
import logging
from ..core.models import MetricRequest, MetricResponse, ErrorResponse
from ..core.processor import MetricsProcessor
from ..api.auth import verify_api_key, get_rate_limit_status
from ..utils.helpers import generate_request_id

router = APIRouter()
logger = logging.getLogger(__name__)
processor = MetricsProcessor()


@router.post("/metrics", response_model=MetricResponse)
async def collect_metrics(
    metric_request: MetricRequest,
    request: Request,
    response: Response,
    api_key: str = Depends(verify_api_key)
):
    """Collect metrics from MCP components."""
    request_id = generate_request_id()
    
    try:
        # Add rate limit headers
        if hasattr(request.state, 'rate_limit_remaining') and hasattr(request.state, 'rate_limit_limit'):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
        
        # Process metrics
        result = await processor.process_metrics(metric_request, request_id, api_key)
        
        logger.info(f"Processed {result.accepted} metrics from {metric_request.service} (request: {request_id})")
        
        return MetricResponse(
            status="success",
            accepted=result.accepted,
            rejected=result.rejected,
            errors=result.errors,
            request_id=request_id
        )
        
    except Exception as e:
        logger.error(f"Error processing metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/flush")
async def flush_metrics(
    request: Request, 
    response: Response,
    api_key: str = Depends(verify_api_key)
):
    """Force flush buffered metrics to storage."""
    try:
        # Add rate limit headers
        if hasattr(request.state, 'rate_limit_remaining') and hasattr(request.state, 'rate_limit_limit'):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
        
        await processor.force_flush()
        return {"status": "success", "message": "Metrics flushed to storage"}
    except Exception as e:
        logger.error(f"Error flushing metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to flush metrics: {str(e)}"
        )


@router.get("/rate-limit")
async def get_rate_limit(request: Request):
    """Get current rate limit status for the API key."""
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required in X-API-Key header"
        )
    
    try:
        status = await get_rate_limit_status(api_key)
        return status
    except Exception as e:
        logger.error(f"Error getting rate limit status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get rate limit status: {str(e)}"
        )