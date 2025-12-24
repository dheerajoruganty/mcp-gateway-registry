import logging
import asyncio
from typing import Dict, List, Any, Optional

from ..repositories.factory import get_server_repository
from ..repositories.interfaces import ServerRepositoryBase

logger = logging.getLogger(__name__)


class ServerService:
    """Service for managing server registration and state."""
    
    def __init__(self):
        self._repo: ServerRepositoryBase = get_server_repository()
        # Keep these for backward compatibility with code that accesses them directly
        self.registered_servers: Dict[str, Dict[str, Any]] = {}
        self.service_state: Dict[str, bool] = {}
        
    async def load_servers_and_state(self):
        """Load server definitions and persisted state from disk."""
        # Delegate to repository
        await self._repo.load_all()
        
        # Sync to backward-compatible attributes
        self.registered_servers = await self._repo.list_all()
        self.service_state = {}
        for path in self.registered_servers.keys():
            self.service_state[path] = await self._repo.get_state(path)
        

        
    async def register_server(self, server_info: Dict[str, Any]) -> bool:
        """Register a new server."""
        result = await self._repo.create(server_info)
        
        if result:
            # Sync to backward-compatible attributes
            path = server_info["path"]
            self.registered_servers[path] = server_info
            self.service_state[path] = False
        
        return result
        
    async def update_server(self, path: str, server_info: Dict[str, Any]) -> bool:
        """Update an existing server."""
        result = await self._repo.update(path, server_info)
        
        if result:
            # Sync to backward-compatible attributes
            self.registered_servers[path] = server_info
            
            # Update FAISS index
            try:
                from ..search.service import faiss_service
                try:
                    asyncio.get_running_loop()
                    is_enabled = self.service_state.get(path, False)
                    asyncio.create_task(faiss_service.add_or_update_service(path, server_info, is_enabled))
                except RuntimeError:
                    logger.debug(f"Skipping FAISS update for {path} - no async context available")
            except Exception as e:
                logger.error(f"Failed to update FAISS index after server update: {e}")
            
            # Regenerate nginx config if enabled
            if self.service_state.get(path, False):
                try:
                    from ..core.nginx_service import nginx_service
                    enabled_servers = {
                        service_path: self.get_server_info(service_path)
                        for service_path in self.get_enabled_services()
                    }
                    nginx_service.generate_config(enabled_servers)
                    nginx_service.reload_nginx()
                    logger.info(f"Regenerated nginx config due to server update: {path}")
                except Exception as e:
                    logger.error(f"Failed to regenerate nginx configuration after server update: {e}")
        
        return result
        
    async def toggle_service(self, path: str, enabled: bool) -> bool:
        """Toggle service enabled/disabled state."""
        result = await self._repo.set_state(path, enabled)
        
        if result:
            # Sync to backward-compatible attributes
            self.service_state[path] = enabled
            
            # Trigger nginx config regeneration
            try:
                from ..core.nginx_service import nginx_service
                enabled_servers = {
                    service_path: self.get_server_info(service_path) 
                    for service_path in self.get_enabled_services()
                }
                nginx_service.generate_config(enabled_servers)
                nginx_service.reload_nginx()
            except Exception as e:
                logger.error(f"Failed to update nginx configuration after toggle: {e}")
        
        return result
        
    def get_server_info(self, path: str) -> Optional[Dict[str, Any]]:
        """Get server information by path."""
        return self.registered_servers.get(path)
        
    async def get_all_servers(self, include_federated: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        Get all registered servers.

        Args:
            include_federated: If True, include servers from federated registries

        Returns:
            Dict of all servers (local and federated if requested)
        """
        all_servers = self.registered_servers.copy()

        # Add federated servers if requested
        if include_federated:
            try:
                from .federation_service import get_federation_service
                federation_service = get_federation_service()
                federated_servers = await federation_service.get_federated_servers()

                # Add federated servers with their paths as keys
                for fed_server in federated_servers:
                    path = fed_server.get("path")
                    if path and path not in all_servers:
                        all_servers[path] = fed_server

                logger.debug(f"Included {len(federated_servers)} federated servers")
            except Exception as e:
                logger.error(f"Failed to get federated servers: {e}")

        return all_servers
        
    def get_filtered_servers(self, accessible_servers: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get servers filtered by user's accessible servers list.
        
        Args:
            accessible_servers: List of server names the user can access
            
        Returns:
            Dict of servers the user is authorized to see
        """
        if not accessible_servers:
            logger.debug("User has no accessible servers, returning empty dict")
            return {}
        
        logger.info(f"DEBUG: get_filtered_servers called with accessible_servers: {accessible_servers}")
        logger.info(f"DEBUG: Available registered servers paths: {list(self.registered_servers.keys())}")
        
        filtered_servers = {}
        for path, server_info in self.registered_servers.items():
            server_name = server_info.get("server_name", "")
            # Extract technical name from path (remove leading and trailing slashes)
            technical_name = path.strip('/')
            logger.info(f"DEBUG: Checking server path='{path}', server_name='{server_name}', technical_name='{technical_name}' against accessible_servers")
            
            # Check if user has access to this server using technical name
            if technical_name in accessible_servers:
                filtered_servers[path] = server_info
                logger.info(f"DEBUG: ✓ User has access to server: {technical_name} ({server_name})")
            else:
                logger.info(f"DEBUG: ✗ User does not have access to server: {technical_name} ({server_name})")
        
        logger.info(f"Filtered {len(filtered_servers)} servers from {len(self.registered_servers)} total servers")
        return filtered_servers

    async def get_all_servers_with_permissions(
        self,
        accessible_servers: Optional[List[str]] = None,
        include_federated: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get servers with optional filtering based on user permissions.

        Args:
            accessible_servers: Optional list of server names the user can access.
                               If None, returns all servers (admin access).
            include_federated: If True, include servers from federated registries

        Returns:
            Dict of servers the user is authorized to see
        """
        if accessible_servers is None:
            # Admin access - return all servers (including federated)
            logger.debug("Admin access - returning all servers")
            return await self.get_all_servers(include_federated=include_federated)
        else:
            # Filtered access - return only accessible servers
            logger.debug(f"Filtered access - returning servers accessible to user: {accessible_servers}")
            # Note: Federated servers are read-only, so we include them in filtered results too
            all_servers = await self.get_all_servers(include_federated=include_federated)

            # Filter based on accessible_servers
            filtered_servers = {}
            for path, server_info in all_servers.items():
                server_name = server_info.get("server_name", "")
                technical_name = path.strip('/')

                # Check if user has access to this server using technical name
                if technical_name in accessible_servers:
                    filtered_servers[path] = server_info

            return filtered_servers

    def user_can_access_server_path(self, path: str, accessible_servers: List[str]) -> bool:
        """
        Check if user can access a specific server by path.
        
        Args:
            path: Server path to check
            accessible_servers: List of server names the user can access
            
        Returns:
            True if user can access the server, False otherwise
        """
        server_info = self.get_server_info(path)
        if not server_info:
            return False

        # Extract technical name from path (remove leading and trailing slashes)
        technical_name = path.strip('/')
        return technical_name in accessible_servers

    async def is_service_enabled(self, path: str) -> bool:
        """Check if a service is enabled."""
        return await self._repo.get_state(path)
        
    def get_enabled_services(self) -> List[str]:
        """Get list of enabled service paths."""
        return [path for path, enabled in self.service_state.items() if enabled]

    async def reload_state_from_disk(self):
        """Reload service state from disk."""
        logger.info("Reloading service state from disk...")
        
        previous_enabled_services = set(self.get_enabled_services())
        
        # Reload from repository
        await self._repo.load_all()
        
        # Sync to backward-compatible attributes
        self.registered_servers = await self._repo.list_all()
        self.service_state = {}
        for path in self.registered_servers.keys():
            self.service_state[path] = await self._repo.get_state(path)
        
        current_enabled_services = set(self.get_enabled_services())
        
        if previous_enabled_services != current_enabled_services:
            logger.info(f"Service state changes detected: {len(previous_enabled_services)} -> {len(current_enabled_services)} enabled services")
            
            try:
                from ..core.nginx_service import nginx_service
                enabled_servers = {
                    service_path: self.get_server_info(service_path) 
                    for service_path in self.get_enabled_services()
                }
                nginx_service.generate_config(enabled_servers)
                nginx_service.reload_nginx()
                logger.info("Regenerated nginx config due to state reload")
            except Exception as e:
                logger.error(f"Failed to regenerate nginx configuration after state reload: {e}")
        else:
            logger.info("No service state changes detected after reload")

    def update_rating(
        self,
        path: str,
        username: str,
        rating: int,
    ) -> float:
        """
        Log a user rating for a server. If the user has already rated, update their rating.

        Args:
            path: server path
            username: The user who submitted rating
            rating: integer between 1-5

        Return:
            Updated average rating

        Raises:
            ValueError: If server not found or invalid rating
        """
        from . import rating_service

        if path not in self.registered_servers:
            logger.error(f"Cannot update server at path '{path}': not found")
            raise ValueError(f"Server not found at path: {path}")

        # Validate rating using shared service
        rating_service.validate_rating(rating)

        server_info = self.registered_servers[path]

        # Ensure rating_details is a list
        if "rating_details" not in server_info or server_info["rating_details"] is None:
            server_info["rating_details"] = []

        # Update rating details using shared service
        updated_details, is_new_rating = rating_service.update_rating_details(
            server_info["rating_details"],
            username,
            rating
        )
        server_info["rating_details"] = updated_details

        # Calculate average rating using shared service
        server_info["num_stars"] = rating_service.calculate_average_rating(
            server_info["rating_details"]
        )

        # Save to file
        self.save_server_to_file(server_info)

        logger.info(
            f"Updated rating for server {path}: user {username} rated {rating}, "
            f"new average: {server_info['num_stars']:.2f}"
        )
        return server_info["num_stars"]

    async def remove_server(self, path: str) -> bool:
        """Remove a server from the registry and file system."""
        result = await self._repo.delete(path)
        
        if result:
            # Sync to backward-compatible attributes
            if path in self.registered_servers:
                del self.registered_servers[path]
            if path in self.service_state:
                del self.service_state[path]
        
        return result


# Global service instance
server_service = ServerService() 