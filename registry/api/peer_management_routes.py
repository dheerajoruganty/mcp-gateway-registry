"""
Peer management API routes.

Provides REST endpoints for managing peer registry configurations
and triggering synchronization operations.
"""

import logging
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..auth.dependencies import enhanced_auth
from ..schemas.peer_federation_schema import (
    PeerRegistryConfig,
    PeerSyncStatus,
    SyncResult,
)
from ..services.peer_federation_service import get_peer_federation_service


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/v1/peers",
    tags=["peer-management"],
)


# --- CRUD Operations ---


@router.get("", response_model=List[PeerRegistryConfig])
async def list_peers(
    enabled: Optional[bool] = None,
    user_context: Dict = Depends(enhanced_auth),
) -> List[PeerRegistryConfig]:
    """
    List all peer registries with optional filtering by enabled status.

    Args:
        enabled: If True, return only enabled peers. If False, return only disabled peers.
                If None, return all peers.
        user_context: Authenticated user context

    Returns:
        List of peer registry configurations

    Example:
        GET /api/v1/peers
        GET /api/v1/peers?enabled=true
    """
    logger.info(
        f"User '{user_context.get('username')}' listing peers (enabled={enabled})"
    )

    service = get_peer_federation_service()
    peers = await service.list_peers(enabled=enabled)

    logger.info(f"Returning {len(peers)} peer configs")
    return peers


# NOTE: /topology must be defined BEFORE /{peer_id} to avoid route collision
@router.get("/topology")
async def get_federation_topology(
    user_context: Dict = Depends(enhanced_auth),
) -> Dict[str, Any]:
    """
    Get federation topology for visualization.

    Returns nodes and edges representing the federation mesh suitable for
    rendering with React Flow or similar libraries.

    Args:
        user_context: Authenticated user context

    Returns:
        Dictionary with 'nodes' and 'edges' lists for visualization

    Example:
        GET /api/v1/peers/topology
    """
    logger.info(
        f"User '{user_context.get('username')}' retrieving federation topology"
    )

    service = get_peer_federation_service()
    peers = await service.list_peers()

    # Layout constants
    center_x, center_y = 400, 300
    radius = 200

    # Build nodes list - always include "this registry"
    nodes = [
        {
            "id": "this-registry",
            "type": "registry",
            "position": {"x": center_x, "y": center_y},
            "data": {
                "label": "This Registry",
                "isLocal": True,
                "status": "healthy",
            },
        }
    ]

    edges = []

    # Add peer nodes in circular layout
    num_peers = len(peers)
    for i, peer in enumerate(peers):
        # Calculate position on circle
        if num_peers > 0:
            angle = (2 * math.pi * i) / num_peers
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
        else:
            x, y = center_x + radius, center_y

        # Get sync status for this peer
        sync_status = await service.get_sync_status(peer.peer_id)

        # Determine status
        if not peer.enabled:
            status_str = "disabled"
        elif sync_status and sync_status.is_healthy:
            status_str = "healthy"
        elif sync_status and not sync_status.is_healthy:
            status_str = "unhealthy"
        else:
            status_str = "unknown"

        # Build node data
        node_data = {
            "label": peer.name,
            "enabled": peer.enabled,
            "status": status_str,
            "endpoint": peer.endpoint,
            "serversCount": sync_status.total_servers_synced if sync_status else 0,
            "agentsCount": sync_status.total_agents_synced if sync_status else 0,
            "lastSync": (
                sync_status.last_successful_sync.isoformat()
                if sync_status and sync_status.last_successful_sync
                else None
            ),
        }

        nodes.append({
            "id": peer.peer_id,
            "type": "peer",
            "position": {"x": x, "y": y},
            "data": node_data,
        })

        # Create edge for enabled peers
        if peer.enabled:
            is_healthy = sync_status.is_healthy if sync_status else False
            edges.append({
                "id": f"edge-{peer.peer_id}",
                "source": peer.peer_id,
                "target": "this-registry",
                "animated": is_healthy,
                "data": {
                    "status": status_str,
                },
            })

    logger.info(f"Returning topology with {len(nodes)} nodes and {len(edges)} edges")

    return {
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/{peer_id}", response_model=PeerRegistryConfig)
async def get_peer(
    peer_id: str,
    user_context: Dict = Depends(enhanced_auth),
) -> PeerRegistryConfig:
    """
    Get a specific peer by ID.

    Args:
        peer_id: Peer identifier
        user_context: Authenticated user context

    Returns:
        Peer registry configuration

    Raises:
        HTTPException: 404 if peer not found

    Example:
        GET /api/v1/peers/central-registry
    """
    logger.info(f"User '{user_context.get('username')}' retrieving peer '{peer_id}'")

    service = get_peer_federation_service()

    try:
        peer = await service.get_peer(peer_id)
        return peer
    except ValueError as e:
        logger.error(f"Peer not found: {peer_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("", response_model=PeerRegistryConfig, status_code=status.HTTP_201_CREATED)
async def create_peer(
    config: PeerRegistryConfig,
    user_context: Dict = Depends(enhanced_auth),
) -> PeerRegistryConfig:
    """
    Create a new peer registry configuration.

    Args:
        config: Peer registry configuration to create
        user_context: Authenticated user context

    Returns:
        Created peer registry configuration

    Raises:
        HTTPException: 409 if peer_id already exists
        HTTPException: 400 if validation fails

    Example:
        POST /api/v1/peers
        {
            "peer_id": "central-registry",
            "name": "Central MCP Registry",
            "endpoint": "https://central.registry.company.com",
            "enabled": true,
            "sync_mode": "all",
            "sync_interval_minutes": 30
        }
    """
    logger.info(
        f"User '{user_context.get('username')}' creating peer '{config.peer_id}'"
    )

    service = get_peer_federation_service()

    try:
        created_peer = await service.add_peer(config)
        logger.info(f"Successfully created peer '{config.peer_id}'")
        return created_peer
    except ValueError as e:
        error_msg = str(e)
        if "already exists" in error_msg:
            logger.error(f"Peer ID already exists: {config.peer_id}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_msg,
            )
        else:
            logger.error(f"Invalid peer config: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )


@router.put("/{peer_id}", response_model=PeerRegistryConfig)
async def update_peer(
    peer_id: str,
    updates: Dict[str, Any] = Body(...),
    user_context: Dict = Depends(enhanced_auth),
) -> PeerRegistryConfig:
    """
    Update an existing peer configuration.

    Args:
        peer_id: Peer identifier
        updates: Dictionary of fields to update
        user_context: Authenticated user context

    Returns:
        Updated peer registry configuration

    Raises:
        HTTPException: 404 if peer not found
        HTTPException: 400 if validation fails

    Example:
        PUT /api/v1/peers/central-registry
        {
            "enabled": false,
            "sync_interval_minutes": 60
        }
    """
    logger.info(
        f"User '{user_context.get('username')}' updating peer '{peer_id}' "
        f"with updates: {updates}"
    )

    service = get_peer_federation_service()

    try:
        updated_peer = await service.update_peer(peer_id, updates)
        logger.info(f"Successfully updated peer '{peer_id}'")
        return updated_peer
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            logger.error(f"Peer not found: {peer_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        else:
            logger.error(f"Invalid peer update: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )


@router.delete("/{peer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_peer(
    peer_id: str,
    user_context: Dict = Depends(enhanced_auth),
):
    """
    Delete a peer registry configuration.

    Args:
        peer_id: Peer identifier
        user_context: Authenticated user context

    Raises:
        HTTPException: 404 if peer not found

    Example:
        DELETE /api/v1/peers/central-registry
    """
    logger.info(f"User '{user_context.get('username')}' deleting peer '{peer_id}'")

    service = get_peer_federation_service()

    try:
        await service.remove_peer(peer_id)
        logger.info(f"Successfully deleted peer '{peer_id}'")
        # Return None for 204 No Content
        return None
    except ValueError as e:
        logger.error(f"Failed to delete peer '{peer_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# --- Sync Operations ---
# NOTE: /sync must be defined BEFORE /{peer_id}/sync to avoid route collision


@router.post("/sync", response_model=Dict[str, SyncResult])
async def sync_all_peers(
    enabled_only: bool = Query(True, description="If True, only sync enabled peers"),
    user_context: Dict = Depends(enhanced_auth),
) -> Dict[str, SyncResult]:
    """
    Trigger synchronization for all (or enabled) peers.

    Args:
        enabled_only: If True, only sync enabled peers (default: True)
        user_context: Authenticated user context

    Returns:
        Dictionary mapping peer_id to SyncResult

    Example:
        POST /api/v1/peers/sync
        POST /api/v1/peers/sync?enabled_only=false
    """
    logger.info(
        f"User '{user_context.get('username')}' triggering sync for all peers "
        f"(enabled_only={enabled_only})"
    )

    service = get_peer_federation_service()

    results = await service.sync_all_peers(enabled_only=enabled_only)

    # Count successes and failures
    successful = sum(1 for r in results.values() if r.success)
    failed = len(results) - successful
    total_servers = sum(r.servers_synced for r in results.values())
    total_agents = sum(r.agents_synced for r in results.values())

    logger.info(
        f"Sync all completed: {successful} succeeded, {failed} failed. "
        f"Total: {total_servers} servers, {total_agents} agents"
    )

    return results


@router.post("/{peer_id}/sync", response_model=SyncResult)
async def sync_peer(
    peer_id: str,
    user_context: Dict = Depends(enhanced_auth),
) -> SyncResult:
    """
    Trigger synchronization for a specific peer.

    Args:
        peer_id: Peer identifier
        user_context: Authenticated user context

    Returns:
        Sync result with statistics

    Raises:
        HTTPException: 404 if peer not found
        HTTPException: 400 if peer is disabled

    Example:
        POST /api/v1/peers/central-registry/sync
    """
    logger.info(
        f"User '{user_context.get('username')}' triggering sync for peer '{peer_id}'"
    )

    service = get_peer_federation_service()

    try:
        result = await service.sync_peer(peer_id)
        logger.info(
            f"Sync completed for peer '{peer_id}': "
            f"success={result.success}, servers={result.servers_synced}, "
            f"agents={result.agents_synced}"
        )
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            logger.error(f"Peer not found: {peer_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        else:
            logger.error(f"Sync failed: {error_msg}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )


# --- Status Operations ---


@router.get("/{peer_id}/status", response_model=PeerSyncStatus)
async def get_peer_status(
    peer_id: str,
    user_context: Dict = Depends(enhanced_auth),
) -> PeerSyncStatus:
    """
    Get sync status for a specific peer.

    Args:
        peer_id: Peer identifier
        user_context: Authenticated user context

    Returns:
        Peer sync status with health and history

    Raises:
        HTTPException: 404 if peer not found

    Example:
        GET /api/v1/peers/central-registry/status
    """
    logger.info(
        f"User '{user_context.get('username')}' retrieving status for peer '{peer_id}'"
    )

    service = get_peer_federation_service()

    sync_status = await service.get_sync_status(peer_id)

    if not sync_status:
        logger.error(f"Sync status not found for peer: {peer_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sync status not found for peer: {peer_id}",
        )

    return sync_status


@router.post("/{peer_id}/enable", response_model=PeerRegistryConfig)
async def enable_peer(
    peer_id: str,
    user_context: Dict = Depends(enhanced_auth),
) -> PeerRegistryConfig:
    """
    Enable a peer registry.

    Args:
        peer_id: Peer identifier
        user_context: Authenticated user context

    Returns:
        Updated peer registry configuration

    Raises:
        HTTPException: 404 if peer not found

    Example:
        POST /api/v1/peers/central-registry/enable
    """
    logger.info(
        f"User '{user_context.get('username')}' enabling peer '{peer_id}'"
    )

    service = get_peer_federation_service()

    try:
        updated_peer = await service.update_peer(peer_id, {"enabled": True})
        logger.info(f"Successfully enabled peer '{peer_id}'")
        return updated_peer
    except ValueError as e:
        logger.error(f"Failed to enable peer '{peer_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/{peer_id}/disable", response_model=PeerRegistryConfig)
async def disable_peer(
    peer_id: str,
    user_context: Dict = Depends(enhanced_auth),
) -> PeerRegistryConfig:
    """
    Disable a peer registry.

    Args:
        peer_id: Peer identifier
        user_context: Authenticated user context

    Returns:
        Updated peer registry configuration

    Raises:
        HTTPException: 404 if peer not found

    Example:
        POST /api/v1/peers/central-registry/disable
    """
    logger.info(
        f"User '{user_context.get('username')}' disabling peer '{peer_id}'"
    )

    service = get_peer_federation_service()

    try:
        updated_peer = await service.update_peer(peer_id, {"enabled": False})
        logger.info(f"Successfully disabled peer '{peer_id}'")
        return updated_peer
    except ValueError as e:
        logger.error(f"Failed to disable peer '{peer_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
