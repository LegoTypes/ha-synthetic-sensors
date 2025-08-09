"""Unit tests for ReferenceValueManager."""

import pytest
from unittest.mock import patch, MagicMock

from src.ha_synthetic_sensors.reference_value_manager import ReferenceValueManager
from src.ha_synthetic_sensors.type_definitions import ReferenceValue, ContextValue


class TestReferenceValueManager:
    """Test the ReferenceValueManager component."""

    def test_set_variable_with_reference_value_basic(self):
        """Test basic variable setting with reference value."""
        context = {}

        ReferenceValueManager.set_variable_with_reference_value(context, "test_var", "original_ref", "test_value")

        assert "test_var" in context
        assert isinstance(context["test_var"], ReferenceValue)
        assert context["test_var"].reference == "original_ref"
        assert context["test_var"].value == "test_value"

    def test_set_variable_with_reference_value_existing_ref_value(self):
        """Test setting variable when value is already a ReferenceValue."""
        context = {}
        existing_ref = ReferenceValue("existing_ref", "existing_value")

        ReferenceValueManager.set_variable_with_reference_value(context, "test_var", "new_ref", existing_ref)

        assert "test_var" in context
        assert isinstance(context["test_var"], ReferenceValue)
        # Should preserve the existing ReferenceValue
        assert context["test_var"].reference == "existing_ref"
        assert context["test_var"].value == "existing_value"

    @patch("src.ha_synthetic_sensors.reference_value_manager._LOGGER")
    def test_set_variable_debug_logging(self, mock_logger):
        """Test that debug logging works correctly."""
        context = {}

        ReferenceValueManager.set_variable_with_reference_value(context, "test_var", "ref", 42)

        # Should log the variable setting
        mock_logger.debug.assert_called()

    def test_convert_to_evaluation_context_ref_values(self):
        """Test converting context with ReferenceValue objects."""
        ref_value = ReferenceValue("test_ref", "test_value")
        context = {"var1": ref_value, "var2": None, "_private": "private_value"}

        result = ReferenceValueManager.convert_to_evaluation_context(context)

        assert result["var1"] == ref_value
        assert result["var2"] is None
        assert result["_private"] == "private_value"

    def test_convert_to_evaluation_context_callable(self):
        """Test converting context with callable objects."""
        mock_callable = MagicMock()
        context = {"func": mock_callable}

        result = ReferenceValueManager.convert_to_evaluation_context(context)

        assert result["func"] == mock_callable

    def test_convert_to_evaluation_context_state_object(self):
        """Test converting context with State objects."""
        mock_state = MagicMock()
        context = {"state": mock_state}

        result = ReferenceValueManager.convert_to_evaluation_context(context)

        assert result["state"] == mock_state

    def test_convert_to_evaluation_context_dict(self):
        """Test converting context with dict objects (ConfigType)."""
        config_dict = {"key": "value"}
        context = {"config": config_dict}

        result = ReferenceValueManager.convert_to_evaluation_context(context)

        assert result["config"] == config_dict

    @patch("src.ha_synthetic_sensors.reference_value_manager._LOGGER")
    def test_convert_to_evaluation_context_raw_string_error(self, mock_logger):
        """Test that raw string values raise TypeError."""
        context = {"raw_var": "raw_string"}

        with pytest.raises(TypeError) as exc_info:
            ReferenceValueManager.convert_to_evaluation_context(context)

        assert "raw value for variable 'raw_var'" in str(exc_info.value)
        assert "ReferenceValue objects" in str(exc_info.value)
        mock_logger.error.assert_called()

    @patch("src.ha_synthetic_sensors.reference_value_manager._LOGGER")
    def test_convert_to_evaluation_context_raw_int_error(self, mock_logger):
        """Test that raw int values raise TypeError."""
        context = {"raw_var": 42}

        with pytest.raises(TypeError) as exc_info:
            ReferenceValueManager.convert_to_evaluation_context(context)

        assert "raw value for variable 'raw_var'" in str(exc_info.value)
        mock_logger.error.assert_called()

    @patch("src.ha_synthetic_sensors.reference_value_manager._LOGGER")
    def test_convert_to_evaluation_context_raw_float_error(self, mock_logger):
        """Test that raw float values raise TypeError."""
        context = {"raw_var": 3.14}

        with pytest.raises(TypeError) as exc_info:
            ReferenceValueManager.convert_to_evaluation_context(context)

        assert "raw value for variable 'raw_var'" in str(exc_info.value)
        mock_logger.error.assert_called()

    @patch("src.ha_synthetic_sensors.reference_value_manager._LOGGER")
    def test_convert_to_evaluation_context_raw_bool_error(self, mock_logger):
        """Test that raw bool values raise TypeError."""
        context = {"raw_var": True}

        with pytest.raises(TypeError) as exc_info:
            ReferenceValueManager.convert_to_evaluation_context(context)

        assert "raw value for variable 'raw_var'" in str(exc_info.value)
        mock_logger.error.assert_called()

    @patch("src.ha_synthetic_sensors.reference_value_manager._LOGGER")
    def test_convert_to_evaluation_context_debug_info(self, mock_logger):
        """Test that debug information is logged on type safety violations."""
        context = {"raw_var": "bad_value", "_entity_reference_registry": {"entity1": "ref1", "entity2": "ref2"}}

        with pytest.raises(TypeError):
            ReferenceValueManager.convert_to_evaluation_context(context)

        # Verify debug information was logged
        mock_logger.error.assert_any_call(
            "TYPE SAFETY VIOLATION: Variable '%s' has raw value '%s' instead of ReferenceValue", "raw_var", "bad_value"
        )

    @patch("src.ha_synthetic_sensors.reference_value_manager._LOGGER")
    def test_convert_to_evaluation_context_other_types(self, mock_logger):
        """Test converting context with other types (logs debug and allows)."""
        custom_object = object()
        context = {"custom": custom_object}

        result = ReferenceValueManager.convert_to_evaluation_context(context)

        assert result["custom"] == custom_object
        mock_logger.debug.assert_called_with("Converting context: allowing type %s for key '%s'", "object", "custom")
