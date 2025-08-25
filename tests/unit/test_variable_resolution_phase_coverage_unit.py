"""Additional unit tests for VariableResolutionPhase to improve coverage."""

import pytest
from unittest.mock import MagicMock, patch, Mock
from typing import Any

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import VariableResolutionPhase
from ha_synthetic_sensors.exceptions import MissingDependencyError
from ha_synthetic_sensors.type_definitions import ContextValue, DataProviderResult, ReferenceValue


class TestVariableResolutionPhaseCoverage:
    """Test cases for VariableResolutionPhase coverage gaps."""

    def test_resolve_collection_functions_property_with_preprocessor(self) -> None:
        """Test resolve_collection_functions property when preprocessor exists."""
        phase = VariableResolutionPhase()
        mock_preprocessor = MagicMock()
        mock_preprocessor._resolve_collection_functions = MagicMock()
        phase._formula_preprocessor = mock_preprocessor
        
        result = phase.resolve_collection_functions
        
        assert result == mock_preprocessor._resolve_collection_functions

    def test_resolve_collection_functions_property_no_preprocessor(self) -> None:
        """Test resolve_collection_functions property when no preprocessor."""
        phase = VariableResolutionPhase()
        phase._formula_preprocessor = None
        
        result = phase.resolve_collection_functions
        
        assert result is None

    def test_resolve_collection_functions_property_no_method(self) -> None:
        """Test resolve_collection_functions property when method doesn't exist."""
        phase = VariableResolutionPhase()
        mock_preprocessor = MagicMock()
        del mock_preprocessor._resolve_collection_functions
        phase._formula_preprocessor = mock_preprocessor
        
        result = phase.resolve_collection_functions
        
        assert result is None

    def test_set_dependency_handler_with_data_provider_callback(self) -> None:
        """Test set_dependency_handler when dependency handler has data_provider_callback."""
        phase = VariableResolutionPhase()
        mock_dependency_handler = MagicMock()
        mock_dependency_handler.data_provider_callback = MagicMock()
        mock_resolver_factory = MagicMock()
        phase._resolver_factory = mock_resolver_factory
        
        phase.set_dependency_handler(mock_dependency_handler)
        
        assert phase._dependency_handler == mock_dependency_handler
        mock_resolver_factory.set_dependency_handler.assert_called_once_with(mock_dependency_handler)
        mock_resolver_factory.update_data_provider_callback.assert_called_once_with(mock_dependency_handler.data_provider_callback)

    def test_set_dependency_handler_without_data_provider_callback(self) -> None:
        """Test set_dependency_handler when dependency handler has no data_provider_callback."""
        phase = VariableResolutionPhase()
        mock_dependency_handler = MagicMock()
        del mock_dependency_handler.data_provider_callback
        mock_resolver_factory = MagicMock()
        phase._resolver_factory = mock_resolver_factory
        
        phase.set_dependency_handler(mock_dependency_handler)
        
        assert phase._dependency_handler == mock_dependency_handler
        mock_resolver_factory.set_dependency_handler.assert_called_once_with(mock_dependency_handler)
        mock_resolver_factory.update_data_provider_callback.assert_not_called()

    def test_resolve_attribute_references_with_resolver(self) -> None:
        """Test _resolve_attribute_references with available resolver."""
        phase = VariableResolutionPhase()
        mock_resolver = MagicMock()
        mock_resolver.get_resolver_name.return_value = "AttributeReferenceResolver"
        mock_resolver.resolve_references_in_formula.return_value = "resolved_formula"
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.get_all_resolvers.return_value = [mock_resolver]
        phase._resolver_factory = mock_resolver_factory
        
        result = phase._resolve_attribute_references("test_formula", {})
        
        assert result == "resolved_formula"
        mock_resolver.resolve_references_in_formula.assert_called_once_with("test_formula", {})

    def test_resolve_attribute_references_with_resolver_exception(self) -> None:
        """Test _resolve_attribute_references when resolver raises exception."""
        phase = VariableResolutionPhase()
        mock_resolver = MagicMock()
        mock_resolver.get_resolver_name.return_value = "AttributeReferenceResolver"
        mock_resolver.resolve_references_in_formula.side_effect = Exception("Resolver error")
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.get_all_resolvers.return_value = [mock_resolver]
        phase._resolver_factory = mock_resolver_factory
        
        with pytest.raises(MissingDependencyError, match="Error resolving attribute references"):
            phase._resolve_attribute_references("test_formula", {})

    def test_resolve_attribute_references_no_resolver(self) -> None:
        """Test _resolve_attribute_references when no resolver available."""
        phase = VariableResolutionPhase()
        mock_resolver = MagicMock()
        mock_resolver.get_resolver_name.return_value = "OtherResolver"
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.get_all_resolvers.return_value = [mock_resolver]
        phase._resolver_factory = mock_resolver_factory
        
        result = phase._resolve_attribute_references("test_formula", {})
        
        assert result == "test_formula"

    def test_resolve_attribute_references_no_method(self) -> None:
        """Test _resolve_attribute_references when resolver has no method."""
        phase = VariableResolutionPhase()
        mock_resolver = MagicMock()
        mock_resolver.get_resolver_name.return_value = "AttributeReferenceResolver"
        del mock_resolver.resolve_references_in_formula
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.get_all_resolvers.return_value = [mock_resolver]
        phase._resolver_factory = mock_resolver_factory
        
        result = phase._resolve_attribute_references("test_formula", {})
        
        assert result == "test_formula"

    def test_resolve_collection_functions_with_preprocessor(self) -> None:
        """Test _resolve_collection_functions with preprocessor."""
        phase = VariableResolutionPhase()
        mock_preprocessor = MagicMock()
        mock_resolve_func = MagicMock()
        mock_resolve_func.return_value = "resolved_formula"
        mock_preprocessor._resolve_collection_functions = mock_resolve_func
        phase._formula_preprocessor = mock_preprocessor
        
        sensor_config = SensorConfig(unique_id="test_sensor")
        
        result = phase._resolve_collection_functions("test_formula", sensor_config, {})
        
        assert result == "resolved_formula"
        mock_resolve_func.assert_called_once_with("test_formula", {"sensor.test_sensor"})

    def test_resolve_collection_functions_with_preprocessor_exception(self) -> None:
        """Test _resolve_collection_functions when preprocessor raises exception."""
        phase = VariableResolutionPhase()
        mock_preprocessor = MagicMock()
        mock_resolve_func = MagicMock()
        mock_resolve_func.side_effect = Exception("Preprocessor error")
        mock_preprocessor._resolve_collection_functions = mock_resolve_func
        phase._formula_preprocessor = mock_preprocessor
        
        sensor_config = SensorConfig(unique_id="test_sensor")
        
        with pytest.raises(MissingDependencyError, match="Error resolving collection functions"):
            phase._resolve_collection_functions("test_formula", sensor_config, {})

    def test_resolve_collection_functions_no_preprocessor(self) -> None:
        """Test _resolve_collection_functions without preprocessor."""
        phase = VariableResolutionPhase()
        phase._formula_preprocessor = None
        
        result = phase._resolve_collection_functions("test_formula", None, {})
        
        assert result == "test_formula"

    def test_resolve_collection_functions_no_sensor_config(self) -> None:
        """Test _resolve_collection_functions without sensor config."""
        phase = VariableResolutionPhase()
        mock_preprocessor = MagicMock()
        mock_resolve_func = MagicMock()
        mock_resolve_func.return_value = "resolved_formula"
        mock_preprocessor._resolve_collection_functions = mock_resolve_func
        phase._formula_preprocessor = mock_preprocessor
        
        result = phase._resolve_collection_functions("test_formula", None, {})
        
        assert result == "resolved_formula"
        mock_resolve_func.assert_called_once_with("test_formula", None)

    def test_resolve_collection_functions_no_unique_id(self) -> None:
        """Test _resolve_collection_functions without unique_id."""
        phase = VariableResolutionPhase()
        mock_preprocessor = MagicMock()
        mock_resolve_func = MagicMock()
        mock_resolve_func.return_value = "resolved_formula"
        mock_preprocessor._resolve_collection_functions = mock_resolve_func
        phase._formula_preprocessor = mock_preprocessor
        
        sensor_config = SensorConfig(unique_id="")
        
        result = phase._resolve_collection_functions("test_formula", sensor_config, {})
        
        assert result == "resolved_formula"
        mock_resolve_func.assert_called_once_with("test_formula", None)

    @patch("ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.MetadataHandler")
    def test_resolve_metadata_functions_success(self, mock_metadata_handler_class) -> None:
        """Test _resolve_metadata_functions successful resolution."""
        phase = VariableResolutionPhase()
        mock_hass = MagicMock()
        phase._hass = mock_hass
        
        mock_handler = MagicMock()
        mock_handler.evaluate.return_value = "metadata_value"
        mock_metadata_handler_class.return_value = mock_handler
        
        # Mock isinstance to return True for MetadataHandler
        with patch("ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.isinstance", return_value=True):
            sensor_config = SensorConfig(unique_id="test_sensor")
            formula_config = FormulaConfig(id="test_formula", formula="test")
            eval_context = {"test": "value"}
            
            result = phase._resolve_metadata_functions(
                "metadata(sensor.test, 'friendly_name')", 
                sensor_config, 
                eval_context, 
                formula_config
            )
            
            assert "metadata_value" in result
            mock_handler.evaluate.assert_called_once()

    @patch("ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.MetadataHandler")
    def test_resolve_metadata_functions_exception(self, mock_metadata_handler_class) -> None:
        """Test _resolve_metadata_functions when handler raises exception."""
        phase = VariableResolutionPhase()
        mock_hass = MagicMock()
        phase._hass = mock_hass
        
        mock_handler = MagicMock()
        mock_handler.evaluate.side_effect = Exception("Metadata error")
        mock_metadata_handler_class.return_value = mock_handler
        
        sensor_config = SensorConfig(unique_id="test_sensor")
        
        result = phase._resolve_metadata_functions(
            "metadata(sensor.test, 'friendly_name')", 
            sensor_config, 
            {}, 
            None
        )
        
        # Should return original formula when exception occurs
        assert "metadata(sensor.test, 'friendly_name')" in result

    @patch("ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.MetadataHandler")
    def test_resolve_metadata_functions_not_metadata_handler(self, mock_metadata_handler_class) -> None:
        """Test _resolve_metadata_functions when handler is not MetadataHandler."""
        phase = VariableResolutionPhase()
        mock_hass = MagicMock()
        phase._hass = mock_hass
        
        mock_handler = MagicMock()
        mock_metadata_handler_class.return_value = mock_handler
        
        # Make isinstance check fail
        with patch("ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.isinstance", return_value=False):
            sensor_config = SensorConfig(unique_id="test_sensor")
            
            result = phase._resolve_metadata_functions(
                "metadata(sensor.test, 'friendly_name')", 
                sensor_config, 
                {}, 
                None
            )
            
            # Should return original formula when handler is not MetadataHandler
            assert "metadata(sensor.test, 'friendly_name')" in result

    def test_resolve_config_variables_with_reference_value(self) -> None:
        """Test resolve_config_variables with ReferenceValue return."""
        phase = VariableResolutionPhase()
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.resolve_variable.return_value = ReferenceValue(reference="test", value="value")
        phase._resolver_factory = mock_resolver_factory
        
        eval_context = {}
        config = FormulaConfig(id="test_formula", formula="test")
        
        with patch("ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.resolve_config_variables") as mock_resolve:
            phase.resolve_config_variables(eval_context, config, None)
            
            mock_resolve.assert_called_once()
            # Get the callback function that was passed
            callback = mock_resolve.call_args[0][2]
            
            # Test the callback with ReferenceValue
            result = callback("test_var", "test_value", {}, None)
            assert isinstance(result, ReferenceValue)
            assert result.reference == "test"
            assert result.value == "value"

    def test_resolve_config_variables_with_string_value(self) -> None:
        """Test resolve_config_variables with string value return."""
        phase = VariableResolutionPhase()
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.resolve_variable.return_value = "resolved_value"
        phase._resolver_factory = mock_resolver_factory
        
        eval_context = {}
        config = FormulaConfig(id="test_formula", formula="test")
        
        with patch("ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.resolve_config_variables") as mock_resolve:
            phase.resolve_config_variables(eval_context, config, None)
            
            mock_resolve.assert_called_once()
            # Get the callback function that was passed
            callback = mock_resolve.call_args[0][2]
            
            # Test the callback with string value
            result = callback("test_var", "test_value", {}, None)
            assert isinstance(result, ReferenceValue)
            assert result.reference == "test_value"
            assert result.value == "resolved_value"

    def test_resolve_config_variables_with_non_string_value(self) -> None:
        """Test resolve_config_variables with non-string value return."""
        phase = VariableResolutionPhase()
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.resolve_variable.return_value = 42
        phase._resolver_factory = mock_resolver_factory
        
        eval_context = {}
        config = FormulaConfig(id="test_formula", formula="test")
        
        with patch("ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase.resolve_config_variables") as mock_resolve:
            phase.resolve_config_variables(eval_context, config, None)
            
            mock_resolve.assert_called_once()
            # Get the callback function that was passed
            callback = mock_resolve.call_args[0][2]
            
            # Test the callback with non-string value
            result = callback("test_var", 42, {}, None)
            assert isinstance(result, ReferenceValue)
            assert result.reference == "test_var"
            assert result.value == 42

    def test_resolve_state_attribute_references_no_mapping(self) -> None:
        """Test _resolve_state_attribute_references with no mapping."""
        phase = VariableResolutionPhase()
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.sensor_to_backing_mapping = {}
        phase._resolver_factory = mock_resolver_factory
        
        sensor_config = SensorConfig(unique_id="test_sensor")
        
        result = phase._resolve_state_attribute_references("test_formula", sensor_config)
        
        assert result == "test_formula"

    def test_resolve_state_attribute_references_no_data_provider(self) -> None:
        """Test _resolve_state_attribute_references with no data provider."""
        phase = VariableResolutionPhase()
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.sensor_to_backing_mapping = {"test_sensor": "sensor.backing"}
        mock_resolver_factory.data_provider_callback = None
        phase._resolver_factory = mock_resolver_factory
        
        sensor_config = SensorConfig(unique_id="test_sensor")
        
        result = phase._resolve_state_attribute_references("test_formula", sensor_config)
        
        assert result == "test_formula"

    def test_resolve_state_attribute_references_entity_not_exists(self) -> None:
        """Test _resolve_state_attribute_references when entity doesn't exist."""
        phase = VariableResolutionPhase()
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.sensor_to_backing_mapping = {"test_sensor": "sensor.backing"}
        mock_data_provider = MagicMock()
        mock_data_provider.return_value = {"exists": False}
        mock_resolver_factory.data_provider_callback = mock_data_provider
        phase._resolver_factory = mock_resolver_factory
        
        sensor_config = SensorConfig(unique_id="test_sensor")
        
        result = phase._resolve_state_attribute_references("test_formula", sensor_config)
        
        assert result == "test_formula"
        mock_data_provider.assert_called_once_with("sensor.backing")

    def test_resolve_state_attribute_references_no_attributes(self) -> None:
        """Test _resolve_state_attribute_references with no attributes."""
        phase = VariableResolutionPhase()
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.sensor_to_backing_mapping = {"test_sensor": "sensor.backing"}
        mock_data_provider = MagicMock()
        mock_data_provider.return_value = {"exists": True, "attributes": None}
        mock_resolver_factory.data_provider_callback = mock_data_provider
        phase._resolver_factory = mock_resolver_factory
        
        sensor_config = SensorConfig(unique_id="test_sensor")
        
        result = phase._resolve_state_attribute_references("test_formula", sensor_config)
        
        assert result == "test_formula"

    def test_resolve_state_attribute_references_with_attributes(self) -> None:
        """Test _resolve_state_attribute_references with attributes."""
        phase = VariableResolutionPhase()
        mock_resolver_factory = MagicMock()
        mock_resolver_factory.sensor_to_backing_mapping = {"test_sensor": "sensor.backing"}
        mock_data_provider = MagicMock()
        mock_data_provider.return_value = {
            "exists": True, 
            "attributes": {"friendly_name": "Test Sensor", "unit_of_measurement": "W"}
        }
        mock_resolver_factory.data_provider_callback = mock_data_provider
        phase._resolver_factory = mock_resolver_factory
        
        sensor_config = SensorConfig(unique_id="test_sensor")
        
        result = phase._resolve_state_attribute_references(
            "state.attributes.friendly_name + state.attributes.unit_of_measurement", 
            sensor_config
        )
        
        # Should replace the attribute references
        assert "Test Sensor" in result
        assert "W" in result
        assert "state.attributes.friendly_name" not in result
        assert "state.attributes.unit_of_measurement" not in result
