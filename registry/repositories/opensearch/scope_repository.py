"""OpenSearch-based repository for authorization scopes storage."""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from opensearchpy import AsyncOpenSearch, NotFoundError

from ...core.config import settings
from ..interfaces import ScopeRepositoryBase
from .client import get_opensearch_client, get_index_name

logger = logging.getLogger(__name__)


class OpenSearchScopeRepository(ScopeRepositoryBase):
    """OpenSearch implementation of scope repository."""

    def __init__(self):
        self._scopes_data: Dict[str, Any] = {}
        self._client: Optional[AsyncOpenSearch] = None
        self._index_name = get_index_name(settings.opensearch_index_scopes)

    async def _get_client(self) -> AsyncOpenSearch:
        """Get OpenSearch client."""
        if self._client is None:
            self._client = await get_opensearch_client()
        return self._client


    def _is_aoss(self) -> bool:
        """Check if using AWS OpenSearch Serverless (which doesn't support custom IDs)."""
        return settings.opensearch_auth_type == "aws_iam"


    def _create_doc_id(
        self,
        scope_type: str,
        name: str,
    ) -> str:
        """Create document ID from scope type and name."""
        return f"{scope_type}:{name}".replace("/", "_")

    async def load_all(self) -> None:
        """Load all scopes from OpenSearch."""
        logger.info(f"Loading scopes from OpenSearch index: {self._index_name}")
        client = await self._get_client()

        try:
            response = await client.search(
                index=self._index_name,
                body={
                    "query": {"match_all": {}},
                    "size": 10000
                }
            )

            self._scopes_data = {
                "UI-Scopes": {},
                "group_mappings": {},
            }

            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                scope_type = source.get("scope_type")
                scope_name = source.get("scope_name")
                group_name = source.get("group_name")

                if scope_type == "UI-Scopes" and group_name:
                    self._scopes_data["UI-Scopes"][group_name] = source.get("ui_permissions", {})
                elif scope_type == "group_mappings" and group_name:
                    self._scopes_data["group_mappings"][group_name] = source.get("group_mappings", [])
                elif scope_type == "server_scopes" and scope_name:
                    self._scopes_data[scope_name] = source.get("server_access", [])

            logger.info(f"Loaded scopes from OpenSearch")

        except NotFoundError:
            logger.warning(f"Index {self._index_name} not found, starting with empty scopes")
            self._scopes_data = {"UI-Scopes": {}, "group_mappings": {}}
        except Exception as e:
            logger.error(f"Error loading scopes from OpenSearch: {e}", exc_info=True)
            self._scopes_data = {"UI-Scopes": {}, "group_mappings": {}}

    async def get_ui_scopes(
        self,
        group_name: str,
    ) -> Dict[str, Any]:
        """Get UI scopes for a Keycloak group."""
        ui_scopes = self._scopes_data.get("UI-Scopes", {})
        return ui_scopes.get(group_name, {})

    async def get_group_mappings(
        self,
        keycloak_group: str,
    ) -> List[str]:
        """Get scope names mapped to a Keycloak group."""
        group_mappings = self._scopes_data.get("group_mappings", {})
        return group_mappings.get(keycloak_group, [])

    async def get_server_scopes(
        self,
        scope_name: str,
    ) -> List[Dict[str, Any]]:
        """Get server access rules for a scope."""
        return self._scopes_data.get(scope_name, [])

    async def add_server_scope(
        self,
        server_path: str,
        scope_name: str,
        methods: List[str],
        tools: Optional[List[str]] = None,
    ) -> bool:
        """Add scope for a server."""
        try:
            client = await self._get_client()
            server_name = server_path.lstrip('/')

            server_entry = {
                "server": server_name,
                "methods": methods,
                "tools": tools
            }

            existing_scopes = self._scopes_data.get(scope_name, [])

            existing = [s for s in existing_scopes if s.get('server') == server_name]

            if existing:
                idx = existing_scopes.index(existing[0])
                existing_scopes[idx] = server_entry
            else:
                existing_scopes.append(server_entry)

            doc_id = self._create_doc_id("server_scopes", scope_name)

            document = {
                "scope_type": "server_scopes",
                "scope_name": scope_name,
                "server_access": existing_scopes,
                "updated_at": datetime.utcnow().isoformat()
            }

            if self._is_aoss():
                # AOSS doesn't support custom IDs or refresh=true
                await client.index(
                    index=self._index_name,
                    body=document
                )
            else:
                await client.index(
                    index=self._index_name,
                    id=doc_id,
                    body=document,
                    refresh=True
                )

            self._scopes_data[scope_name] = existing_scopes

            logger.info(f"Added server {server_path} to scope {scope_name} in OpenSearch")
            return True

        except Exception as e:
            logger.error(f"Failed to add server scope in OpenSearch: {e}", exc_info=True)
            return False

    async def remove_server_scope(
        self,
        server_path: str,
        scope_name: str,
    ) -> bool:
        """Remove scope for a server."""
        try:
            client = await self._get_client()
            server_name = server_path.lstrip('/')

            existing_scopes = self._scopes_data.get(scope_name, [])

            original_length = len(existing_scopes)
            existing_scopes = [
                s for s in existing_scopes
                if s.get('server') != server_name
            ]

            if len(existing_scopes) < original_length:
                doc_id = self._create_doc_id("server_scopes", scope_name)

                if len(existing_scopes) == 0:
                    if self._is_aoss():
                        # AOSS doesn't support refresh=true
                        await client.delete(
                            index=self._index_name,
                            id=doc_id
                        )
                    else:
                        await client.delete(
                            index=self._index_name,
                            id=doc_id,
                            refresh=True
                        )
                    if scope_name in self._scopes_data:
                        del self._scopes_data[scope_name]
                else:
                    document = {
                        "scope_type": "server_scopes",
                        "scope_name": scope_name,
                        "server_access": existing_scopes,
                        "updated_at": datetime.utcnow().isoformat()
                    }

                    if self._is_aoss():
                        # AOSS doesn't support custom IDs or refresh=true
                        await client.index(
                            index=self._index_name,
                            body=document
                        )
                    else:
                        await client.index(
                            index=self._index_name,
                            id=doc_id,
                            body=document,
                            refresh=True
                        )
                    self._scopes_data[scope_name] = existing_scopes

                logger.info(f"Removed server {server_path} from scope {scope_name} in OpenSearch")
                return True
            else:
                logger.warning(f"Server {server_path} not found in scope {scope_name}")
                return False

        except Exception as e:
            logger.error(f"Failed to remove server scope in OpenSearch: {e}", exc_info=True)
            return False


    async def create_group(
        self,
        group_name: str,
        description: str = "",
    ) -> bool:
        """Create a new group in scopes with all required documents."""
        try:
            client = await self._get_client()

            if await self.group_exists(group_name):
                logger.warning(f"Group {group_name} already exists")
                return False

            current_time = datetime.utcnow().isoformat()

            # 1. Create server_scope document
            server_scope_id = self._create_doc_id("server_scope", group_name)
            server_scope_doc = {
                "scope_type": "server_scope",
                "scope_name": group_name,
                "server_access": [],
                "description": description,
                "created_at": current_time,
                "updated_at": current_time
            }

            await client.index(
                index=self._index_name,
                id=server_scope_id,
                body=server_scope_doc,
                refresh=True
            )

            # 2. Create group_mapping document (self-mapping)
            group_mapping_id = self._create_doc_id("group_mapping", group_name)
            group_mapping_doc = {
                "scope_type": "group_mapping",
                "group_name": group_name,
                "group_mappings": [group_name],
                "created_at": current_time,
                "updated_at": current_time
            }

            await client.index(
                index=self._index_name,
                id=group_mapping_id,
                body=group_mapping_doc,
                refresh=True
            )

            # 3. Create ui_scope document
            ui_scope_id = self._create_doc_id("ui_scope", group_name)
            ui_scope_doc = {
                "scope_type": "ui_scope",
                "scope_name": group_name,
                "ui_permissions": {
                    "list_service": []
                },
                "created_at": current_time,
                "updated_at": current_time
            }

            await client.index(
                index=self._index_name,
                id=ui_scope_id,
                body=ui_scope_doc,
                refresh=True
            )

            # Update in-memory cache
            self._scopes_data[group_name] = []
            if "group_mappings" not in self._scopes_data:
                self._scopes_data["group_mappings"] = {}
            self._scopes_data["group_mappings"][group_name] = [group_name]

            if "UI-Scopes" not in self._scopes_data:
                self._scopes_data["UI-Scopes"] = {}
            self._scopes_data["UI-Scopes"][group_name] = {"list_service": []}

            logger.info(f"Created group {group_name} in OpenSearch with server_scope, group_mapping, and ui_scope documents")
            return True

        except Exception as e:
            logger.error(f"Failed to create group in OpenSearch: {e}", exc_info=True)
            return False


    async def delete_group(
        self,
        group_name: str,
        remove_from_mappings: bool = True,
    ) -> bool:
        """Delete a group from scopes (all 3 document types)."""
        try:
            client = await self._get_client()
            deleted_any = False

            # 1. Delete server_scope document
            server_scope_id = self._create_doc_id("server_scope", group_name)
            try:
                await client.delete(
                    index=self._index_name,
                    id=server_scope_id,
                    refresh=True
                )
                deleted_any = True
                logger.info(f"Deleted server_scope document for {group_name}")
            except NotFoundError:
                logger.warning(f"server_scope document for {group_name} not found")

            # 2. Delete group_mapping document
            group_mapping_id = self._create_doc_id("group_mapping", group_name)
            try:
                await client.delete(
                    index=self._index_name,
                    id=group_mapping_id,
                    refresh=True
                )
                logger.info(f"Deleted group_mapping document for {group_name}")
            except NotFoundError:
                logger.warning(f"group_mapping document for {group_name} not found")

            # 3. Delete ui_scope document
            ui_scope_id = self._create_doc_id("ui_scope", group_name)
            try:
                await client.delete(
                    index=self._index_name,
                    id=ui_scope_id,
                    refresh=True
                )
                logger.info(f"Deleted ui_scope document for {group_name}")
            except NotFoundError:
                logger.warning(f"ui_scope document for {group_name} not found")

            if not deleted_any:
                logger.warning(f"Group {group_name} not found in OpenSearch")
                return False

            # Update in-memory cache
            if group_name in self._scopes_data:
                del self._scopes_data[group_name]

            if "group_mappings" in self._scopes_data and group_name in self._scopes_data["group_mappings"]:
                del self._scopes_data["group_mappings"][group_name]

            if "UI-Scopes" in self._scopes_data and group_name in self._scopes_data["UI-Scopes"]:
                del self._scopes_data["UI-Scopes"][group_name]

            # Remove from other group mappings if requested
            if remove_from_mappings:
                group_mappings = self._scopes_data.get("group_mappings", {})
                for mapping_group, scopes in list(group_mappings.items()):
                    if group_name in scopes:
                        await self.remove_group_mapping(mapping_group, group_name)

            logger.info(f"Deleted group {group_name} from OpenSearch (all documents)")
            return True

        except Exception as e:
            logger.error(f"Failed to delete group in OpenSearch: {e}", exc_info=True)
            return False


    async def import_group(
        self,
        group_name: str,
        description: str = "",
        server_access: list = None,
        group_mappings: list = None,
        ui_permissions: dict = None,
    ) -> bool:
        """
        Import a complete group definition with all 3 document types.

        This creates/updates all 3 OpenSearch documents with the provided data:
        - server_scope: Contains server_access array
        - group_mapping: Contains group_mappings array
        - ui_scope: Contains ui_permissions object

        Args:
            group_name: Name of the group
            description: Description of the group
            server_access: List of server access definitions (can be simple paths or complex objects)
            group_mappings: List of group names this group maps to
            ui_permissions: Dictionary of UI permissions
        """
        try:
            client = await self._get_client()
            current_time = datetime.utcnow().isoformat()

            # Set defaults
            if server_access is None:
                server_access = []
            if group_mappings is None:
                group_mappings = [group_name]  # Self-mapping by default
            if ui_permissions is None:
                ui_permissions = {"list_service": []}

            # 1. Create/update server_scope document
            server_scope_id = self._create_doc_id("server_scope", group_name)
            server_scope_doc = {
                "scope_type": "server_scope",
                "scope_name": group_name,
                "server_access": server_access,
                "description": description,
                "created_at": current_time,
                "updated_at": current_time
            }

            await client.index(
                index=self._index_name,
                id=server_scope_id,
                body=server_scope_doc,
                refresh=True
            )
            logger.info(f"Created/updated server_scope for {group_name}")

            # 2. Create/update group_mapping document
            group_mapping_id = self._create_doc_id("group_mapping", group_name)
            group_mapping_doc = {
                "scope_type": "group_mapping",
                "group_name": group_name,
                "group_mappings": group_mappings,
                "created_at": current_time,
                "updated_at": current_time
            }

            await client.index(
                index=self._index_name,
                id=group_mapping_id,
                body=group_mapping_doc,
                refresh=True
            )
            logger.info(f"Created/updated group_mapping for {group_name}")

            # 3. Create/update ui_scope document
            ui_scope_id = self._create_doc_id("ui_scope", group_name)
            ui_scope_doc = {
                "scope_type": "ui_scope",
                "scope_name": group_name,
                "ui_permissions": ui_permissions,
                "created_at": current_time,
                "updated_at": current_time
            }

            await client.index(
                index=self._index_name,
                id=ui_scope_id,
                body=ui_scope_doc,
                refresh=True
            )
            logger.info(f"Created/updated ui_scope for {group_name}")

            # Update in-memory cache
            self._scopes_data[group_name] = server_access

            if "group_mappings" not in self._scopes_data:
                self._scopes_data["group_mappings"] = {}
            self._scopes_data["group_mappings"][group_name] = group_mappings

            if "UI-Scopes" not in self._scopes_data:
                self._scopes_data["UI-Scopes"] = {}
            self._scopes_data["UI-Scopes"][group_name] = ui_permissions

            logger.info(f"Imported complete group definition for {group_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to import group {group_name}: {e}", exc_info=True)
            return False


    async def get_group(self, group_name: str) -> Dict[str, Any]:
        """Get full details of a specific group."""
        try:
            client = await self._get_client()

            # OpenSearch Serverless (aws_iam) doesn't support custom document IDs
            # Use search queries instead of direct ID lookups
            use_search = settings.opensearch_auth_type == "aws_iam"

            if use_search:
                # Search for server_scope document by scope_name
                server_scope_response = await client.search(
                    index=self._index_name,
                    body={
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"scope_type": "server_scope"}},
                                    {"term": {"scope_name": group_name}}
                                ]
                            }
                        },
                        "size": 1
                    }
                )

                hits = server_scope_response.get("hits", {}).get("hits", [])
                if not hits:
                    logger.warning(f"Server scope document not found for group {group_name}")
                    return None

                server_scope_source = hits[0]["_source"]
            else:
                # Use direct ID lookup for regular OpenSearch (faster)
                server_scope_id = self._create_doc_id("server_scope", group_name)
                try:
                    server_scope_doc = await client.get(
                        index=self._index_name,
                        id=server_scope_id
                    )
                    server_scope_source = server_scope_doc["_source"]
                except NotFoundError:
                    logger.warning(f"Server scope document not found for group {group_name}")
                    return None

            # Get group_mapping document
            if use_search:
                group_mapping_response = await client.search(
                    index=self._index_name,
                    body={
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"scope_type": "group_mapping"}},
                                    {"term": {"group_name": group_name}}
                                ]
                            }
                        },
                        "size": 1
                    }
                )

                mapping_hits = group_mapping_response.get("hits", {}).get("hits", [])
                if mapping_hits:
                    group_mapping_source = mapping_hits[0]["_source"]
                else:
                    logger.debug(f"Group mapping document not found for group {group_name}")
                    group_mapping_source = {"group_mappings": [group_name]}
            else:
                group_mapping_id = self._create_doc_id("group_mapping", group_name)
                try:
                    group_mapping_doc = await client.get(
                        index=self._index_name,
                        id=group_mapping_id
                    )
                    group_mapping_source = group_mapping_doc["_source"]
                except NotFoundError:
                    logger.debug(f"Group mapping document not found for group {group_name}")
                    group_mapping_source = {"group_mappings": [group_name]}

            # Get ui_scope document
            if use_search:
                ui_scope_response = await client.search(
                    index=self._index_name,
                    body={
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"scope_type": "ui_scope"}},
                                    {"term": {"scope_name": group_name}}
                                ]
                            }
                        },
                        "size": 1
                    }
                )

                ui_hits = ui_scope_response.get("hits", {}).get("hits", [])
                if ui_hits:
                    ui_scope_source = ui_hits[0]["_source"]
                else:
                    logger.debug(f"UI scope document not found for group {group_name}")
                    ui_scope_source = {"ui_permissions": {}}
            else:
                ui_scope_id = self._create_doc_id("ui_scope", group_name)
                try:
                    ui_scope_doc = await client.get(
                        index=self._index_name,
                        id=ui_scope_id
                    )
                    ui_scope_source = ui_scope_doc["_source"]
                except NotFoundError:
                    logger.debug(f"UI scope document not found for group {group_name}")
                    ui_scope_source = {"ui_permissions": {}}

            # Combine all three document types into a single response
            result = {
                "scope_name": group_name,
                "scope_type": server_scope_source.get("scope_type", "server_scope"),
                "description": server_scope_source.get("description", ""),
                "server_access": server_scope_source.get("server_access", []),
                "group_mappings": group_mapping_source.get("group_mappings", []),
                "ui_permissions": ui_scope_source.get("ui_permissions", {}),
                "created_at": server_scope_source.get("created_at", ""),
                "updated_at": server_scope_source.get("updated_at", "")
            }

            logger.info(f"Retrieved full group details for {group_name} from OpenSearch")
            return result

        except Exception as e:
            logger.error(f"Failed to get group {group_name} from OpenSearch: {e}", exc_info=True)
            return None


    async def list_groups(self) -> Dict[str, Any]:
        """List all groups with server counts."""
        try:
            client = await self._get_client()

            response = await client.search(
                index=self._index_name,
                body={
                    "query": {
                        "term": {"scope_type": "server_scope"}
                    },
                    "size": 10000
                }
            )

            groups = {}
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                scope_name = source.get("scope_name", "")
                server_access = source.get("server_access", [])

                groups[scope_name] = {
                    "server_count": len(server_access),
                    "servers": [s.get("server") for s in server_access],
                    "description": source.get("description", ""),
                    "created_at": source.get("created_at", ""),
                    "updated_at": source.get("updated_at", "")
                }

            logger.info(f"Listed {len(groups)} groups from OpenSearch")
            return groups

        except NotFoundError:
            logger.warning(f"Index {self._index_name} not found")
            return {}
        except Exception as e:
            logger.error(f"Failed to list groups from OpenSearch: {e}", exc_info=True)
            return {}


    async def group_exists(
        self,
        group_name: str,
    ) -> bool:
        """Check if a group exists."""
        try:
            client = await self._get_client()
            doc_id = self._create_doc_id("server_scope", group_name)

            exists = await client.exists(
                index=self._index_name,
                id=doc_id
            )

            return exists

        except Exception as e:
            logger.error(f"Failed to check group existence in OpenSearch: {e}", exc_info=True)
            return False


    async def add_server_to_ui_scopes(
        self,
        group_name: str,
        server_name: str,
    ) -> bool:
        """Add server to group's UI scopes list_service."""
        try:
            client = await self._get_client()
            doc_id = self._create_doc_id("ui_scope", group_name)

            ui_scopes = self._scopes_data.get("UI-Scopes", {})
            current_ui = ui_scopes.get(group_name, {})

            list_service = current_ui.get("list_service", [])

            if server_name not in list_service:
                list_service.append(server_name)
                current_ui["list_service"] = list_service

            document = {
                "scope_type": "ui_scope",
                "scope_name": group_name,
                "ui_permissions": current_ui,
                "updated_at": datetime.utcnow().isoformat()
            }

            await client.index(
                index=self._index_name,
                id=doc_id,
                body=document,
                refresh=True
            )

            if "UI-Scopes" not in self._scopes_data:
                self._scopes_data["UI-Scopes"] = {}
            self._scopes_data["UI-Scopes"][group_name] = current_ui

            logger.info(f"Added server {server_name} to UI scopes for group {group_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add server to UI scopes: {e}", exc_info=True)
            return False


    async def remove_server_from_ui_scopes(
        self,
        group_name: str,
        server_name: str,
    ) -> bool:
        """Remove server from group's UI scopes list_service."""
        try:
            client = await self._get_client()
            doc_id = self._create_doc_id("ui_scope", group_name)

            ui_scopes = self._scopes_data.get("UI-Scopes", {})
            current_ui = ui_scopes.get(group_name, {})

            list_service = current_ui.get("list_service", [])

            if server_name in list_service:
                list_service.remove(server_name)
                current_ui["list_service"] = list_service

                document = {
                    "scope_type": "ui_scope",
                    "scope_name": group_name,
                    "ui_permissions": current_ui,
                    "updated_at": datetime.utcnow().isoformat()
                }

                await client.index(
                    index=self._index_name,
                    id=doc_id,
                    body=document,
                    refresh=True
                )

                self._scopes_data["UI-Scopes"][group_name] = current_ui
                logger.info(f"Removed server {server_name} from UI scopes for group {group_name}")
                return True
            else:
                logger.warning(f"Server {server_name} not found in UI scopes for group {group_name}")
                return False

        except Exception as e:
            logger.error(f"Failed to remove server from UI scopes: {e}", exc_info=True)
            return False


    async def add_group_mapping(
        self,
        group_name: str,
        scope_name: str,
    ) -> bool:
        """Add a scope to group mappings."""
        try:
            client = await self._get_client()
            doc_id = self._create_doc_id("group_mapping", group_name)

            group_mappings = self._scopes_data.get("group_mappings", {})
            current_mappings = group_mappings.get(group_name, [])

            if scope_name not in current_mappings:
                current_mappings.append(scope_name)

            document = {
                "scope_type": "group_mapping",
                "group_name": group_name,
                "group_mappings": current_mappings,
                "updated_at": datetime.utcnow().isoformat()
            }

            await client.index(
                index=self._index_name,
                id=doc_id,
                body=document,
                refresh=True
            )

            if "group_mappings" not in self._scopes_data:
                self._scopes_data["group_mappings"] = {}
            self._scopes_data["group_mappings"][group_name] = current_mappings

            logger.info(f"Added scope {scope_name} to group mappings for {group_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add group mapping: {e}", exc_info=True)
            return False


    async def remove_group_mapping(
        self,
        group_name: str,
        scope_name: str,
    ) -> bool:
        """Remove a scope from group mappings."""
        try:
            client = await self._get_client()
            doc_id = self._create_doc_id("group_mapping", group_name)

            group_mappings = self._scopes_data.get("group_mappings", {})
            current_mappings = group_mappings.get(group_name, [])

            if scope_name in current_mappings:
                current_mappings.remove(scope_name)

                document = {
                    "scope_type": "group_mapping",
                    "group_name": group_name,
                    "group_mappings": current_mappings,
                    "updated_at": datetime.utcnow().isoformat()
                }

                await client.index(
                    index=self._index_name,
                    id=doc_id,
                    body=document,
                    refresh=True
                )

                self._scopes_data["group_mappings"][group_name] = current_mappings
                logger.info(f"Removed scope {scope_name} from group mappings for {group_name}")
                return True
            else:
                logger.warning(f"Scope {scope_name} not found in group mappings for {group_name}")
                return False

        except Exception as e:
            logger.error(f"Failed to remove group mapping: {e}", exc_info=True)
            return False


    async def get_all_group_mappings(self) -> Dict[str, List[str]]:
        """Get all group mappings."""
        try:
            client = await self._get_client()

            response = await client.search(
                index=self._index_name,
                body={
                    "query": {
                        "term": {"scope_type": "group_mapping"}
                    },
                    "size": 10000
                }
            )

            mappings = {}
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                group_name = source.get("group_name", "")
                group_mappings_list = source.get("group_mappings", [])

                if group_name:
                    mappings[group_name] = group_mappings_list

            logger.info(f"Retrieved {len(mappings)} group mappings from OpenSearch")
            return mappings

        except NotFoundError:
            logger.warning(f"Index {self._index_name} not found")
            return {}
        except Exception as e:
            logger.error(f"Failed to get all group mappings: {e}", exc_info=True)
            return {}


    async def add_server_to_multiple_scopes(
        self,
        server_path: str,
        scope_names: List[str],
        methods: List[str],
        tools: List[str],
    ) -> bool:
        """Add server to multiple scopes at once."""
        try:
            success = True
            for scope_name in scope_names:
                result = await self.add_server_scope(
                    server_path,
                    scope_name,
                    methods,
                    tools
                )
                if not result:
                    logger.error(f"Failed to add server {server_path} to scope {scope_name}")
                    success = False

            if success:
                logger.info(f"Added server {server_path} to {len(scope_names)} scopes")
            else:
                logger.warning(f"Partially added server {server_path} to scopes")

            return success

        except Exception as e:
            logger.error(f"Failed to add server to multiple scopes: {e}", exc_info=True)
            return False


    async def remove_server_from_all_scopes(
        self,
        server_path: str,
    ) -> bool:
        """Remove server from all scopes."""
        try:
            client = await self._get_client()
            server_name = server_path.lstrip('/')

            response = await client.search(
                index=self._index_name,
                body={
                    "query": {
                        "term": {"scope_type": "server_scope"}
                    },
                    "size": 10000
                }
            )

            scopes_to_update = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                scope_name = source.get("scope_name", "")
                server_access = source.get("server_access", [])

                for server_entry in server_access:
                    if server_entry.get("server") == server_name:
                        scopes_to_update.append(scope_name)
                        break

            success = True
            for scope_name in scopes_to_update:
                result = await self.remove_server_scope(server_path, scope_name)
                if not result:
                    logger.error(f"Failed to remove server {server_path} from scope {scope_name}")
                    success = False

            if success:
                logger.info(f"Removed server {server_path} from {len(scopes_to_update)} scopes")
            else:
                logger.warning(f"Partially removed server {server_path} from scopes")

            return success

        except NotFoundError:
            logger.warning(f"Index {self._index_name} not found")
            return True
        except Exception as e:
            logger.error(f"Failed to remove server from all scopes: {e}", exc_info=True)
            return False
