"""Unit tests for DateFunctions class."""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from ha_synthetic_sensors.datetime_functions.date_functions import DateFunctions


class TestDateFunctions:
    """Test DateFunctions functionality."""

    @pytest.fixture
    def date_functions(self):
        """Create a DateFunctions instance for testing."""
        return DateFunctions()

    def test_initialization(self, date_functions):
        """Test DateFunctions initialization."""
        assert date_functions is not None
        assert hasattr(date_functions, "_supported_functions")
        assert isinstance(date_functions._supported_functions, set)

    def test_supported_functions(self, date_functions):
        """Test that all expected functions are supported."""
        expected_functions = {"today", "yesterday", "tomorrow", "utc_today", "utc_yesterday", "date"}
        assert date_functions.get_supported_functions() == expected_functions

    def test_can_handle_function(self, date_functions):
        """Test can_handle_function returns correct results."""
        # Test supported functions
        assert date_functions.can_handle_function("today") is True
        assert date_functions.can_handle_function("yesterday") is True
        assert date_functions.can_handle_function("tomorrow") is True
        assert date_functions.can_handle_function("utc_today") is True
        assert date_functions.can_handle_function("utc_yesterday") is True
        assert date_functions.can_handle_function("date") is True

        # Test unsupported functions
        assert date_functions.can_handle_function("now") is False
        assert date_functions.can_handle_function("invalid") is False
        assert date_functions.can_handle_function("") is False

    def test_get_function_info(self, date_functions):
        """Test get_function_info returns correct metadata."""
        info = date_functions.get_function_info()

        assert isinstance(info, dict)
        assert info["handler_name"] == "DateFunctions"
        assert info["category"] == "date_functions"
        assert info["description"] == "Functions for getting date boundaries (midnight) with timezone awareness"
        assert info["return_type"] == "str"
        assert info["return_format"] == "ISO datetime string"

        # Check functions dictionary
        functions = info["functions"]
        assert "today" in functions
        assert "yesterday" in functions
        assert "tomorrow" in functions
        assert "utc_today" in functions
        assert "utc_yesterday" in functions
        assert "date" in functions

    @patch("ha_synthetic_sensors.datetime_functions.date_functions.datetime")
    def test_today_function(self, mock_datetime, date_functions):
        """Test today() function returns correct ISO datetime string."""
        # Mock datetime.now() to return a fixed date
        mock_date = date(2025, 1, 15)
        mock_datetime.now.return_value.date.return_value = mock_date
        mock_datetime.combine.return_value.isoformat.return_value = "2025-01-15T00:00:00"

        result = date_functions.evaluate_function("today")

        assert result == "2025-01-15T00:00:00"
        mock_datetime.now.assert_called_once()
        mock_datetime.combine.assert_called_once_with(mock_date, mock_datetime.min.time())

    @patch("ha_synthetic_sensors.datetime_functions.date_functions.datetime")
    def test_yesterday_function(self, mock_datetime, date_functions):
        """Test yesterday() function returns correct ISO datetime string."""
        # Mock datetime.now() to return a fixed date
        mock_date = date(2025, 1, 15)
        mock_datetime.now.return_value.date.return_value = mock_date
        mock_datetime.combine.return_value.isoformat.return_value = "2025-01-14T00:00:00"

        result = date_functions.evaluate_function("yesterday")

        assert result == "2025-01-14T00:00:00"
        mock_datetime.now.assert_called_once()
        # yesterday should be today - timedelta(days=1)
        expected_yesterday = mock_date - timedelta(days=1)
        mock_datetime.combine.assert_called_once_with(expected_yesterday, mock_datetime.min.time())

    @patch("ha_synthetic_sensors.datetime_functions.date_functions.datetime")
    def test_tomorrow_function(self, mock_datetime, date_functions):
        """Test tomorrow() function returns correct ISO datetime string."""
        # Mock datetime.now() to return a fixed date
        mock_date = date(2025, 1, 15)
        mock_datetime.now.return_value.date.return_value = mock_date
        mock_datetime.combine.return_value.isoformat.return_value = "2025-01-16T00:00:00"

        result = date_functions.evaluate_function("tomorrow")

        assert result == "2025-01-16T00:00:00"
        mock_datetime.now.assert_called_once()
        # tomorrow should be today + timedelta(days=1)
        expected_tomorrow = mock_date + timedelta(days=1)
        mock_datetime.combine.assert_called_once_with(expected_tomorrow, mock_datetime.min.time())

    @patch("ha_synthetic_sensors.datetime_functions.date_functions.datetime")
    @patch("ha_synthetic_sensors.datetime_functions.date_functions.pytz")
    def test_utc_today_function(self, mock_pytz, mock_datetime, date_functions):
        """Test utc_today() function returns correct UTC ISO datetime string."""
        # Mock datetime.now(pytz.UTC) to return a fixed UTC date
        mock_utc_date = date(2025, 1, 15)
        mock_datetime.now.return_value.date.return_value = mock_utc_date
        mock_datetime.combine.return_value.isoformat.return_value = "2025-01-15T00:00:00+00:00"

        result = date_functions.evaluate_function("utc_today")

        assert result == "2025-01-15T00:00:00+00:00"
        mock_datetime.now.assert_called_once_with(mock_pytz.UTC)
        mock_datetime.combine.assert_called_once_with(mock_utc_date, mock_datetime.min.time(), mock_pytz.UTC)

    @patch("ha_synthetic_sensors.datetime_functions.date_functions.datetime")
    @patch("ha_synthetic_sensors.datetime_functions.date_functions.pytz")
    def test_utc_yesterday_function(self, mock_pytz, mock_datetime, date_functions):
        """Test utc_yesterday() function returns correct UTC ISO datetime string."""
        # Mock datetime.now(pytz.UTC) to return a fixed UTC date
        mock_utc_date = date(2025, 1, 15)
        mock_datetime.now.return_value.date.return_value = mock_utc_date
        mock_datetime.combine.return_value.isoformat.return_value = "2025-01-14T00:00:00+00:00"

        result = date_functions.evaluate_function("utc_yesterday")

        assert result == "2025-01-14T00:00:00+00:00"
        mock_datetime.now.assert_called_once_with(mock_pytz.UTC)
        # utc_yesterday should be utc_today - timedelta(days=1)
        expected_utc_yesterday = mock_utc_date - timedelta(days=1)
        mock_datetime.combine.assert_called_once_with(expected_utc_yesterday, mock_datetime.min.time(), mock_pytz.UTC)

    def test_date_function_with_integers(self, date_functions):
        """Test date() function with integer arguments (year, month, day)."""
        result = date_functions.evaluate_function("date", [2025, 1, 15])

        # Should return ISO date format (YYYY-MM-DD)
        assert result == "2025-01-15"

    def test_date_function_with_string(self, date_functions):
        """Test date() function with string argument (YYYY-MM-DD format)."""
        with patch("ha_synthetic_sensors.datetime_functions.date_functions.datetime") as mock_datetime:
            mock_datetime.strptime.return_value.date.return_value = date(2025, 1, 15)
            mock_datetime.combine.return_value.isoformat.return_value = "2025-01-15T00:00:00"

            result = date_functions.evaluate_function("date", ["2025-01-15"])

            assert result == "2025-01-15T00:00:00"
            mock_datetime.strptime.assert_called_once_with("2025-01-15", "%Y-%m-%d")

    def test_date_function_with_invalid_integers(self, date_functions):
        """Test date() function with invalid integer arguments."""
        # Invalid month
        with pytest.raises(ValueError, match="Invalid date constructor arguments"):
            date_functions.evaluate_function("date", [2025, 13, 1])

        # Invalid day
        with pytest.raises(ValueError, match="Invalid date constructor arguments"):
            date_functions.evaluate_function("date", [2025, 1, 32])

    def test_date_function_with_invalid_string(self, date_functions):
        """Test date() function with invalid string format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            date_functions.evaluate_function("date", ["invalid-date"])

    def test_date_function_with_wrong_number_of_arguments(self, date_functions):
        """Test date() function with wrong number of arguments."""
        # No arguments
        with pytest.raises(ValueError, match="date\\(\\) function requires arguments"):
            date_functions.evaluate_function("date")

        # Two arguments (not supported)
        with pytest.raises(
            ValueError, match="date\\(\\) expects either \\(year, month, day\\) integers or a single date string"
        ):
            date_functions.evaluate_function("date", [2025, 1])

        # Four arguments (not supported)
        with pytest.raises(
            ValueError, match="date\\(\\) expects either \\(year, month, day\\) integers or a single date string"
        ):
            date_functions.evaluate_function("date", [2025, 1, 15, 12])

    def test_date_function_with_non_string_single_argument(self, date_functions):
        """Test date() function with non-string single argument."""
        with pytest.raises(
            ValueError, match="date\\(\\) expects either \\(year, month, day\\) integers or a single date string"
        ):
            date_functions.evaluate_function("date", [123])

    def test_unsupported_function(self, date_functions):
        """Test that unsupported functions raise ValueError."""
        with pytest.raises(ValueError, match="Function 'invalid' is not supported"):
            date_functions.evaluate_function("invalid")

    def test_functions_with_unexpected_arguments(self, date_functions):
        """Test that functions that don't accept arguments raise ValueError when given arguments."""
        # today() doesn't accept arguments
        with pytest.raises(ValueError, match="Function 'today' does not accept arguments"):
            date_functions.evaluate_function("today", ["some_arg"])

        # yesterday() doesn't accept arguments
        with pytest.raises(ValueError, match="Function 'yesterday' does not accept arguments"):
            date_functions.evaluate_function("yesterday", [1, 2, 3])

        # tomorrow() doesn't accept arguments
        with pytest.raises(ValueError, match="Function 'tomorrow' does not accept arguments"):
            date_functions.evaluate_function("tomorrow", ["arg"])

    def test_functions_with_none_arguments(self, date_functions):
        """Test that functions work correctly with None arguments (no arguments)."""
        # These should work fine with None args
        with patch("ha_synthetic_sensors.datetime_functions.date_functions.datetime") as mock_datetime:
            mock_datetime.now.return_value.date.return_value = date(2025, 1, 15)
            mock_datetime.combine.return_value.isoformat.return_value = "2025-01-15T00:00:00"

            result = date_functions.evaluate_function("today", None)
            assert result == "2025-01-15T00:00:00"

    def test_date_function_edge_cases(self, date_functions):
        """Test date() function with edge case dates."""
        # Leap year date
        result = date_functions.evaluate_function("date", [2024, 2, 29])
        assert result == "2024-02-29"

        # Year boundary
        result = date_functions.evaluate_function("date", [2025, 12, 31])
        assert result == "2025-12-31"

        # Beginning of year
        result = date_functions.evaluate_function("date", [2025, 1, 1])
        assert result == "2025-01-01"

    def test_date_function_string_edge_cases(self, date_functions):
        """Test date() function with edge case string dates."""
        with patch("ha_synthetic_sensors.datetime_functions.date_functions.datetime") as mock_datetime:
            # Leap year
            mock_datetime.strptime.return_value.date.return_value = date(2024, 2, 29)
            mock_datetime.combine.return_value.isoformat.return_value = "2024-02-29T00:00:00"

            result = date_functions.evaluate_function("date", ["2024-02-29"])
            assert result == "2024-02-29T00:00:00"

            # Year boundary
            mock_datetime.strptime.return_value.date.return_value = date(2025, 12, 31)
            mock_datetime.combine.return_value.isoformat.return_value = "2025-12-31T00:00:00"

            result = date_functions.evaluate_function("date", ["2025-12-31"])
            assert result == "2025-12-31T00:00:00"

    def test_validate_function_name(self, date_functions):
        """Test _validate_function_name method."""
        # Valid function names should not raise
        date_functions._validate_function_name("today")
        date_functions._validate_function_name("date")

        # Invalid function names should raise
        with pytest.raises(ValueError, match="Function 'invalid' is not supported"):
            date_functions._validate_function_name("invalid")

    def test_validate_no_arguments(self, date_functions):
        """Test _validate_no_arguments method."""
        # None arguments should not raise
        date_functions._validate_no_arguments("today", None)

        # Empty list should not raise
        date_functions._validate_no_arguments("today", [])

        # Non-empty arguments should raise
        with pytest.raises(ValueError, match="Function 'today' does not accept arguments"):
            date_functions._validate_no_arguments("today", ["arg"])
