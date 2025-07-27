"""Tests for formula_constants module."""

import pytest

from ha_synthetic_sensors.formula_constants import __getattr__
from ha_synthetic_sensors.ha_constants import HAConstantLoader


class TestFormulaConstants:
    """Test formula constants lazy loading functionality."""

    def test_getattr_loads_valid_ha_constants(self):
        """Test that __getattr__ successfully loads known HA constants."""
        # Test with constants that should definitely exist in HA
        state_on = __getattr__("STATE_ON")
        assert state_on == "on"

        state_off = __getattr__("STATE_OFF")
        assert state_off == "off"

        state_unknown = __getattr__("STATE_UNKNOWN")
        assert state_unknown == "unknown"

    def test_getattr_raises_attributeerror_for_invalid_constants(self):
        """Test that __getattr__ raises AttributeError for invalid constants."""
        with pytest.raises(AttributeError, match="has no attribute 'DEFINITELY_NOT_A_CONSTANT'"):
            __getattr__("DEFINITELY_NOT_A_CONSTANT")

        with pytest.raises(AttributeError, match="has no attribute 'INVALID_CONSTANT_NAME'"):
            __getattr__("INVALID_CONSTANT_NAME")

    def test_getattr_handles_empty_string(self):
        """Test that __getattr__ raises AttributeError for empty string."""
        with pytest.raises(AttributeError, match="has no attribute ''"):
            __getattr__("")

    def test_getattr_caching_behavior(self):
        """Test that repeated calls return the same cached result."""
        # First call loads from HA
        result1 = __getattr__("STATE_ON")

        # Second call should return cached value
        result2 = __getattr__("STATE_ON")

        # Should be identical
        assert result1 is result2
        assert result1 == "on"

    def test_getattr_consistent_with_ha_constant_loader(self):
        """Test that __getattr__ returns same values as HAConstantLoader."""
        constant_name = "STATE_OFF"

        # Get via __getattr__
        formula_result = __getattr__(constant_name)

        # Get via HAConstantLoader directly
        loader_result = HAConstantLoader.get_constant(constant_name)

        # Should be identical
        assert formula_result == loader_result
        assert formula_result == "off"

    def test_multiple_state_constants(self):
        """Test loading multiple state constants to verify they have expected values."""
        expected_constants = {
            "STATE_ON": "on",
            "STATE_OFF": "off",
            "STATE_UNKNOWN": "unknown",
            "STATE_OPEN": "open",
            "STATE_CLOSED": "closed",
            "STATE_HOME": "home",
            "STATE_NOT_HOME": "not_home",
        }

        for constant_name, expected_value in expected_constants.items():
            actual_value = __getattr__(constant_name)
            assert actual_value == expected_value, f"{constant_name} should be '{expected_value}', got '{actual_value}'"

    def test_device_class_constants_exist(self):
        """Test that device class constants can be loaded."""
        # These should exist as enums or classes
        sensor_device_class = __getattr__("SensorDeviceClass")
        assert sensor_device_class is not None

        binary_sensor_device_class = __getattr__("BinarySensorDeviceClass")
        assert binary_sensor_device_class is not None

    def test_error_message_format(self):
        """Test that error messages are properly formatted."""
        with pytest.raises(AttributeError) as exc_info:
            __getattr__("NONEXISTENT_CONSTANT")

        error_msg = str(exc_info.value)
        assert "ha_synthetic_sensors.formula_constants" in error_msg
        assert "NONEXISTENT_CONSTANT" in error_msg
        assert "has no attribute" in error_msg

    def test_case_sensitive_constants(self):
        """Test that constant names are case sensitive."""
        # This should work
        state_on = __getattr__("STATE_ON")
        assert state_on == "on"

        # This should fail - wrong case
        with pytest.raises(AttributeError):
            __getattr__("state_on")

        with pytest.raises(AttributeError):
            __getattr__("State_On")

    def test_lazy_loading_performance(self):
        """Test that constants are only loaded when accessed."""
        # Clear cache to ensure fresh test
        HAConstantLoader.clear_cache()

        # First access should load from HA
        result1 = __getattr__("STATE_ON")

        # Second access should be from cache (faster)
        result2 = __getattr__("STATE_ON")

        # Results should be identical (same object)
        assert result1 is result2

        # Clean up
        HAConstantLoader.clear_cache()
