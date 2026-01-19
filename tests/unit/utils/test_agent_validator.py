"""
Unit tests for agent validator.
"""

import logging
from unittest.mock import patch, MagicMock

import pytest

from registry.schemas.agent_models import AgentCard, Skill, SecurityScheme
from registry.utils.agent_validator import (
    ValidationResult,
    _validate_agent_url,
    _validate_skills,
    _validate_security_schemes,
    _validate_tags,
    _check_endpoint_reachability,
    _validate_agent_card,
    validate_agent_card,
    AgentValidator,
)


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: _validate_agent_url
# =============================================================================


@pytest.mark.unit
class TestValidateAgentUrl:
    """Tests for _validate_agent_url function."""

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        assert _validate_agent_url("http://example.com/agent") is True

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        assert _validate_agent_url("https://example.com/agent") is True

    def test_valid_url_with_port(self):
        """Test valid URL with port."""
        assert _validate_agent_url("http://localhost:8080/agent") is True

    def test_valid_url_with_subdomain(self):
        """Test valid URL with subdomain."""
        assert _validate_agent_url("https://api.example.com/v1/agent") is True

    def test_empty_url(self):
        """Test empty URL is invalid."""
        assert _validate_agent_url("") is False

    def test_none_url(self):
        """Test None URL is invalid."""
        assert _validate_agent_url(None) is False

    def test_invalid_protocol(self):
        """Test URL with invalid protocol."""
        assert _validate_agent_url("ftp://example.com/agent") is False

    def test_no_protocol(self):
        """Test URL without protocol."""
        assert _validate_agent_url("example.com/agent") is False


# =============================================================================
# TEST: _validate_skills
# =============================================================================


@pytest.mark.unit
class TestValidateSkills:
    """Tests for _validate_skills function."""

    def test_valid_skills(self):
        """Test valid skills list."""
        skills = [
            Skill(id="skill1", name="Skill 1", description="Description 1", tags=["test"]),
            Skill(id="skill2", name="Skill 2", description="Description 2", tags=["test"]),
        ]
        errors = _validate_skills(skills)
        assert errors == []

    def test_empty_skills_list(self):
        """Test empty skills list is valid."""
        errors = _validate_skills([])
        assert errors == []

    def test_skill_missing_id(self):
        """Test skill with missing ID by modifying after creation."""
        skill = Skill(id="skill1", name="Skill 1", description="Description 1", tags=["test"])
        # Manually set id to empty to test validation function
        object.__setattr__(skill, 'id', "")
        errors = _validate_skills([skill])
        assert len(errors) == 1
        assert "ID cannot be empty" in errors[0]

    def test_skill_missing_name(self):
        """Test skill with missing name by modifying after creation."""
        skill = Skill(id="skill1", name="Skill 1", description="Description 1", tags=["test"])
        # Manually set name to empty to test validation function
        object.__setattr__(skill, 'name', "")
        errors = _validate_skills([skill])
        assert len(errors) == 1
        assert "name cannot be empty" in errors[0]

    def test_skill_missing_description(self):
        """Test skill with missing description by modifying after creation."""
        skill = Skill(id="skill1", name="Skill 1", description="Description 1", tags=["test"])
        # Manually set description to empty to test validation function
        object.__setattr__(skill, 'description', "")
        errors = _validate_skills([skill])
        assert len(errors) == 1
        assert "description cannot be empty" in errors[0]

    def test_invalid_skills_type(self):
        """Test skills as non-list."""
        errors = _validate_skills("not a list")
        assert len(errors) == 1
        assert "must be a list" in errors[0]


# =============================================================================
# TEST: _validate_security_schemes
# =============================================================================


@pytest.mark.unit
class TestValidateSecuritySchemes:
    """Tests for _validate_security_schemes function."""

    def test_valid_apikey_scheme(self):
        """Test valid apiKey security scheme."""
        schemes = {
            "api_key": SecurityScheme(type="apiKey", in_="header", name="X-API-Key")
        }
        errors = _validate_security_schemes(schemes)
        assert errors == []

    def test_valid_http_scheme(self):
        """Test valid HTTP security scheme."""
        schemes = {
            "bearer": SecurityScheme(type="http", scheme="bearer")
        }
        errors = _validate_security_schemes(schemes)
        assert errors == []

    def test_empty_schemes(self):
        """Test empty security schemes."""
        errors = _validate_security_schemes({})
        assert errors == []

    def test_invalid_type(self):
        """Test invalid scheme type by modifying after creation."""
        scheme = SecurityScheme(type="apiKey", in_="header", name="X-API-Key")
        # Manually set type to invalid to test validation function
        object.__setattr__(scheme, 'type', "invalid_type")
        schemes = {"invalid": scheme}
        errors = _validate_security_schemes(schemes)
        assert len(errors) == 1
        assert "invalid type" in errors[0]

    def test_apikey_missing_in(self):
        """Test apiKey scheme missing 'in' field."""
        schemes = {
            "api_key": SecurityScheme(type="apiKey", name="X-API-Key")
        }
        errors = _validate_security_schemes(schemes)
        assert any("'in' is required" in e for e in errors)

    def test_apikey_missing_name(self):
        """Test apiKey scheme missing name field."""
        schemes = {
            "api_key": SecurityScheme(type="apiKey", in_="header")
        }
        errors = _validate_security_schemes(schemes)
        assert any("'name' is required" in e for e in errors)

    def test_http_missing_scheme(self):
        """Test HTTP scheme missing scheme field."""
        schemes = {
            "bearer": SecurityScheme(type="http")
        }
        errors = _validate_security_schemes(schemes)
        assert any("'scheme' is required" in e for e in errors)

    def test_oauth2_missing_flows(self):
        """Test oauth2 scheme missing flows."""
        schemes = {
            "oauth": SecurityScheme(type="oauth2")
        }
        errors = _validate_security_schemes(schemes)
        assert any("'flows' is required" in e for e in errors)

    def test_openidconnect_missing_url(self):
        """Test openIdConnect scheme missing URL."""
        schemes = {
            "oidc": SecurityScheme(type="openIdConnect")
        }
        errors = _validate_security_schemes(schemes)
        assert any("URL required" in e for e in errors)

    def test_invalid_schemes_type(self):
        """Test schemes as non-dict."""
        errors = _validate_security_schemes("not a dict")
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]


# =============================================================================
# TEST: _validate_tags
# =============================================================================


@pytest.mark.unit
class TestValidateTags:
    """Tests for _validate_tags function."""

    def test_valid_tags(self):
        """Test valid tags list."""
        tags = ["tag1", "tag2", "tag3"]
        errors = _validate_tags(tags)
        assert errors == []

    def test_empty_tags_list(self):
        """Test empty tags list is valid."""
        errors = _validate_tags([])
        assert errors == []

    def test_empty_tag_string(self):
        """Test empty tag string."""
        tags = ["tag1", "", "tag3"]
        errors = _validate_tags(tags)
        assert len(errors) == 1
        assert "cannot be empty" in errors[0]

    def test_whitespace_only_tag(self):
        """Test whitespace-only tag."""
        tags = ["tag1", "   ", "tag3"]
        errors = _validate_tags(tags)
        assert len(errors) == 1
        assert "cannot be empty" in errors[0]

    def test_non_string_tag(self):
        """Test non-string tag."""
        tags = ["tag1", 123, "tag3"]
        errors = _validate_tags(tags)
        assert len(errors) == 1
        assert "must be a string" in errors[0]

    def test_invalid_tags_type(self):
        """Test tags as non-list."""
        errors = _validate_tags("not a list")
        assert len(errors) == 1
        assert "must be a list" in errors[0]


# =============================================================================
# TEST: _check_endpoint_reachability
# =============================================================================


@pytest.mark.unit
class TestCheckEndpointReachability:
    """Tests for _check_endpoint_reachability function."""

    def test_reachable_endpoint(self):
        """Test reachable endpoint."""
        with patch("registry.utils.agent_validator.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            is_reachable, error = _check_endpoint_reachability("http://example.com")

            assert is_reachable is True
            assert error is None

    def test_unreachable_endpoint_status(self):
        """Test unreachable endpoint by status code."""
        with patch("registry.utils.agent_validator.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            is_reachable, error = _check_endpoint_reachability("http://example.com")

            assert is_reachable is False
            assert "status 404" in error

    def test_endpoint_timeout(self):
        """Test endpoint timeout."""
        import httpx
        with patch("registry.utils.agent_validator.httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Timeout")

            is_reachable, error = _check_endpoint_reachability("http://example.com")

            assert is_reachable is False
            assert "timed out" in error

    def test_endpoint_exception(self):
        """Test endpoint exception."""
        with patch("registry.utils.agent_validator.httpx.get") as mock_get:
            mock_get.side_effect = Exception("Connection refused")

            is_reachable, error = _check_endpoint_reachability("http://example.com")

            assert is_reachable is False
            assert "Connection refused" in error


# =============================================================================
# TEST: _validate_agent_card
# =============================================================================


@pytest.mark.unit
class TestValidateAgentCardInternal:
    """Tests for _validate_agent_card function."""

    @pytest.fixture
    def valid_agent_card(self):
        """Create a valid agent card for testing."""
        return AgentCard(
            name="Test Agent",
            description="A test agent",
            url="https://example.com/agent",
            path="/test-agent",
            protocol_version="1.0",
            version="1.0.0",
            visibility="public",
            trust_level="unverified",
            skills=[],
            security_schemes={},
            tags=["test"],
        )

    def test_valid_agent_card(self, valid_agent_card):
        """Test valid agent card."""
        is_valid, errors = _validate_agent_card(valid_agent_card)
        assert is_valid is True
        assert errors == []

    def test_empty_name(self, valid_agent_card):
        """Test agent card with empty name."""
        valid_agent_card.name = ""
        is_valid, errors = _validate_agent_card(valid_agent_card)
        assert is_valid is False
        assert any("name cannot be empty" in e for e in errors)

    def test_empty_description(self, valid_agent_card):
        """Test agent card with empty description."""
        valid_agent_card.description = ""
        is_valid, errors = _validate_agent_card(valid_agent_card)
        assert is_valid is False
        assert any("description cannot be empty" in e for e in errors)

    def test_invalid_url(self, valid_agent_card):
        """Test agent card with invalid URL."""
        valid_agent_card.url = "invalid-url"
        is_valid, errors = _validate_agent_card(valid_agent_card)
        assert is_valid is False
        assert any("URL must be HTTP" in e for e in errors)

    def test_invalid_protocol_version(self, valid_agent_card):
        """Test agent card with invalid protocol version."""
        valid_agent_card.protocol_version = "invalid"
        is_valid, errors = _validate_agent_card(valid_agent_card)
        assert is_valid is False
        assert any("Protocol version" in e for e in errors)

    def test_valid_protocol_version_formats(self, valid_agent_card):
        """Test valid protocol version formats."""
        valid_agent_card.protocol_version = "1.0"
        is_valid, _ = _validate_agent_card(valid_agent_card)
        assert is_valid is True

        valid_agent_card.protocol_version = "1.0.0"
        is_valid, _ = _validate_agent_card(valid_agent_card)
        assert is_valid is True

    def test_invalid_visibility(self, valid_agent_card):
        """Test agent card with invalid visibility."""
        valid_agent_card.visibility = "invalid"
        is_valid, errors = _validate_agent_card(valid_agent_card)
        assert is_valid is False
        assert any("Invalid visibility" in e for e in errors)

    def test_invalid_trust_level(self, valid_agent_card):
        """Test agent card with invalid trust level."""
        valid_agent_card.trust_level = "invalid"
        is_valid, errors = _validate_agent_card(valid_agent_card)
        assert is_valid is False
        assert any("Invalid trust level" in e for e in errors)


# =============================================================================
# TEST: validate_agent_card (public function)
# =============================================================================


@pytest.mark.unit
class TestValidateAgentCardPublic:
    """Tests for validate_agent_card public function."""

    @pytest.fixture
    def valid_agent_card(self):
        """Create a valid agent card for testing."""
        return AgentCard(
            name="Test Agent",
            description="A test agent",
            url="https://example.com/agent",
            path="/test-agent",
            protocol_version="1.0",
            version="1.0.0",
            visibility="public",
            trust_level="unverified",
            skills=[],
            security_schemes={},
            tags=["test"],
        )

    def test_valid_card_returns_valid_result(self, valid_agent_card):
        """Test that valid card returns valid result."""
        result = validate_agent_card(valid_agent_card)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert result.errors == []

    def test_invalid_card_returns_errors(self, valid_agent_card):
        """Test that invalid card returns errors."""
        valid_agent_card.name = ""
        result = validate_agent_card(valid_agent_card)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_reachability_check_adds_warning(self, valid_agent_card):
        """Test that unreachable endpoint adds warning."""
        with patch("registry.utils.agent_validator._check_endpoint_reachability") as mock_check:
            mock_check.return_value = (False, "Connection refused")

            result = validate_agent_card(valid_agent_card, check_reachability=True)

            assert result.is_valid is True  # Still valid, just warning
            assert len(result.warnings) == 1
            assert "unreachable" in result.warnings[0]


# =============================================================================
# TEST: AgentValidator class
# =============================================================================


@pytest.mark.unit
class TestAgentValidatorClass:
    """Tests for AgentValidator class."""

    @pytest.fixture
    def valid_agent_card(self):
        """Create a valid agent card for testing."""
        return AgentCard(
            name="Test Agent",
            description="A test agent",
            url="https://example.com/agent",
            path="/test-agent",
            protocol_version="1.0",
            version="1.0.0",
            visibility="public",
            trust_level="unverified",
            skills=[],
            security_schemes={},
            tags=["test"],
        )

    @pytest.mark.asyncio
    async def test_async_validate(self, valid_agent_card):
        """Test async validation method."""
        validator = AgentValidator()
        result = await validator.validate_agent_card(valid_agent_card)
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_async_validate_with_verify(self, valid_agent_card):
        """Test async validation with endpoint verification."""
        validator = AgentValidator()

        with patch("registry.utils.agent_validator._check_endpoint_reachability") as mock_check:
            mock_check.return_value = (True, None)

            result = await validator.validate_agent_card(
                valid_agent_card, verify_endpoint=True
            )

            assert result.is_valid is True
