"""Unit tests for TimezoneFunctions class."""

import pytest
from datetime import datetime
from unittest.mock import patch, Mock

from ha_synthetic_sensors.datetime_functions.timezone_functions import TimezoneFunctions


class TestTimezoneFunctions:
    """Test TimezoneFunctions functionality."""

    @pytest.fixture
    def timezone_functions(self):
        """Create a TimezoneFunctions instance for testing."""
        return TimezoneFunctions()

    def test_initialization(self, timezone_functions):
        """Test TimezoneFunctions initialization."""
        assert timezone_functions is not None
        assert hasattr(timezone_functions, "_supported_functions")
        assert isinstance(timezone_functions._supported_functions, set)

    def test_supported_functions(self, timezone_functions):
        """Test that all expected functions are supported."""
        expected_functions = {"now", "local_now", "utc_now"}
        assert timezone_functions.get_supported_functions() == expected_functions

    def test_can_handle_function(self, timezone_functions):
        """Test can_handle_function returns correct results."""
        # Test supported functions
        assert timezone_functions.can_handle_function("now") is True
        assert timezone_functions.can_handle_function("local_now") is True
        assert timezone_functions.can_handle_function("utc_now") is True

        # Test unsupported functions
        assert timezone_functions.can_handle_function("today") is False
        assert timezone_functions.can_handle_function("invalid") is False
        assert timezone_functions.can_handle_function("") is False

    def test_get_function_info(self, timezone_functions):
        """Test get_function_info returns correct metadata."""
        info = timezone_functions.get_function_info()

        assert isinstance(info, dict)
        assert info["handler_name"] == "TimezoneFunctions"
        assert info["category"] == "timezone_datetime"
        assert info["description"] == "Functions for getting current datetime with timezone awareness"
        assert info["return_type"] == "str"
        assert info["return_format"] == "ISO datetime string"

        # Check functions dictionary
        functions = info["functions"]
        assert "now" in functions
        assert "local_now" in functions
        assert "utc_now" in functions

    @patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime")
    def test_now_function(self, mock_datetime, timezone_functions):
        """Test now() function returns correct ISO datetime string."""
        # Mock datetime.now() to return a mock datetime object
        mock_now = Mock()
        mock_datetime.now.return_value = mock_now
        mock_now.isoformat.return_value = "2025-01-15T12:30:45.123456"

        result = timezone_functions.evaluate_function("now")

        assert result == "2025-01-15T12:30:45.123456"
        mock_datetime.now.assert_called_once()
        mock_now.isoformat.assert_called_once()

    @patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime")
    def test_local_now_function(self, mock_datetime, timezone_functions):
        """Test local_now() function returns correct ISO datetime string."""
        # Mock datetime.now() to return a mock datetime object
        mock_now = Mock()
        mock_datetime.now.return_value = mock_now
        mock_now.isoformat.return_value = "2025-01-15T12:30:45.123456"

        result = timezone_functions.evaluate_function("local_now")

        assert result == "2025-01-15T12:30:45.123456"
        mock_datetime.now.assert_called_once()
        mock_now.isoformat.assert_called_once()

    @patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime")
    @patch("ha_synthetic_sensors.datetime_functions.timezone_functions.pytz")
    def test_utc_now_function(self, mock_pytz, mock_datetime, timezone_functions):
        """Test utc_now() function returns correct UTC ISO datetime string."""
        # Mock datetime.now(pytz.UTC) to return a mock datetime object
        mock_utc_now = Mock()
        mock_datetime.now.return_value = mock_utc_now
        mock_utc_now.isoformat.return_value = "2025-01-15T12:30:45.123456+00:00"

        result = timezone_functions.evaluate_function("utc_now")

        assert result == "2025-01-15T12:30:45.123456+00:00"
        mock_datetime.now.assert_called_once_with(mock_pytz.UTC)
        mock_utc_now.isoformat.assert_called_once()

    def test_unsupported_function(self, timezone_functions):
        """Test that unsupported functions raise ValueError."""
        with pytest.raises(ValueError, match="Function 'invalid' is not supported"):
            timezone_functions.evaluate_function("invalid")

    def test_functions_with_unexpected_arguments(self, timezone_functions):
        """Test that functions that don't accept arguments raise ValueError when given arguments."""
        # now() doesn't accept arguments
        with pytest.raises(ValueError, match="Function 'now' does not accept arguments"):
            timezone_functions.evaluate_function("now", ["some_arg"])

        # local_now() doesn't accept arguments
        with pytest.raises(ValueError, match="Function 'local_now' does not accept arguments"):
            timezone_functions.evaluate_function("local_now", [1, 2, 3])

        # utc_now() doesn't accept arguments
        with pytest.raises(ValueError, match="Function 'utc_now' does not accept arguments"):
            timezone_functions.evaluate_function("utc_now", ["arg"])

    def test_functions_with_none_arguments(self, timezone_functions):
        """Test that functions work correctly with None arguments (no arguments)."""
        # These should work fine with None args
        with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime") as mock_datetime:
            mock_now = Mock()
            mock_datetime.now.return_value = mock_now
            mock_now.isoformat.return_value = "2025-01-15T12:30:45"

            result = timezone_functions.evaluate_function("now", None)
            assert result == "2025-01-15T12:30:45"

    def test_functions_with_empty_arguments(self, timezone_functions):
        """Test that functions work correctly with empty arguments list."""
        # These should work fine with empty args
        with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime") as mock_datetime:
            mock_now = Mock()
            mock_datetime.now.return_value = mock_now
            mock_now.isoformat.return_value = "2025-01-15T12:30:45"

            result = timezone_functions.evaluate_function("now", [])
            assert result == "2025-01-15T12:30:45"

    def test_validate_function_name(self, timezone_functions):
        """Test _validate_function_name method."""
        # Valid function names should not raise
        timezone_functions._validate_function_name("now")
        timezone_functions._validate_function_name("utc_now")

        # Invalid function names should raise
        with pytest.raises(ValueError, match="Function 'invalid' is not supported"):
            timezone_functions._validate_function_name("invalid")

    def test_validate_no_arguments(self, timezone_functions):
        """Test _validate_no_arguments method."""
        # None arguments should not raise
        timezone_functions._validate_no_arguments("now", None)

        # Empty list should not raise
        timezone_functions._validate_no_arguments("now", [])

        # Non-empty arguments should raise
        with pytest.raises(ValueError, match="Function 'now' does not accept arguments"):
            timezone_functions._validate_no_arguments("now", ["arg"])

    def test_now_and_local_now_are_equivalent(self, timezone_functions):
        """Test that now() and local_now() return the same result."""
        with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime") as mock_datetime:
            mock_now = Mock()
            mock_datetime.now.return_value = mock_now
            mock_now.isoformat.return_value = "2025-01-15T12:30:45"

            now_result = timezone_functions.evaluate_function("now")
            local_now_result = timezone_functions.evaluate_function("local_now")

            assert now_result == local_now_result
            assert now_result == "2025-01-15T12:30:45"

    def test_utc_now_uses_pytz_utc(self, timezone_functions):
        """Test that utc_now() uses pytz.UTC timezone."""
        with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime") as mock_datetime:
            with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.pytz") as mock_pytz:
                mock_utc_now = Mock()
                mock_datetime.now.return_value = mock_utc_now
                mock_utc_now.isoformat.return_value = "2025-01-15T12:30:45+00:00"

                timezone_functions.evaluate_function("utc_now")

                # Verify that datetime.now() was called with pytz.UTC
                mock_datetime.now.assert_called_once_with(mock_pytz.UTC)

    def test_isoformat_called_on_datetime_objects(self, timezone_functions):
        """Test that isoformat() is called on the datetime objects."""
        with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime") as mock_datetime:
            mock_now = Mock()
            mock_datetime.now.return_value = mock_now
            mock_now.isoformat.return_value = "2025-01-15T12:30:45"

            timezone_functions.evaluate_function("now")

            # Verify that isoformat() was called on the datetime object
            mock_now.isoformat.assert_called_once()

    def test_all_supported_functions_return_strings(self, timezone_functions):
        """Test that all supported functions return string results."""
        with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime") as mock_datetime:
            mock_now = Mock()
            mock_datetime.now.return_value = mock_now
            mock_now.isoformat.return_value = "2025-01-15T12:30:45"

            # Test all supported functions return strings
            for func in ["now", "local_now"]:
                result = timezone_functions.evaluate_function(func)
                assert isinstance(result, str)
                assert result == "2025-01-15T12:30:45"

        with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.datetime") as mock_datetime:
            with patch("ha_synthetic_sensors.datetime_functions.timezone_functions.pytz") as mock_pytz:
                mock_utc_now = Mock()
                mock_datetime.now.return_value = mock_utc_now
                mock_utc_now.isoformat.return_value = "2025-01-15T12:30:45+00:00"

                result = timezone_functions.evaluate_function("utc_now")
                assert isinstance(result, str)
                assert result == "2025-01-15T12:30:45+00:00"

    def test_error_propagation_from_validation(self, timezone_functions):
        """Test that validation errors are properly propagated."""
        # Test unsupported function
        with pytest.raises(ValueError, match="Function 'invalid' is not supported"):
            timezone_functions.evaluate_function("invalid")

        # Test function with arguments
        with pytest.raises(ValueError, match="Function 'now' does not accept arguments"):
            timezone_functions.evaluate_function("now", ["arg"])
