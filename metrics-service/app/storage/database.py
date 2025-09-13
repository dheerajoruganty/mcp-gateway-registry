import aiosqlite
import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
from ..config import settings

logger = logging.getLogger(__name__)


async def wait_for_database(max_retries: int = 10, delay: float = 2.0):
    """Wait for SQLite database container to be ready."""
    db_path = settings.SQLITE_DB_PATH
    
    for attempt in range(max_retries):
        try:
            # Ensure directory exists first
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Try to connect to database
            async with aiosqlite.connect(db_path) as db:
                await db.execute("SELECT 1")
                logger.info(f"Database connection successful on attempt {attempt + 1}")
                return
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
            else:
                raise Exception(f"Failed to connect to database after {max_retries} attempts")


async def init_database():
    """Initialize database using migrations."""
    db_path = settings.SQLITE_DB_PATH
    
    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Import here to avoid circular imports
    from .migrations import migration_manager
    
    # Apply all pending migrations
    logger.info("Applying database migrations...")
    success = await migration_manager.migrate_up()
    
    if success:
        logger.info("Database migrations completed successfully")
    else:
        raise Exception("Database migration failed")
    


class MetricsStorage:
    """SQLite storage handler for containerized database."""
    
    def __init__(self):
        self.db_path = settings.SQLITE_DB_PATH
    
    async def store_metrics_batch(self, metrics_batch: List[Dict[str, Any]]):
        """Store a batch of metrics in the containerized database."""
        if not metrics_batch:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            try:
                for metric_data in metrics_batch:
                    metric = metric_data['metric']
                    request = metric_data['request']
                    request_id = metric_data['request_id']
                    
                    # Store in main metrics table
                    await db.execute("""
                        INSERT INTO metrics (
                            request_id, service, service_version, instance_id,
                            metric_type, timestamp, value, duration_ms,
                            dimensions, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        request_id,
                        request.service,
                        request.version,
                        request.instance_id,
                        metric.type.value,
                        metric.timestamp.isoformat(),
                        metric.value,
                        metric.duration_ms,
                        json.dumps(metric.dimensions),
                        json.dumps(metric.metadata)
                    ))
                    
                    # Store in specialized table based on type
                    await self._store_specialized_metric(db, metric, request, request_id)
                
                await db.commit()
                logger.debug(f"Stored batch of {len(metrics_batch)} metrics to container DB")
                
            except Exception as e:
                await db.rollback()
                logger.error(f"Failed to store metrics batch: {e}")
                raise
    
    async def _store_specialized_metric(self, db, metric, request, request_id):
        """Store metric in specialized table based on type."""
        if metric.type.value == "auth_request":
            await db.execute("""
                INSERT INTO auth_metrics (
                    request_id, timestamp, service, duration_ms,
                    success, method, server, user_hash, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                metric.timestamp.isoformat(),
                request.service,
                metric.duration_ms,
                metric.dimensions.get('success'),
                metric.dimensions.get('method'),
                metric.dimensions.get('server'),
                metric.dimensions.get('user_hash'),
                metric.metadata.get('error_code')
            ))
        
        elif metric.type.value == "tool_discovery":
            await db.execute("""
                INSERT INTO discovery_metrics (
                    request_id, timestamp, service, duration_ms,
                    query, results_count, top_k_services, top_n_tools,
                    embedding_time_ms, faiss_search_time_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                metric.timestamp.isoformat(),
                request.service,
                metric.duration_ms,
                metric.dimensions.get('query'),
                metric.dimensions.get('results_count'),
                metric.dimensions.get('top_k_services'),
                metric.dimensions.get('top_n_tools'),
                metric.metadata.get('embedding_time_ms'),
                metric.metadata.get('faiss_search_time_ms')
            ))
        
        elif metric.type.value == "tool_execution":
            await db.execute("""
                INSERT INTO tool_metrics (
                    request_id, timestamp, service, duration_ms,
                    tool_name, server_path, server_name, success,
                    error_code, input_size_bytes, output_size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request_id,
                metric.timestamp.isoformat(),
                request.service,
                metric.duration_ms,
                metric.dimensions.get('tool_name'),
                metric.dimensions.get('server_path'),
                metric.dimensions.get('server_name'),
                metric.dimensions.get('success'),
                metric.metadata.get('error_code'),
                metric.metadata.get('input_size_bytes'),
                metric.metadata.get('output_size_bytes')
            ))

    async def get_api_key(self, key_hash: str) -> Dict[str, Any] | None:
        """Get API key details from database."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT service_name, is_active, rate_limit, last_used_at
                FROM api_keys 
                WHERE key_hash = ?
            """, (key_hash,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'service_name': row[0],
                        'is_active': bool(row[1]),
                        'rate_limit': row[2],
                        'last_used_at': row[3]
                    }
                return None

    async def update_api_key_usage(self, key_hash: str):
        """Update last_used_at timestamp for API key."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE api_keys 
                SET last_used_at = datetime('now') 
                WHERE key_hash = ?
            """, (key_hash,))
            await db.commit()

    async def create_api_key(self, key_hash: str, service_name: str) -> bool:
        """Create a new API key in the database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO api_keys (key_hash, service_name, created_at, is_active)
                    VALUES (?, ?, datetime('now'), 1)
                """, (key_hash, service_name))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to create API key: {e}")
            return False