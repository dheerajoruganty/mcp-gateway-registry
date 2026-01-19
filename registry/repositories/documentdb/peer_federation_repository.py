"""DocumentDB repository for peer federation configuration storage."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from ...schemas.peer_federation_schema import PeerRegistryConfig, PeerSyncStatus
from ..interfaces import PeerFederationRepositoryBase
from .client import get_collection_name, get_documentdb_client


logger = logging.getLogger(__name__)


class DocumentDBPeerFederationRepository(PeerFederationRepositoryBase):
    """DocumentDB implementation of peer federation repository."""

    def __init__(self):
        self._peers_collection: Optional[AsyncIOMotorCollection] = None
        self._sync_state_collection: Optional[AsyncIOMotorCollection] = None
        self._peers_collection_name = get_collection_name("mcp_peers")
        self._sync_state_collection_name = get_collection_name("mcp_peer_sync_state")
        logger.info(
            f"Initialized DocumentDB PeerFederationRepository with collections: "
            f"{self._peers_collection_name}, {self._sync_state_collection_name}"
        )

    async def _get_peers_collection(self) -> AsyncIOMotorCollection:
        """Get DocumentDB collection for peer configs."""
        if self._peers_collection is None:
            db = await get_documentdb_client()
            self._peers_collection = db[self._peers_collection_name]
        return self._peers_collection

    async def _get_sync_state_collection(self) -> AsyncIOMotorCollection:
        """Get DocumentDB collection for sync states."""
        if self._sync_state_collection is None:
            db = await get_documentdb_client()
            self._sync_state_collection = db[self._sync_state_collection_name]
        return self._sync_state_collection

    async def get_peer(
        self,
        peer_id: str,
    ) -> Optional[PeerRegistryConfig]:
        """Get peer configuration by ID."""
        try:
            collection = await self._get_peers_collection()

            peer_doc = await collection.find_one({"_id": peer_id})

            if not peer_doc:
                logger.debug(f"Peer config not found: {peer_id}")
                return None

            # Remove MongoDB internal fields
            peer_doc.pop("_id", None)
            peer_doc["peer_id"] = peer_id

            peer = PeerRegistryConfig(**peer_doc)
            logger.debug(f"Retrieved peer config: {peer_id}")
            return peer

        except Exception as e:
            logger.error(f"Failed to get peer config {peer_id}: {e}", exc_info=True)
            return None

    async def list_peers(
        self,
        enabled: Optional[bool] = None,
    ) -> List[PeerRegistryConfig]:
        """List all peer configurations."""
        try:
            collection = await self._get_peers_collection()

            # Build query filter
            query = {}
            if enabled is not None:
                query["enabled"] = enabled

            cursor = collection.find(query)

            peers = []
            async for doc in cursor:
                try:
                    peer_id = doc.pop("_id", None)
                    if peer_id:
                        doc["peer_id"] = peer_id
                    peer = PeerRegistryConfig(**doc)
                    peers.append(peer)
                except Exception as e:
                    logger.error(f"Failed to parse peer doc: {e}")
                    continue

            logger.info(f"Listed {len(peers)} peer configs from DocumentDB")
            return peers

        except Exception as e:
            logger.error(f"Failed to list peer configs: {e}", exc_info=True)
            return []

    async def save_peer(
        self,
        peer: PeerRegistryConfig,
    ) -> PeerRegistryConfig:
        """Save or update peer configuration."""
        try:
            collection = await self._get_peers_collection()

            peer_id = peer.peer_id

            # Check if exists
            existing = await collection.find_one({"_id": peer_id})

            # Prepare document
            doc = peer.model_dump(mode="json")
            doc.pop("peer_id", None)  # Don't store peer_id in doc, use _id

            now = datetime.now(timezone.utc).isoformat()
            if existing:
                doc["created_at"] = existing.get("created_at", now)
                doc["updated_at"] = now
            else:
                doc["created_at"] = now
                doc["updated_at"] = now

            doc["_id"] = peer_id

            await collection.replace_one(
                {"_id": peer_id},
                doc,
                upsert=True
            )

            logger.info(f"Saved peer config: {peer_id}")
            return peer

        except Exception as e:
            logger.error(f"Failed to save peer config {peer.peer_id}: {e}", exc_info=True)
            raise

    async def delete_peer(
        self,
        peer_id: str,
    ) -> bool:
        """Delete peer configuration."""
        try:
            collection = await self._get_peers_collection()

            result = await collection.delete_one({"_id": peer_id})

            if result.deleted_count == 0:
                logger.warning(f"Peer config not found for deletion: {peer_id}")
                return False

            logger.info(f"Deleted peer config: {peer_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete peer config {peer_id}: {e}", exc_info=True)
            return False

    async def get_sync_state(
        self,
        peer_id: str,
    ) -> Optional[PeerSyncStatus]:
        """Get sync state for a peer."""
        try:
            collection = await self._get_sync_state_collection()

            state_doc = await collection.find_one({"_id": peer_id})

            if not state_doc:
                logger.debug(f"Sync state not found: {peer_id}")
                return None

            # Remove MongoDB internal fields
            state_doc.pop("_id", None)
            state_doc["peer_id"] = peer_id

            state = PeerSyncStatus(**state_doc)
            logger.debug(f"Retrieved sync state: {peer_id}")
            return state

        except Exception as e:
            logger.error(f"Failed to get sync state {peer_id}: {e}", exc_info=True)
            return None

    async def save_sync_state(
        self,
        peer_id: str,
        state: PeerSyncStatus,
    ) -> bool:
        """Save sync state for a peer."""
        try:
            collection = await self._get_sync_state_collection()

            # Prepare document
            doc = state.model_dump(mode="json")
            doc.pop("peer_id", None)  # Don't store peer_id in doc, use _id
            doc["_id"] = peer_id

            await collection.replace_one(
                {"_id": peer_id},
                doc,
                upsert=True
            )

            logger.debug(f"Saved sync state: {peer_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save sync state {peer_id}: {e}", exc_info=True)
            return False

    async def delete_sync_state(
        self,
        peer_id: str,
    ) -> bool:
        """Delete sync state for a peer."""
        try:
            collection = await self._get_sync_state_collection()

            result = await collection.delete_one({"_id": peer_id})

            if result.deleted_count == 0:
                logger.debug(f"Sync state not found for deletion: {peer_id}")
                return False

            logger.info(f"Deleted sync state: {peer_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete sync state {peer_id}: {e}", exc_info=True)
            return False

    async def list_all_sync_states(self) -> Dict[str, PeerSyncStatus]:
        """List all sync states."""
        try:
            collection = await self._get_sync_state_collection()

            cursor = collection.find({})

            states = {}
            async for doc in cursor:
                try:
                    peer_id = doc.pop("_id", None)
                    if peer_id:
                        doc["peer_id"] = peer_id
                        state = PeerSyncStatus(**doc)
                        states[peer_id] = state
                except Exception as e:
                    logger.error(f"Failed to parse sync state doc: {e}")
                    continue

            logger.info(f"Listed {len(states)} sync states from DocumentDB")
            return states

        except Exception as e:
            logger.error(f"Failed to list sync states: {e}", exc_info=True)
            return {}

    async def load_all(self) -> None:
        """
        Load/reload all peer configurations and sync states.

        For DocumentDB, this is a no-op as data is fetched on-demand.
        Exists for interface compatibility.
        """
        logger.info("DocumentDB peer federation repository ready (data loaded on demand)")
