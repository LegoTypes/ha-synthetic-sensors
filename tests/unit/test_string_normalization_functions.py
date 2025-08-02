"""Unit tests for string normalization functions (normalize, clean, sanitize)."""

import pytest

from ha_synthetic_sensors.evaluator_handlers.string_handler import StringHandler


class TestStringNormalizationFunctions:
    """Test string normalization functions."""

    @pytest.fixture
    def handler(self):
        """Create a StringHandler instance for testing."""
        return StringHandler()

    def test_can_handle_normalization_functions(self, handler):
        """Test that handler can handle normalization functions."""
        assert handler.can_handle("normalize('test')")
        assert handler.can_handle("clean('test')")
        assert handler.can_handle("sanitize('test')")

    def test_normalize_function(self, handler):
        """Test normalize function - normalizes whitespace."""
        # Multiple spaces
        result = handler.evaluate("normalize('  hello   world  ')")
        assert result == "hello world"

        # Tabs and newlines
        result = handler.evaluate("normalize('hello\\t\\nworld')")
        assert result == "hello world"

        # Mixed whitespace
        result = handler.evaluate("normalize('  \\t hello \\n  world  \\t  ')")
        assert result == "hello world"

        # Already normalized
        result = handler.evaluate("normalize('hello world')")
        assert result == "hello world"

        # Empty string
        result = handler.evaluate("normalize('')")
        assert result == ""

        # Only whitespace
        result = handler.evaluate("normalize('   \\t\\n   ')")
        assert result == ""

    def test_clean_function(self, handler):
        """Test clean function - removes non-alphanumeric except spaces."""
        # Special characters
        result = handler.evaluate("clean('hello@#$%world!')")
        assert result == "helloworld"

        # Keep spaces
        result = handler.evaluate("clean('hello world!')")
        assert result == "hello world"

        # Mixed content
        result = handler.evaluate("clean('device_name: test-123!')")
        assert result == "device_name test123"

        # Numbers and letters
        result = handler.evaluate("clean('test123')")
        assert result == "test123"

        # Only special characters
        result = handler.evaluate("clean('!@#$%')")
        assert result == ""

        # Underscores (alphanumeric)
        result = handler.evaluate("clean('test_device_name')")
        assert result == "test_device_name"

    def test_sanitize_function(self, handler):
        """Test sanitize function - replaces non-alphanumeric with underscores."""
        # Special characters
        result = handler.evaluate("sanitize('hello@#$%world!')")
        assert result == "hello____world_"

        # Spaces become underscores
        result = handler.evaluate("sanitize('hello world')")
        assert result == "hello_world"

        # Mixed content
        result = handler.evaluate("sanitize('device-name: test')")
        assert result == "device_name__test"

        # Already sanitized
        result = handler.evaluate("sanitize('test_device_name')")
        assert result == "test_device_name"

        # Only alphanumeric
        result = handler.evaluate("sanitize('test123')")
        assert result == "test123"

        # Only special characters
        result = handler.evaluate("sanitize('!@#$%')")
        assert result == "_____"

    def test_normalization_functions_with_context(self, handler):
        """Test normalization functions with context variables."""
        context = {
            "device_name": "  Living Room Sensor!!  ",
            "status": "active\t\nrunning",  # Use actual tab and newline, not escaped
            "description": "temp@sensor#1",
        }

        result = handler.evaluate("normalize(device_name)", context)
        assert result == "Living Room Sensor!!"

        result = handler.evaluate("clean(device_name)", context)
        assert result == "Living Room Sensor"

        result = handler.evaluate("sanitize(description)", context)
        assert result == "temp_sensor_1"

        result = handler.evaluate("normalize(status)", context)
        assert result == "active running"

    def test_nested_normalization_functions(self, handler):
        """Test nested normalization functions."""
        # Clean then normalize
        result = handler.evaluate("normalize(clean('  hello@world!!  '))")
        assert result == "helloworld"

        # Sanitize then normalize (sanitize should handle whitespace)
        result = handler.evaluate("normalize(sanitize('hello world!'))")
        assert result == "hello_world_"

        # Complex nesting
        result = handler.evaluate("clean(normalize('  test@device#name  '))")
        assert result == "testdevicename"

    def test_normalization_functions_in_concatenation(self, handler):
        """Test normalization functions within string concatenation."""
        # With normalize
        result = handler.evaluate("'Cleaned: ' + normalize('  hello   world  ')")
        assert result == "Cleaned: hello world"

        # With clean
        result = handler.evaluate("clean('device@name') + '_sensor'")
        assert result == "devicename_sensor"

        # With sanitize
        result = handler.evaluate("'sensor_' + sanitize('Living Room')")
        assert result == "sensor_Living_Room"

    def test_normalization_functions_with_numeric_conversion(self, handler):
        """Test normalization functions with numeric context."""
        context = {"temperature": 25.5, "humidity": 60}

        # Numbers get converted to strings first
        result = handler.evaluate("normalize(str(temperature))", context)
        assert result == "25.5"

        result = handler.evaluate("clean('60%')", context)
        assert result == "60"  # % gets removed by clean

        result = handler.evaluate("sanitize(str(temperature) + '°C')", context)
        assert result == "25_5_C"

    def test_normalization_functions_error_handling(self, handler):
        """Test normalization functions error handling."""
        # These should work without errors
        assert handler.evaluate("normalize('')") == ""
        assert handler.evaluate("clean('')") == ""
        assert handler.evaluate("sanitize('')") == ""

        # With None context
        result = handler.evaluate("normalize('test')", None)
        assert result == "test"

    def test_normalization_functions_empty_and_none_context(self, handler):
        """Test normalization functions with empty and None context."""
        # Empty context
        result = handler.evaluate("normalize('  test  ')", {})
        assert result == "test"

        result = handler.evaluate("clean('test@device')", {})
        assert result == "testdevice"

        result = handler.evaluate("sanitize('test device')", {})
        assert result == "test_device"

        # None context
        result = handler.evaluate("normalize('  test  ')", None)
        assert result == "test"

        result = handler.evaluate("clean('test@device')", None)
        assert result == "testdevice"

        result = handler.evaluate("sanitize('test device')", None)
        assert result == "test_device"
