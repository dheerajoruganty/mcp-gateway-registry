from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
import logging
import asyncio
from .config import settings
from .api.routes import router as api_router
from .storage.database import init_database, wait_for_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting Metrics Collection Service...")
    
    # Wait for database container to be ready
    logger.info("Waiting for database container...")
    await wait_for_database()
    logger.info("Database container is ready")
    
    # Initialize database
    await init_database()
    logger.info("Database initialized")
    
    # Setup OpenTelemetry (optional, continue if it fails)
    try:
        from .otel.exporters import setup_otel
        setup_otel()
        logger.info("OpenTelemetry configured")
    except Exception as e:
        logger.warning(f"OpenTelemetry setup skipped: {e}")
    
    yield
    
    logger.info("Shutting down Metrics Collection Service")


app = FastAPI(
    title="MCP Metrics Collection Service",
    description="Centralized metrics collection for MCP Gateway Registry components",
    version="1.0.0",
    lifespan=lifespan
)

# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "metrics-collection"}


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "MCP Metrics Collection Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "metrics": "/metrics",
            "health": "/health",
            "flush": "/flush"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=settings.METRICS_SERVICE_HOST, 
        port=settings.METRICS_SERVICE_PORT
    )