from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List
import uuid
import logging
from ..core.models import MetricRequest, MetricResponse, ErrorResponse
from ..core.processor import MetricsProcessor
from ..api.auth import verify_api_key
from ..utils.helpers import generate_request_id

router = APIRouter()
logger = logging.getLogger(__name__)
processor = MetricsProcessor()


@router.post("/metrics", response_model=MetricResponse)
async def collect_metrics(
    request: MetricRequest,
    api_key: str = Depends(verify_api_key)
):
    """Collect metrics from MCP components."""
    request_id = generate_request_id()
    
    try:
        # Process metrics
        result = await processor.process_metrics(request, request_id, api_key)
        
        logger.info(f"Processed {result.accepted} metrics from {request.service} (request: {request_id})")
        
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
async def flush_metrics(api_key: str = Depends(verify_api_key)):
    """Force flush buffered metrics to storage."""
    try:
        await processor.force_flush()
        return {"status": "success", "message": "Metrics flushed to storage"}
    except Exception as e:
        logger.error(f"Error flushing metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to flush metrics: {str(e)}"
        )