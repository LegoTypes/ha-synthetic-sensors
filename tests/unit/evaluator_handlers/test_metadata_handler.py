"""Unit tests for MetadataHandler."""

from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock
import pytest

from ha_synthetic_sensors.evaluator_handlers.metadata_handler import MetadataHandler


class TestMetadataHandler:
    """Test the MetadataHandler in isolation."""

    def test_can_handle_metadata_function(self):
        """Test that can_handle correctly identifies metadata() calls."""
        handler = MetadataHandler()

        # Should handle metadata function calls
        assert handler.can_handle("metadata(power_entity, 'last_changed')")
        assert handler.can_handle("metadata(1000.0, 'entity_id')")
        assert handler.can_handle("some_value + metadata(temp_sensor, 'last_updated')")

        # Should not handle non-metadata expressions
        assert not handler.can_handle("now()")
        assert not handler.can_handle("power_entity + 100")
        assert not handler.can_handle("split(some_string, ',')")

    def test_metadata_function_evaluation_last_changed(self):
        """Test evaluation of metadata() function for last_changed."""
        # Create mock Home Assistant instance
        mock_hass = Mock()
        mock_state = Mock()

        # Set up test timestamp
        test_timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_state.last_changed = test_timestamp
        mock_state.entity_id = "sensor.test_entity"

        mock_hass.states.get.return_value = mock_state

        # Create handler with mock hass
        handler = MetadataHandler(hass=mock_hass)

        # Test evaluation
        formula = "metadata(sensor.test_entity, 'last_changed')"
        result, metadata_results = handler.evaluate(formula)

        # Should return transformed formula and metadata results
        expected_formula = "metadata_result(_metadata_0)"
        expected_metadata = {"_metadata_0": test_timestamp.isoformat()}
        assert result == expected_formula
        assert metadata_results == expected_metadata

        # Verify hass.states.get was called correctly
        mock_hass.states.get.assert_called_once_with("sensor.test_entity")

    def test_metadata_function_evaluation_entity_id(self):
        """Test evaluation of metadata() function for entity_id."""
        # Create mock Home Assistant instance
        mock_hass = Mock()
        mock_state = Mock()

        mock_state.entity_id = "sensor.test_power"
        mock_hass.states.get.return_value = mock_state

        # Create handler with mock hass
        handler = MetadataHandler(hass=mock_hass)

        # Test evaluation
        formula = "metadata(sensor.test_power, 'entity_id')"
        result, metadata_results = handler.evaluate(formula)

        # Should return transformed formula and metadata results
        expected_formula = "metadata_result(_metadata_0)"
        expected_metadata = {"_metadata_0": "sensor.test_power"}
        assert result == expected_formula
        assert metadata_results == expected_metadata

    def test_metadata_function_with_variable_resolution(self):
        """Test metadata() function with variable context."""
        # Create mock Home Assistant instance
        mock_hass = Mock()
        mock_state = Mock()

        mock_state.entity_id = "sensor.power_meter"
        mock_hass.states.get.return_value = mock_state

        # Create handler with mock hass
        handler = MetadataHandler(hass=mock_hass)

        # Test evaluation with context variable - use ReferenceValue (ReferenceValue architecture)
        from ha_synthetic_sensors.type_definitions import ReferenceValue

        formula = "metadata(power_var, 'entity_id')"
        context = {"power_var": ReferenceValue("sensor.power_meter", "sensor.power_meter")}

        result, metadata_results = handler.evaluate(formula, context)

        # Should return transformed formula and metadata results
        expected_formula = "metadata_result(_metadata_0)"
        expected_metadata = {"_metadata_0": "sensor.power_meter"}
        assert result == expected_formula
        assert metadata_results == expected_metadata

        # Verify the resolved entity_id was used
        mock_hass.states.get.assert_called_once_with("sensor.power_meter")

    def test_metadata_function_invalid_key(self):
        """Test metadata() function with invalid metadata key."""
        mock_hass = Mock()

        # Create a custom state object that only has specific attributes
        class MockState:
            def __init__(self):
                self.entity_id = "sensor.test"
                self.attributes = {}

            def __getattr__(self, name):
                # Only allow access to known attributes
                if name in ["entity_id", "attributes"]:
                    return getattr(self, name)
                raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        mock_state = MockState()
        mock_hass.states.get.return_value = mock_state

        handler = MetadataHandler(hass=mock_hass)

        # Test with invalid key
        formula = "metadata(sensor.test, 'invalid_key')"

        with pytest.raises(ValueError, match="Metadata key 'invalid_key' not found for entity 'sensor.test'"):
            handler.evaluate(formula)

    def test_metadata_function_missing_entity(self):
        """Test metadata() function with non-existent entity."""
        mock_hass = Mock()
        mock_hass.states.get.return_value = None  # Entity not found

        handler = MetadataHandler(hass=mock_hass)

        formula = "metadata(sensor.nonexistent, 'entity_id')"

        with pytest.raises(ValueError, match="Entity 'sensor.nonexistent' not found"):
            handler.evaluate(formula)

    def test_metadata_function_no_hass(self):
        """Test metadata() function without Home Assistant instance."""
        handler = MetadataHandler()  # No hass instance

        formula = "metadata(sensor.test, 'entity_id')"

        with pytest.raises(ValueError, match="Home Assistant instance not available"):
            handler.evaluate(formula)

    def test_metadata_function_wrong_parameter_count(self):
        """Test metadata() function with wrong number of parameters."""
        mock_hass = Mock()
        handler = MetadataHandler(hass=mock_hass)

        # Too few parameters
        formula = "metadata(sensor.test)"
        with pytest.raises(ValueError, match="metadata\\(\\) function requires exactly 2 parameters, got 1"):
            handler.evaluate(formula)

        # Too many parameters
        formula = "metadata(sensor.test, 'entity_id', 'extra')"
        with pytest.raises(ValueError, match="metadata\\(\\) function requires exactly 2 parameters, got 3"):
            handler.evaluate(formula)

    def test_multiple_metadata_calls(self):
        """Test formula with multiple metadata() calls."""
        mock_hass = Mock()

        # Set up two different mock states
        mock_state1 = Mock()
        mock_state1.entity_id = "sensor.power"
        mock_state2 = Mock()
        mock_state2.entity_id = "sensor.temp"

        # Configure mock to return different states for different entity_ids
        def get_state(entity_id):
            if entity_id == "sensor.power":
                return mock_state1
            elif entity_id == "sensor.temp":
                return mock_state2
            return None

        mock_hass.states.get.side_effect = get_state

        handler = MetadataHandler(hass=mock_hass)

        # Test formula with multiple metadata calls
        formula = "metadata(sensor.power, 'entity_id') + metadata(sensor.temp, 'entity_id')"
        result, metadata_results = handler.evaluate(formula)

        # Should return transformed formula and metadata results
        expected_formula = "metadata_result(_metadata_0) + metadata_result(_metadata_1)"
        expected_metadata = {"_metadata_0": "sensor.power", "_metadata_1": "sensor.temp"}
        assert result == expected_formula
        assert metadata_results == expected_metadata

    def test_get_handler_info(self):
        """Test handler information methods."""
        handler = MetadataHandler()

        assert handler.get_handler_name() == "metadata"
        assert handler.get_supported_functions() == {"metadata"}

        function_info = handler.get_function_info()
        assert len(function_info) == 1
        assert function_info[0]["name"] == "metadata"
        assert "last_changed" in function_info[0]["valid_keys"]
        assert "entity_id" in function_info[0]["valid_keys"]
