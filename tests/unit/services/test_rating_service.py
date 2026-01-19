"""
Unit tests for registry.services.rating_service module.

This module tests the shared rating service utilities for servers and agents,
including validation, rating updates, and average calculation.
"""

import logging
from typing import Any, Dict, List

import pytest

from registry.services.rating_service import (
    MAX_RATINGS_PER_RESOURCE,
    MAX_RATING_VALUE,
    MIN_RATING_VALUE,
    calculate_average_rating,
    update_rating_details,
    validate_rating,
)


logger = logging.getLogger(__name__)


# =============================================================================
# TEST: validate_rating
# =============================================================================


@pytest.mark.unit
class TestValidateRating:
    """Tests for the validate_rating function."""

    def test_validate_rating_valid_min(self):
        """Test validation with minimum valid rating."""
        validate_rating(MIN_RATING_VALUE)

    def test_validate_rating_valid_max(self):
        """Test validation with maximum valid rating."""
        validate_rating(MAX_RATING_VALUE)

    def test_validate_rating_valid_middle(self):
        """Test validation with middle valid rating."""
        validate_rating(3)

    def test_validate_rating_all_valid_values(self):
        """Test validation with all valid rating values 1-5."""
        for rating in range(MIN_RATING_VALUE, MAX_RATING_VALUE + 1):
            validate_rating(rating)

    def test_validate_rating_invalid_zero(self):
        """Test validation rejects zero rating."""
        with pytest.raises(ValueError, match="Rating must be between"):
            validate_rating(0)

    def test_validate_rating_invalid_negative(self):
        """Test validation rejects negative rating."""
        with pytest.raises(ValueError, match="Rating must be between"):
            validate_rating(-1)

    def test_validate_rating_invalid_too_high(self):
        """Test validation rejects rating above maximum."""
        with pytest.raises(ValueError, match="Rating must be between"):
            validate_rating(6)

    def test_validate_rating_invalid_string(self):
        """Test validation rejects string type."""
        with pytest.raises(ValueError, match="Rating must be an integer"):
            validate_rating("5")  # type: ignore

    def test_validate_rating_invalid_float(self):
        """Test validation rejects float type."""
        with pytest.raises(ValueError, match="Rating must be an integer"):
            validate_rating(4.5)  # type: ignore

    def test_validate_rating_invalid_none(self):
        """Test validation rejects None type."""
        with pytest.raises(ValueError, match="Rating must be an integer"):
            validate_rating(None)  # type: ignore

    def test_validate_rating_invalid_list(self):
        """Test validation rejects list type."""
        with pytest.raises(ValueError, match="Rating must be an integer"):
            validate_rating([5])  # type: ignore


# =============================================================================
# TEST: update_rating_details
# =============================================================================


@pytest.mark.unit
class TestUpdateRatingDetails:
    """Tests for the update_rating_details function."""

    def test_update_rating_details_add_new_rating(self):
        """Test adding a new user rating to empty list."""
        rating_details: List[Dict[str, Any]] = []
        username = "user1"
        rating = 5

        result, is_new = update_rating_details(rating_details, username, rating)

        assert is_new is True
        assert len(result) == 1
        assert result[0]["user"] == username
        assert result[0]["rating"] == rating

    def test_update_rating_details_add_to_none(self):
        """Test adding a rating when rating_details is None."""
        username = "user1"
        rating = 4

        result, is_new = update_rating_details(None, username, rating)

        assert is_new is True
        assert len(result) == 1
        assert result[0]["user"] == username
        assert result[0]["rating"] == rating

    def test_update_rating_details_add_multiple_users(self):
        """Test adding ratings from multiple users."""
        rating_details: List[Dict[str, Any]] = []

        result1, is_new1 = update_rating_details(rating_details, "user1", 5)
        result2, is_new2 = update_rating_details(result1, "user2", 4)
        result3, is_new3 = update_rating_details(result2, "user3", 3)

        assert is_new1 is True
        assert is_new2 is True
        assert is_new3 is True
        assert len(result3) == 3

    def test_update_rating_details_update_existing_rating(self):
        """Test updating an existing user rating."""
        rating_details = [{"user": "user1", "rating": 3}]
        username = "user1"
        new_rating = 5

        result, is_new = update_rating_details(rating_details, username, new_rating)

        assert is_new is False
        assert len(result) == 1
        assert result[0]["user"] == username
        assert result[0]["rating"] == new_rating

    def test_update_rating_details_preserves_other_ratings(self):
        """Test updating a rating preserves other users ratings."""
        rating_details = [
            {"user": "user1", "rating": 3},
            {"user": "user2", "rating": 4},
            {"user": "user3", "rating": 5},
        ]

        result, is_new = update_rating_details(rating_details, "user2", 2)

        assert is_new is False
        assert len(result) == 3
        assert result[0]["rating"] == 3
        assert result[1]["rating"] == 2
        assert result[2]["rating"] == 5

    def test_update_rating_details_buffer_overflow(self):
        """Test that buffer is maintained at MAX_RATINGS_PER_RESOURCE."""
        rating_details = [
            {"user": f"user{i}", "rating": (i % 5) + 1}
            for i in range(MAX_RATINGS_PER_RESOURCE)
        ]

        result, is_new = update_rating_details(rating_details, "new_user", 5)

        assert is_new is True
        assert len(result) == MAX_RATINGS_PER_RESOURCE
        assert result[0]["user"] == "user1"
        assert result[-1]["user"] == "new_user"

    def test_update_rating_details_buffer_no_overflow_on_update(self):
        """Test that buffer is not trimmed when updating existing rating."""
        rating_details = [
            {"user": f"user{i}", "rating": (i % 5) + 1}
            for i in range(MAX_RATINGS_PER_RESOURCE)
        ]

        result, is_new = update_rating_details(rating_details, "user0", 1)

        assert is_new is False
        assert len(result) == MAX_RATINGS_PER_RESOURCE
        assert result[0]["user"] == "user0"
        assert result[0]["rating"] == 1


# =============================================================================
# TEST: calculate_average_rating
# =============================================================================


@pytest.mark.unit
class TestCalculateAverageRating:
    """Tests for the calculate_average_rating function."""

    def test_calculate_average_single_rating(self):
        """Test average calculation with single rating."""
        rating_details = [{"user": "user1", "rating": 5}]

        result = calculate_average_rating(rating_details)

        assert result == 5.0

    def test_calculate_average_multiple_ratings(self):
        """Test average calculation with multiple ratings."""
        rating_details = [
            {"user": "user1", "rating": 5},
            {"user": "user2", "rating": 3},
            {"user": "user3", "rating": 4},
        ]

        result = calculate_average_rating(rating_details)

        assert result == 4.0

    def test_calculate_average_returns_float(self):
        """Test that average calculation returns float."""
        rating_details = [
            {"user": "user1", "rating": 4},
            {"user": "user2", "rating": 5},
        ]

        result = calculate_average_rating(rating_details)

        assert isinstance(result, float)
        assert result == 4.5

    def test_calculate_average_empty_list_raises(self):
        """Test that empty list raises ValueError."""
        rating_details: List[Dict[str, Any]] = []

        with pytest.raises(ValueError, match="Cannot calculate average from empty"):
            calculate_average_rating(rating_details)

    def test_calculate_average_all_same_ratings(self):
        """Test average calculation when all ratings are the same."""
        rating_details = [{"user": f"user{i}", "rating": 3} for i in range(10)]

        result = calculate_average_rating(rating_details)

        assert result == 3.0

    def test_calculate_average_min_max_ratings(self):
        """Test average calculation with min and max ratings only."""
        rating_details = [
            {"user": "user1", "rating": MIN_RATING_VALUE},
            {"user": "user2", "rating": MAX_RATING_VALUE},
        ]

        result = calculate_average_rating(rating_details)

        assert result == (MIN_RATING_VALUE + MAX_RATING_VALUE) / 2.0
