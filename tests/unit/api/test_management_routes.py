"""
Unit tests for registry.api.management_routes module.

Tests IAM management endpoints for Keycloak user and group management.
"""

import logging
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from registry.api.management_routes import (
    router,
    _translate_keycloak_error,
    _require_admin,
)
from registry.auth.dependencies import nginx_proxied_auth
from registry.utils.keycloak_manager import KeycloakAdminError


logger = logging.getLogger(__name__)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def admin_user_context() -> dict[str, Any]:
    """Create admin user context."""
    return {
        "username": "admin",
        "is_admin": True,
        "groups": ["mcp-registry-admin"],
        "scopes": ["admin:all"],
        "auth_method": "session",
    }


@pytest.fixture
def regular_user_context() -> dict[str, Any]:
    """Create regular (non-admin) user context."""
    return {
        "username": "testuser",
        "is_admin": False,
        "groups": ["test-group"],
        "scopes": ["test-server/read"],
        "auth_method": "session",
    }


@pytest.fixture
def test_app_admin(admin_user_context):
    """Create test app with admin auth."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[nginx_proxied_auth] = lambda: admin_user_context

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def test_app_regular(regular_user_context):
    """Create test app with regular user auth."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[nginx_proxied_auth] = lambda: regular_user_context

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# =============================================================================
# TEST: Helper Functions
# =============================================================================


@pytest.mark.unit
class TestHelperFunctions:
    """Tests for helper functions."""

    def test_translate_keycloak_error_already_exists(self):
        """Test translation of 'already exists' errors."""
        error = KeycloakAdminError("User already exists")
        result = _translate_keycloak_error(error)

        assert result.status_code == 400
        assert "already exists" in result.detail

    def test_translate_keycloak_error_not_found(self):
        """Test translation of 'not found' errors."""
        error = KeycloakAdminError("User not found")
        result = _translate_keycloak_error(error)

        assert result.status_code == 400
        assert "not found" in result.detail

    def test_translate_keycloak_error_provided(self):
        """Test translation of 'provided' errors."""
        error = KeycloakAdminError("Invalid value provided")
        result = _translate_keycloak_error(error)

        assert result.status_code == 400

    def test_translate_keycloak_error_generic(self):
        """Test translation of generic errors."""
        error = KeycloakAdminError("Connection refused")
        result = _translate_keycloak_error(error)

        assert result.status_code == 502

    def test_require_admin_with_admin(self, admin_user_context):
        """Test _require_admin passes for admin users."""
        # Should not raise
        _require_admin(admin_user_context)

    def test_require_admin_without_admin(self, regular_user_context):
        """Test _require_admin raises for non-admin users."""
        with pytest.raises(HTTPException) as exc_info:
            _require_admin(regular_user_context)

        assert exc_info.value.status_code == 403
        assert "Administrator" in exc_info.value.detail


# =============================================================================
# TEST: List Users
# =============================================================================


@pytest.mark.unit
class TestListUsers:
    """Tests for the list users endpoint."""

    def test_list_users_success(self, test_app_admin):
        """Test successful user listing."""
        mock_users = [
            {
                "id": "user-1",
                "username": "user1",
                "email": "user1@test.com",
                "firstName": "First",
                "lastName": "Last",
                "enabled": True,
                "groups": ["group1"],
            }
        ]

        with patch("registry.api.management_routes.list_keycloak_users", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_users
            response = test_app_admin.get("/management/iam/users")

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] == 1

    def test_list_users_with_search(self, test_app_admin):
        """Test user listing with search parameter."""
        with patch("registry.api.management_routes.list_keycloak_users", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            response = test_app_admin.get("/management/iam/users?search=test")

        assert response.status_code == 200
        mock_list.assert_called_once_with(search="test", max_results=500)

    def test_list_users_forbidden_for_non_admin(self, test_app_regular):
        """Test non-admin cannot list users."""
        response = test_app_regular.get("/management/iam/users")

        assert response.status_code == 403

    def test_list_users_keycloak_error(self, test_app_admin):
        """Test handling of Keycloak errors."""
        with patch("registry.api.management_routes.list_keycloak_users", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = KeycloakAdminError("Connection failed")
            response = test_app_admin.get("/management/iam/users")

        assert response.status_code == 502


# =============================================================================
# TEST: Create M2M User
# =============================================================================


@pytest.mark.unit
class TestCreateM2MUser:
    """Tests for the create M2M user endpoint."""

    def test_create_m2m_user_success(self, test_app_admin):
        """Test successful M2M user creation."""
        mock_result = {
            "client_id": "test-service",
            "client_secret": "secret-123",
        }

        with patch("registry.api.management_routes.create_service_account_client", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_result
            response = test_app_admin.post(
                "/management/iam/users/m2m",
                json={"name": "test-service", "groups": ["group1"], "description": "Test"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["client_id"] == "test-service"

    def test_create_m2m_user_forbidden_for_non_admin(self, test_app_regular):
        """Test non-admin cannot create M2M users."""
        response = test_app_regular.post(
            "/management/iam/users/m2m",
            json={"name": "test-service", "groups": ["test-group"], "description": "Test"},
        )

        assert response.status_code == 403

    def test_create_m2m_user_keycloak_error(self, test_app_admin):
        """Test handling of Keycloak errors."""
        with patch("registry.api.management_routes.create_service_account_client", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = KeycloakAdminError("Already exists")
            response = test_app_admin.post(
                "/management/iam/users/m2m",
                json={"name": "test-service", "groups": ["test-group"], "description": "Test"},
            )

        assert response.status_code == 400


# =============================================================================
# TEST: Create Human User
# =============================================================================


@pytest.mark.unit
class TestCreateHumanUser:
    """Tests for the create human user endpoint."""

    def test_create_human_user_success(self, test_app_admin):
        """Test successful human user creation."""
        mock_result = {
            "id": "user-123",
            "username": "newuser",
            "email": "new@test.com",
            "firstName": "New",
            "lastName": "User",
            "enabled": True,
            "groups": ["group1"],
        }

        with patch("registry.api.management_routes.create_human_user_account", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_result
            response = test_app_admin.post(
                "/management/iam/users/human",
                json={
                    "username": "newuser",
                    "email": "new@test.com",
                    "firstname": "New",
                    "lastname": "User",
                    "groups": ["group1"],
                    "password": "password123",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newuser"

    def test_create_human_user_forbidden_for_non_admin(self, test_app_regular):
        """Test non-admin cannot create human users."""
        response = test_app_regular.post(
            "/management/iam/users/human",
            json={
                "username": "newuser",
                "email": "new@test.com",
                "firstname": "New",
                "lastname": "User",
                "groups": ["test-group"],
            },
        )

        assert response.status_code == 403


# =============================================================================
# TEST: Delete User
# =============================================================================


@pytest.mark.unit
class TestDeleteUser:
    """Tests for the delete user endpoint."""

    def test_delete_user_success(self, test_app_admin):
        """Test successful user deletion."""
        with patch("registry.api.management_routes.delete_keycloak_user", new_callable=AsyncMock):
            response = test_app_admin.delete("/management/iam/users/testuser")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"

    def test_delete_user_forbidden_for_non_admin(self, test_app_regular):
        """Test non-admin cannot delete users."""
        response = test_app_regular.delete("/management/iam/users/testuser")

        assert response.status_code == 403

    def test_delete_user_keycloak_error(self, test_app_admin):
        """Test handling of Keycloak errors."""
        with patch("registry.api.management_routes.delete_keycloak_user", new_callable=AsyncMock) as mock_delete:
            mock_delete.side_effect = KeycloakAdminError("User not found")
            response = test_app_admin.delete("/management/iam/users/nonexistent")

        assert response.status_code == 400


# =============================================================================
# TEST: List Groups
# =============================================================================


@pytest.mark.unit
class TestListGroups:
    """Tests for the list groups endpoint."""

    def test_list_groups_success(self, test_app_admin):
        """Test successful group listing."""
        mock_groups = [
            {
                "id": "group-1",
                "name": "test-group",
                "path": "/test-group",
                "attributes": {},
            }
        ]

        with patch("registry.api.management_routes.list_keycloak_groups", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = mock_groups
            response = test_app_admin.get("/management/iam/groups")

        assert response.status_code == 200
        data = response.json()
        assert "groups" in data
        assert data["total"] == 1

    def test_list_groups_forbidden_for_non_admin(self, test_app_regular):
        """Test non-admin cannot list groups."""
        response = test_app_regular.get("/management/iam/groups")

        assert response.status_code == 403

    def test_list_groups_error(self, test_app_admin):
        """Test handling of generic errors."""
        with patch("registry.api.management_routes.list_keycloak_groups", new_callable=AsyncMock) as mock_list:
            mock_list.side_effect = Exception("Database error")
            response = test_app_admin.get("/management/iam/groups")

        assert response.status_code == 502


# =============================================================================
# TEST: Create Group
# =============================================================================


@pytest.mark.unit
class TestCreateGroup:
    """Tests for the create group endpoint."""

    def test_create_group_success(self, test_app_admin):
        """Test successful group creation."""
        mock_result = {
            "id": "group-123",
            "name": "new-group",
            "path": "/new-group",
            "attributes": {},
        }

        with patch("registry.api.management_routes.create_keycloak_group", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_result
            response = test_app_admin.post(
                "/management/iam/groups",
                json={"name": "new-group", "description": "Test group"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "new-group"

    def test_create_group_forbidden_for_non_admin(self, test_app_regular):
        """Test non-admin cannot create groups."""
        response = test_app_regular.post(
            "/management/iam/groups",
            json={"name": "new-group"},
        )

        assert response.status_code == 403

    def test_create_group_already_exists(self, test_app_admin):
        """Test handling of 'already exists' errors."""
        with patch("registry.api.management_routes.create_keycloak_group", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("Group already exists")
            response = test_app_admin.post(
                "/management/iam/groups",
                json={"name": "existing-group"},
            )

        assert response.status_code == 400

    def test_create_group_generic_error(self, test_app_admin):
        """Test handling of generic errors."""
        with patch("registry.api.management_routes.create_keycloak_group", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("Unknown error")
            response = test_app_admin.post(
                "/management/iam/groups",
                json={"name": "new-group"},
            )

        assert response.status_code == 502


# =============================================================================
# TEST: Delete Group
# =============================================================================


@pytest.mark.unit
class TestDeleteGroup:
    """Tests for the delete group endpoint."""

    def test_delete_group_success(self, test_app_admin):
        """Test successful group deletion."""
        with patch("registry.api.management_routes.delete_keycloak_group", new_callable=AsyncMock):
            response = test_app_admin.delete("/management/iam/groups/test-group")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-group"

    def test_delete_group_forbidden_for_non_admin(self, test_app_regular):
        """Test non-admin cannot delete groups."""
        response = test_app_regular.delete("/management/iam/groups/test-group")

        assert response.status_code == 403

    def test_delete_group_not_found(self, test_app_admin):
        """Test handling of 'not found' errors."""
        with patch("registry.api.management_routes.delete_keycloak_group", new_callable=AsyncMock) as mock_delete:
            mock_delete.side_effect = Exception("Group not found")
            response = test_app_admin.delete("/management/iam/groups/nonexistent")

        assert response.status_code == 404

    def test_delete_group_generic_error(self, test_app_admin):
        """Test handling of generic errors."""
        with patch("registry.api.management_routes.delete_keycloak_group", new_callable=AsyncMock) as mock_delete:
            mock_delete.side_effect = Exception("Database error")
            response = test_app_admin.delete("/management/iam/groups/test-group")

        assert response.status_code == 502
