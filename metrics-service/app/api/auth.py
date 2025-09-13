from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
from ..storage.database import MetricsStorage
from ..utils.helpers import hash_api_key

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def verify_api_key(request: Request) -> str:
    """Verify API key from X-API-Key header."""
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required in X-API-Key header"
        )
    
    # Hash the provided API key
    key_hash = hash_api_key(api_key)
    
    # Verify against database
    storage = MetricsStorage()
    key_info = await storage.get_api_key(key_hash)
    
    if not key_info:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    if not key_info['is_active']:
        raise HTTPException(
            status_code=401,
            detail="API key is inactive"
        )
    
    # Update last used timestamp
    await storage.update_api_key_usage(key_hash)
    
    logger.debug(f"API key verified for service: {key_info['service_name']}")
    return key_info['service_name']